"""Add a CO2 global constraint to a prepared network.

Called by a custom rule between prepare_network and solve_network.
Idempotent: safe to run on a network that already has the constraint.

Emission factors are read from the processed cost data
(resources/<RDIR>/costs_<year>_<scope>.csv), using:

    EF[carrier] (tCO2/MWh_e) = CO2_intensity (tCO2/MWh_th)
                              / efficiency (MWh_th/MWh_e)

The CO2_intensity and efficiency rows are looked up per carrier. If a
carrier is missing from the cost data, the script falls back to a
conservative hard-coded value and logs a warning.
"""

import logging
import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

# Fallback EF (tCO2/MWh_e) used only if the cost data is missing an entry.
# These are conservative defaults; the primary source is costs.csv.
EF_FALLBACK = {
    "CCGT": 0.342,
    "OCGT": 0.489,
    "oil": 0.268,
    "coal": 0.339,
}

CONSTRAINT_NAME = "co2_emission_limit"


def load_emission_factors(costs_csv_path):
    """Return dict carrier -> tCO2/MWh_e derived from the processed cost data.

    The processed file (resources/<RDIR>/costs_<year>_elec.csv) is wide:
    one row per technology, with columns including 'co2_emissions'
    (tCO2/MWh_th) and 'efficiency' (MWh_th/MWh_e).
    """
    costs = pd.read_csv(costs_csv_path, index_col="technology")

    if "co2_emissions" not in costs.columns or "efficiency" not in costs.columns:
        raise ValueError(
            f"costs file {costs_csv_path} is missing required columns "
            f"'co2_emissions' and/or 'efficiency'; found: {list(costs.columns)}"
        )

    ef = {}
    for tech, row in costs.iterrows():
        ci = row["co2_emissions"]
        eff = row["efficiency"]
        if pd.notna(ci) and pd.notna(eff) and eff > 0:
            ef[tech] = float(ci) / float(eff)
    logger.info("Derived emission factors from %s: %s", costs_csv_path, ef)
    return ef


def add_constraint(input_path, output_path, limit_tonnes, costs_csv_path):
    n = pypsa.Network(input_path)

    ef_by_carrier = load_emission_factors(costs_csv_path)

    if "co2_emissions" not in n.generators.columns:
        n.generators["co2_emissions"] = 0.0

    carriers = n.generators["carrier"].astype(str).tolist()
    col = n.generators.columns.get_loc("co2_emissions")

    for i, carrier in enumerate(carriers):
        matched = False
        # Prefer longest-match to avoid "gas" matching before "CCGT"
        for key, ef in sorted(ef_by_carrier.items(), key=lambda x: -len(x[0])):
            if key.lower() in carrier.lower():
                n.generators.iloc[i, col] = ef
                matched = True
                break
        if not matched:
            for key, ef in sorted(EF_FALLBACK.items(), key=lambda x: -len(x[0])):
                if key.lower() in carrier.lower():
                    n.generators.iloc[i, col] = ef
                    logger.warning(
                        "Carrier %r not in cost data; using fallback EF=%s",
                        carrier, ef,
                    )
                    matched = True
                    break
        if not matched:
            logger.warning("No EF found for carrier %r; setting 0.0", carrier)

    if CONSTRAINT_NAME in n.global_constraints.index:
        n.global_constraints.drop(CONSTRAINT_NAME, inplace=True)

    n.add(
        "GlobalConstraint",
        CONSTRAINT_NAME,
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=limit_tonnes,
    )

    n.export_to_netcdf(output_path)
    logger.info(
        "Added CO2 constraint of %.2f Mt to %s", limit_tonnes / 1e6, output_path
    )


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("add_co2_constraint")

    logging.basicConfig(level=logging.INFO)
    add_constraint(
        snakemake.input.network,
        snakemake.output.network,
        float(snakemake.params.co2_limit),
        snakemake.input.costs,
    )