#!/usr/bin/env python3
"""
verify_scenarios.py — print the PyPSA-Earth scenario matrix.

Usage:
    python3 scripts/verify_scenarios.py scripts/scenarios/
    python3 scripts/verify_scenarios.py scripts/scenarios/ --csv out.csv
"""

import argparse
import csv
import glob
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def find_rate_for_carrier(costs, carrier):
    groups = costs.get("discountrate_groups", {}) or {}
    for _, gval in groups.items():
        if isinstance(gval, dict):
            if carrier in (gval.get("carriers") or []):
                return gval.get("rate")
    return None


def detect_ndc(cfg):
    co2 = cfg.get("co2")
    if isinstance(co2, dict) and co2.get("limit") is not None:
        return "Y", co2["limit"]
    return "N", None


def detect_retrieve_cost_data(cfg):
    return (cfg.get("enable") or {}).get("retrieve_cost_data", "MISSING")


def detect_gas_price(run_name):
    if "gas_600" in run_name:
        return "$6.00 (costs_gas_600.csv)"
    return "$3.39 (costs.csv)"


def summarize(path):
    cfg = load_yaml(path)
    name = Path(path).stem
    costs = cfg.get("costs") or {}
    run_name = (cfg.get("run") or {}).get("name", name)

    solar_wacc   = find_rate_for_carrier(costs, "solar")
    gas_wacc     = find_rate_for_carrier(costs, "OCGT")
    battery_wacc = find_rate_for_carrier(costs, "battery storage")
    hydro_wacc   = find_rate_for_carrier(costs, "hydro")

    ndc, ndc_limit = detect_ndc(cfg)
    rcd = detect_retrieve_cost_data(cfg)
    gas_price = detect_gas_price(run_name)

    notes = []
    if rcd is True:
        notes.append("!! retrieve_cost_data=true")
    if rcd == "MISSING":
        notes.append("!! retrieve_cost_data missing")
    if solar_wacc is None:
        notes.append("!! no solar WACC")
    if gas_wacc is None:
        notes.append("!! no gas WACC")
    if battery_wacc is None:
        notes.append("!! no battery WACC")
    if "marginal_cost" in costs:
        notes.append("!! marginal_cost present (should be removed)")
    if ndc_limit is not None:
        notes.append(f"co2_limit={ndc_limit}")

    f = lambda v: f"{v:.4f}" if isinstance(v, (int, float)) else "—"
    return {
        "name": name,
        "solar_wacc": f(solar_wacc),
        "gas_wacc": f(gas_wacc),
        "battery_wacc": f(battery_wacc),
        "hydro_wacc": f(hydro_wacc),
        "gas_price": gas_price,
        "ndc": ndc,
        "retrieve_cost_data": str(rcd),
        "notes": "; ".join(notes),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios_dir", nargs="?", default="scripts/scenarios")
    ap.add_argument("--csv", default=None, help="also write the table to CSV")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.scenarios_dir, "*.yaml")))
    if not files:
        sys.exit(f"No .yaml files in {args.scenarios_dir!r} (CWD={os.getcwd()})")

    rows = [summarize(f) for f in files]

    cols = ["name", "solar_wacc", "gas_wacc", "battery_wacc", "hydro_wacc",
            "gas_price", "ndc", "retrieve_cost_data", "notes"]
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    fmt = lambda r: " | ".join(str(r[c]).ljust(widths[c]) for c in cols)

    print(f"\nScenario matrix ({len(rows)} configs in {args.scenarios_dir}/)\n")
    print(fmt({c: c for c in cols}))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(fmt(r))

    problems = [r for r in rows if "!!" in r["notes"]]
    print()
    if problems:
        print(f"{len(problems)} config(s) flagged:\n")
        for r in problems:
            print(f"  - {r['name']}: {r['notes']}")
    else:
        print("No flagged issues. ✅")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()