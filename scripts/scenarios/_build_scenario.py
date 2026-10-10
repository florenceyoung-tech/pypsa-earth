#!/usr/bin/env python3
"""
_build_scenarios.py

Rebuilds the PyPSA-Earth Nigeria 2030 scenario set.

- Backs up the existing scenarios/ to scenarios_archive_<timestamp>/
- Deletes obsolete config.nigeria.2030_* files
- Rewrites the two 2030 baselines (split WACC, uniform WACC)
- Creates config.nigeria.2030_B3_high_fin_2000.yaml
- Generates C1-C10, D1-D3, P2-P4, P1, P1D, S2a, S2b
- Leaves config.nigeria.2024.yaml untouched
- Writes data/costs_gas_600.csv (gas fuel row = 19.40 USD/MWh_th)

Marginal cost is NEVER written into the YAML. PyPSA computes it
from costs.csv:
    MC_OCGT = gas_fuel / eff_OCGT + VOM_OCGT
    MC_CCGT = gas_fuel / eff_CCGT + VOM_CCGT
At gas = 10.96 USD/MWh_th: OCGT = 34.36, CCGT = 25.42
At gas = 19.40 USD/MWh_th: OCGT = 57.17, CCGT = 41.34
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path.cwd()
SCEN = REPO / "scripts" / "scenarios"
DATA = REPO / "data"
COSTS_CSV = DATA / "costs.csv"
COSTS_600_CSV = DATA / "costs_gas_600.csv"

KEEP_ALWAYS = {
    "config.nigeria.2024.yaml",
    "cap_exp_2030_split_wacc.yaml",
    "cap_exp_2030_uniform_wacc.yaml",
}

# ---------------------------------------------------------------------------
# The template — single source of truth for all generated YAMLs
# ---------------------------------------------------------------------------
TEMPLATE_BODY = """
run:
  name: {run_name}
countries:
- NG
scenario:
  simpl: ['']
  ll: [copt]
  clusters: [10]
  opts: [1h]
snapshots:
  start: '2024-01-01'
  end: '2025-01-01'
  inclusive: left
enable:
  retrieve_databundle: false
  download_osm_data: true
  retrieve_cutout: false
  build_cutout: false
  retrieve_cost_data: false
  retrieve_databundle_sector: false
  download_global_buildings: false
  build_natura_raster: true
  progress_bar: true
atlite:
  nprocesses: 4
  cutouts:
    cutout-2024-era5:
      module: era5
      dx: 0.3
      dy: 0.3
      time: ['2024-01-01', '2025-01-01']
  default: cutout-2024-era5
renewable:
  onwind:
    cutout: auto
    resource:
      method: wind
      turbine: Vestas_V112_3MW
    capacity_per_sqkm: 3
    copernicus:
      grid_codes: [20, 30, 40, 60, 100, 111, 112, 113, 114, 115, 116, 121, 122, 123, 124, 125, 126]
      distance: 1000
      distance_grid_codes: [50]
    natura: true
    potential: simple
    clip_p_max_pu: 0.01
    extendable: true
  solar:
    cutout: auto
    resource:
      method: pv
      panel: CSi
      orientation: latitude_optimal
    capacity_per_sqkm: 4.6
    correction_factor: 1.0
    copernicus:
      grid_codes: [20, 30, 40, 50, 60, 90, 100]
    natura: true
    potential: simple
    clip_p_max_pu: 0.01
    extendable: true
  hydro:
    cutout: auto
    hydrobasins_level: 6
    resource:
      method: hydro
      hydrobasins: data/hydrobasins/hybas_world.shp
      flowspeed: 1.0
    carriers: [ror, hydro, PHS]
    hydro_max_hours: energy_capacity_totals_by_country
    hydro_max_hours_default: 6.0
    clip_min_inflow: 1.0
    extendable: false
    normalization:
      method: eia
      year: 2023
    multiplier: 1.268
    hydro_min_inflow_pu: 1.0
conventional:
  CCGT:
    p_max_pu: 0.306
  OCGT:
    p_max_pu: 0.217
clustering:
  exclude_carriers: [oil, gas, coal]
  remove_stubs: true
  p_threshold_drop_isolated: 100
base_network:
  min_voltage_rebase_voltage: 330000
load_options:
  source: demcast
  weather_year: 2024
  prediction_year: 2030
  scale: 2.074
electricity:
  base_voltage: 330.0
  voltages: [132.0, 330.0]
  renewable_carriers: [solar, onwind, hydro]
  conventional_carriers: [oil, OCGT, CCGT, biomass]
  extendable_carriers:
    Generator: [solar, onwind, OCGT, CCGT]
    StorageUnit: [battery]
    Store: []
  max_hours:
    battery: 6
  powerplants_filter: (DateOut >= 2030 or DateOut != DateOut) and (DateIn <= 2030 or DateIn != DateIn)
  custom_powerplants: replace
  estimate_renewable_capacities:
    stats: irena
    year: 2023
  conventional_efficiency:
    CCGT: 0.58
    OCGT: 0.41
