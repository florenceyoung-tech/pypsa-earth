"""Add a CO2 global constraint to a prepared network.

Called by a custom rule between prepare_network and solve_network.
Idempotent: safe to run on a network that already has the constraint.
"""

import logging
import pypsa

logger = logging.getLogger(__name__)

EF = {
    "CCGT": 0.184,
    "OCGT": 0.297,
    "oil": 0.268,
    "coal": 0.339,
}

CONSTRAINT_NAME = "co2_emission_limit"


def add_constraint(input_path, output_path, limit_tonnes):
    n = pypsa.Network(input_path)

    # Populate co2_emissions on each generator
    if "co2_emissions" not in n.generators.columns:
        n.generators["co2_emissions"] = 0.0

    carriers = n.generators["carrier"].astype(str).tolist()
    col = n.generators.columns.get_loc("co2_emissions")
    for i, carrier in enumerate(carriers):
        for key, ef in EF.items():
            if key.lower() in carrier.lower():
                n.generators.iloc[i, col] = ef

    # Remove any existing co2 constraint so the add below does not fail
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
    )
