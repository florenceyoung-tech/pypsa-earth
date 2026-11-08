"""Add a fuel-based CO2 cap using PyPSA's carrier-level primary_energy convention."""
import logging
import pandas as pd
import pypsa
from nigeria_consistency import set_emission_factors

logger = logging.getLogger(__name__)
CONSTRAINT_NAME = "co2_emission_limit"


def add_constraint(input_path, output_path, limit_tonnes, costs_csv_path):
    if limit_tonnes < 0:
        raise ValueError("CO2 limit cannot be negative")
    n = pypsa.Network(input_path)
    costs = pd.read_csv(costs_csv_path, index_col=0)
    set_emission_factors(n, costs)
    # Carrier factor is tCO2/MWh_fuel. PyPSA divides by each generator's
    # effective efficiency. Never pre-divide the factor a second time.
    if CONSTRAINT_NAME in n.global_constraints.index:
        n.remove("GlobalConstraint", CONSTRAINT_NAME)
    n.add("GlobalConstraint", CONSTRAINT_NAME, type="primary_energy",
          carrier_attribute="co2_emissions", sense="<=", constant=limit_tonnes)
    n.export_to_netcdf(output_path)
    logger.info("Added %.4f Mt CO2 model-period cap", limit_tonnes / 1e6)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake
        snakemake = mock_snakemake("add_co2_constraint")
    logging.basicConfig(level=logging.INFO)
    add_constraint(snakemake.input.network, snakemake.output.network,
                   float(snakemake.params.co2_limit), snakemake.input.costs)