lines:
  s_max_pu: 1.0
  custom_line_types: data/line_types.csv
  ac_types:
    330.0: ACSR Zebra 2-bundle 330.0
costs:
  year: 2030
  discountrate: [{solar_rate}]
  discountrate_groups:
    renewable:
      rate: {solar_rate}
      carriers: [solar, solar-utility, solar-rooftop, onwind]
    hydro:
      rate: {solar_rate}
      carriers: [hydro, ror, PHS]
    battery:
      rate: {battery_rate}
      carriers: [battery storage, battery inverter]
    fossil:
      rate: {gas_rate}
      carriers: [OCGT, CCGT]
solving:
  options:
    load_shedding: 1.0
  solver:
    name: gurobi
    options: gurobi-default
validation:
  interconnectors:
    enable: false
{co2_block}"""

NDC_BLOCK = """
co2:
  limit: 8800000.0
  base: 0.0
"""


def render(run_name, solar_rate, battery_rate, gas_rate, ndc=False):
    return TEMPLATE_BODY.format(
        run_name=run_name,
        solar_rate=f"{solar_rate:.4f}",
        battery_rate=f"{battery_rate:.4f}",
        gas_rate=f"{gas_rate:.4f}",
        co2_block=NDC_BLOCK if ndc else "",
    ).lstrip("\n")


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------
# (filename, run_name, solar_rate, battery_rate, gas_rate, ndc)
SCENARIOS = [
    # ---- Baselines (B) --------------------------------------------------
    ("cap_exp_2030_uniform_wacc.yaml",       "cap_exp_2030_uniform_wacc",
     0.10,   0.10,   0.10,   False),
    ("cap_exp_2030_split_wacc.yaml",         "cap_exp_2030_split_wacc",
     0.1379, 0.1379, 0.1468, False),
    ("config.nigeria.2030_B3_high_fin_2000.yaml", "config.nigeria.2030_B3_high_fin_2000",
     0.20,   0.20,   0.20,   False),

    # ---- WACC sweep (C) — gas WACC 14.68% -------------------------------
    ("config.nigeria.2030_C1_wacc_0700.yaml",  "config.nigeria.2030_C1_wacc_0700",
     0.07,   0.07,   0.1468, False),
    ("config.nigeria.2030_C2_wacc_0900.yaml",  "config.nigeria.2030_C2_wacc_0900",
     0.09,   0.09,   0.1468, False),
    ("config.nigeria.2030_C3_wacc_1100.yaml",  "config.nigeria.2030_C3_wacc_1100",
     0.11,   0.11,   0.1468, False),
    ("config.nigeria.2030_C4_wacc_1200.yaml",  "config.nigeria.2030_C4_wacc_1200",
     0.12,   0.12,   0.1468, False),
    ("config.nigeria.2030_C5_wacc_1300.yaml",  "config.nigeria.2030_C5_wacc_1300",
     0.13,   0.13,   0.1468, False),
    ("config.nigeria.2030_C6_wacc_1379.yaml",  "config.nigeria.2030_C6_wacc_1379",
     0.1379, 0.1379, 0.1468, False),
    ("config.nigeria.2030_C7_wacc_1468.yaml",  "config.nigeria.2030_C7_wacc_1468",
     0.1468, 0.1468, 0.1468, False),
    ("config.nigeria.2030_C8_wacc_1600.yaml",  "config.nigeria.2030_C8_wacc_1600",
     0.16,   0.16,   0.1468, False),
    ("config.nigeria.2030_C9_wacc_1800.yaml",  "config.nigeria.2030_C9_wacc_1800",
     0.18,   0.18,   0.1468, False),
    ("config.nigeria.2030_C10_wacc_2000.yaml", "config.nigeria.2030_C10_wacc_2000",
     0.20,   0.20,   0.1468, False),

    # ---- NDC (D) --------------------------------------------------------
    ("config.nigeria.2030_D1_wacc_1000_ndc.yaml", "config.nigeria.2030_D1_wacc_1000_ndc",
     0.10,   0.10,   0.10,   True),
    ("config.nigeria.2030_D2_wacc_1379_ndc.yaml", "config.nigeria.2030_D2_wacc_1379_ndc",
     0.1379, 0.1379, 0.1468, True),
    ("config.nigeria.2030_D3_wacc_2000_ndc.yaml", "config.nigeria.2030_D3_wacc_2000_ndc",
     0.20,   0.20,   0.20,   True),

    # ---- Policy de-risking (P-a) ---------------------------------------
    ("config.nigeria.2030_P2_wacc_1179.yaml", "config.nigeria.2030_P2_wacc_1179",
     0.1179, 0.1179, 0.1468, False),
    ("config.nigeria.2030_P3_wacc_0979.yaml", "config.nigeria.2030_P3_wacc_0979",
     0.0979, 0.0979, 0.1068, False),
    ("config.nigeria.2030_P4_wacc_0779.yaml", "config.nigeria.2030_P4_wacc_0779",
     0.0779, 0.0779, 0.1068, False),

    # ---- Gas pricing (P-b) — use costs_gas_600.csv ---------------------
    ("config.nigeria.2030_P1_wacc_1379_gas_600.yaml", "config.nigeria.2030_P1_wacc_1379_gas_600",
     0.1379, 0.1379, 0.1468, False),
    ("config.nigeria.2030_P1D_wacc_1379_gas_600_ndc.yaml", "config.nigeria.2030_P1D_wacc_1379_gas_600_ndc",
     0.1379, 0.1379, 0.1468, True),

    # ---- Sensitivity (S) -----------------------------------------------
    ("config.nigeria.2030_S2a_battery_1468.yaml", "config.nigeria.2030_S2a_battery_1468",
     0.1379, 0.1468, 0.1468, False),
    ("config.nigeria.2030_S2b_battery_1468_wacc11.yaml", "config.nigeria.2030_S2b_battery_1468_wacc11",
     0.11,   0.1468, 0.1468, False),
]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def backup_scenarios():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = REPO / f"scenarios_archive_{ts}"
    archive.mkdir(exist_ok=True)
    for f in SCEN.glob("*.yaml"):
        shutil.copy2(f, archive / f.name)
    print(f"[backup] copied {len(list(archive.glob('*.yaml')))} YAMLs -> {archive.name}/")
    return archive


def delete_obsolete():
    keep = {fname for fname, *_ in SCENARIOS} | KEEP_ALWAYS
    deleted = []
    for f in sorted(SCEN.glob("config.nigeria.2030_*.yaml")):
        if f.name not in keep:
            f.unlink()
            deleted.append(f.name)
    for f in sorted(SCEN.glob("config.nigeria.2025*.yaml")):
        # (only if such files exist — keep them; adjust if you want them gone)
        pass
    for f in sorted(SCEN.glob("cap_exp_2030_*.yaml")):
        if f.name not in keep:
            f.unlink()
            deleted.append(f.name)
    print(f"[delete] removed {len(deleted)} obsolete files")
    for name in deleted:
        print(f"         - {name}")


def write_scenarios():
    written = []
    for fname, run_name, s, b, g, ndc in SCENARIOS:
        body = render(run_name, s, b, g, ndc=ndc)
        (SCEN / fname).write_text(body)
        written.append(fname)
    print(f"[write] wrote {len(written)} scenario YAMLs")
    return written


def write_costs_gas_600():
    """
    Copy data/costs.csv to data/costs_gas_600.csv and scale the gas fuel row
    from 10.96 (=$3.39/MMBtu) to 19.40 (=$6.00/MMBtu).
    Ratio = 6.00 / 3.39.
    """
    if not COSTS_CSV.exists():
        print(f"[costs] WARNING: {COSTS_CSV} not found — skipping costs_gas_600.csv")
        return
    ratio = 6.00 / 3.39
    rows = []
    with COSTS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["technology"] == "gas" and row["parameter"] == "fuel":
                old = float(row["value"])
                new = round(old * ratio, 4)
                row = dict(row)
                row["value"] = f"{new}"
                row["further description"] = (
                    f"gas at $6.00/MMBtu (scaled from $3.39 by {ratio:.4f}); "
                    "HHV basis; see costs.csv for derivation"
                )
            rows.append(row)
    with COSTS_600_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[costs] wrote {COSTS_600_CSV.name} (gas fuel = 19.40 USD/MWh_th)")


def main():
    if not SCEN.is_dir():
        sys.exit(f"Run from repo root — {SCEN} not found")
    backup_scenarios()
    delete_obsolete()
    written = write_scenarios()
    write_costs_gas_600()

    print("\n=== Summary ===")
    print(f"Scenarios written: {len(written)}")
    print("Files kept untouched: config.nigeria.2024.yaml")
    print("\nNext steps:")
    print("  1. python verify_scenarios.py scenarios/")
    print("  2. For P1/P1D: point PyPSA at data/costs_gas_600.csv")
    print("     (symlink swap or config key, depending on your Snakefile)")
    print("  3. Review the two baselines and B3 before launching runs.")


if __name__ == "__main__":
    main()