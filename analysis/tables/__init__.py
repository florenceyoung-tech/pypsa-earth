"""Table registry. Every module exposes make(metrics) -> Path."""
from importlib import import_module

TABLE_MODULES = [
    "tbl_5_01_headline",
    "tbl_5_02_lcoe",
    "tbl_5_03_instrument_effectiveness",
    "tbl_5_04_debt_equity",
    "tbl_5_05_gas_price_effect",
    "tbl_5_06_battery_wacc",
]

def all_tables():
    for name in TABLE_MODULES:
        yield import_module(f"tables.{name}")
