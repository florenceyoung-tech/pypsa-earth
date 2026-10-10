"""Figure registry. Every module exposes make(metrics) -> Path."""
from importlib import import_module
from pathlib import Path

FIGURE_MODULES = [
    "fig_5_01_capacity",
    "fig_5_02_generation",
    "fig_5_03_wacc_sweep",
    "fig_5_04_emissions",
    "fig_5_05_system_cost",
    "fig_5_06_cost_of_cap",
    "fig_5_07_financing_gap",
    "fig_5_08_lcoe_curves",
    "fig_5_09_lcoe_crossover",
    "fig_5_10_policy_derisking",
    "fig_5_11_gas_price",
    "fig_5_12_battery",
    "fig_5_13_dispatch_weeks",
    "fig_5_14_gen_duration",
    "fig_5_15_price_duration",
    "fig_5_16_curtailment_map",
]

def all_figures():
    for name in FIGURE_MODULES:
        yield import_module(f"figures.{name}")
