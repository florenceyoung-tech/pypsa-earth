#!/usr/bin/env python3
"""Build a separate, reproducible scenario set; never replace the legacy runs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml
from nigeria_consistency import real_rate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs/nigeria_study"
MWH_PER_MMBTU = 0.29307107


def scenarios():
    # code, group, renewable/battery/gas NOMINAL rates, gas USD/MMBtu, CO2 cap
    rows = [("B1", "baseline", .10, .10, .10, 3.39, None),
            ("B2", "baseline", .1379, .1379, .1468, 3.39, None),
            ("B3", "baseline", .20, .20, .20, 3.39, None)]
    for i, r in enumerate([.07, .09, .11, .12, .13, .1379, .1468, .16, .17, .18, .20], 1):
        rows.append((f"C{i:02}", "sweep", r, r, .1468, 3.39, None))
    rows += [("D1", "cap", .10, .10, .10, 3.39, 8.8e6),
             ("D2", "cap", .1379, .1379, .1468, 3.39, 8.8e6),
             ("D3", "cap", .20, .20, .20, 3.39, 8.8e6),
             ("P1", "gas", .1379, .1379, .1468, 6., None),
             ("P1D", "gas", .1379, .1379, .1468, 6., 8.8e6),
             ("P2", "policy", .1179, .1179, .1468, 3.39, None),
             ("P3", "policy", .0979, .0979, .1068, 3.39, None),
             ("P4", "policy", .0779, .0779, .1068, 3.39, None),
             ("S2a", "battery", .1379, .1468, .1468, 3.39, None),
             ("S2b", "battery", .11, .1468, .1468, 3.39, None),
             ("S_nominal", "sensitivity", .1379, .1379, .1468, 3.39, None),
             ("S_gas85", "sensitivity", .1379, .1379, .1468, 3.39, None),
             ("S_inflation4", "sensitivity", .1379, .1379, .1468, 3.39, None)]
    return rows


def make_config(template, row, inflation=.02, cost_file="data/nigeria_study/costs_source.csv"):
    code, group, renewable, battery, gas, price, cap = row
    cfg = copy.deepcopy(template)
    pi = .04 if code == "S_inflation4" else inflation
    rate = (lambda x: x) if code == "S_nominal" else (lambda x: real_rate(x, pi))
    cfg["run"]["name"] = f"nigeria_consistent_{code}"
    cfg["co2"] = {"limit": cap, "base": 0.0}
    cfg["costs"].update(
        input_file=cost_file, output_currency="USD", price_year=2024,
        exchange_rates={"USD": 1.0, "EUR": 1.0824}, reference_year_hours=8760,
        price_year_factors={"EUR": {2013: 126.08 / 99.39}},
        price_year_factor_source="Eurostat prc_hicp_aind; EA20 CP00 INX_A_AVG; 2013=99.39, 2024=126.08; general-price proxy",
        included_technologies=["onwind", "solar", "solar-utility", "hydro", "ror", "PHS", "OCGT", "CCGT", "gas", "oil", "biomass", "coal", "battery inverter", "battery storage", "HVAC overhead", "HVDC overhead", "HVDC submarine", "HVDC inverter pair"],
        rooftop_share=0.0,
        # Transmission and unlisted technologies do NOT track renewable WACC.
        discountrate=[rate(.10)], efficiency={"CCGT": .53, "OCGT": .37},
        # The source CSV ALREADY expresses the 2026 quote of $3.39/MMBtu
        # as 10.96 real-2024 USD/MWh_fuel. Preserve that baseline and scale
        # the $6 quote on the same price basis; do not deflate it twice.
        fuel={"gas": 10.96 * price / 3.39},
    )
    for key, r in (("renewable", renewable), ("hydro", renewable), ("battery", battery), ("fossil", gas)):
        cfg["costs"]["discountrate_groups"][key]["rate"] = rate(r)
    cfg["costs"]["discountrate_groups"]["renewable"]["carriers"] = ["solar", "solar-utility", "onwind"]
    cfg["electricity"].pop("conventional_efficiency", None)  # unused by this code
    # Preserve the author's later local decisions: fixed transmission nominal
    # rate and a USD 10,000/MWh unmet-demand penalty in the revised USD model.
    cfg["costs"]["discountrate_groups"]["transmission"] = {
        "rate": rate(.1468),
        "carriers": ["HVAC overhead", "HVDC overhead", "HVDC submarine", "HVDC inverter pair"],
    }
    cfg["electricity"].pop("allow_retirement", None)  # unused/inconsistent with fixed stock
    cfg["electricity"]["split_existing"] = True
    cfg["solving"]["options"]["load_shedding"] = 10.0
    cfg["load_options"]["scale"] = 1.0  # exact target imposed after clustering
    cfg["solving"]["options"]["noisy_costs"] = False
    cfg["nigeria_study"] = {
        "enabled": True, "scenario": code, "group": group,
        "inflation_assumption": pi, "rate_basis": "nominal_stress" if code == "S_nominal" else "real",
        "nominal_renewable_wacc": renewable, "nominal_battery_wacc": battery,
        "nominal_gas_wacc": gas, "gas_usd_per_mmbtu": price,
        "gas_quote_price_year": 2026, "gas_real_2024_usd_per_mwh": 10.96 * price / 3.39,
        "preserve_existing_renewables": True, "annual_demand_twh": 78.0, "max_excluded_load_share": .10,
        "existing_gas_derating": {"CCGT": .306, "OCGT": .217},
        "new_gas_availability": .85 if code == "S_gas85" else 1.0,
        "boundary": "largest_connected_component_rescaled_to_national_demand",
        "co2_cap_basis": "analytical allocation; 2018 grid baseline 12.4 Mt remains to be sourced",
    }
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cost-file", default="data/nigeria_study/costs_source.csv")
    parser.add_argument("--inflation", type=float, default=.02)
    args = parser.parse_args()
    template = yaml.safe_load((ROOT / "scripts/scenarios/cap_exp_2030_split_wacc.yaml").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for row in scenarios():
        cfg = make_config(template, row, args.inflation, args.cost_file)
        path = OUT / f"{row[0]}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        manifest.append({"scenario": row[0], "group": row[1], "config": str(path.relative_to(ROOT)),
                         "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "run_name": cfg["run"]["name"],
                         "network": f"results/{cfg['run']['name']}/networks/elec_s_10_ec_lcopt_1h.nc"})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} separate scenarios to {OUT}")


if __name__ == "__main__":
    main()
