#!/usr/bin/env python3
"""Run revised scenarios sequentially, without symlink swaps or automatic unlocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def merge(base, overlay):
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def preflight(cfg):
    from process_cost_data import load_costs
    path = ROOT / cfg["costs"]["input_file"]
    if not path.is_file():
        raise FileNotFoundError(f"Missing raw costs file: {path}. Supply your actual source CSV with --cost-file when building scenarios.")
    cost_cfg = cfg["costs"]
    costs = load_costs(path, cost_cfg, cfg["electricity"]["max_hours"], Nyears=1.0)
    required = {"solar", "onwind", "CCGT", "OCGT", "battery", "HVAC overhead"}
    for tech in required:
        if tech not in costs.index or not np.isfinite(costs.at[tech, "capital_cost"]) or costs.at[tech, "capital_cost"] <= 0:
            raise ValueError(f"Missing/nonpositive annual investment cost for {tech}")
    for tech in ("CCGT", "OCGT"):
        expected = costs.at["gas", "fuel"] / costs.at[tech, "efficiency"] + costs.at[tech, "VOM"]
        if not np.isclose(expected, costs.at[tech, "marginal_cost"]):
            raise ValueError(f"{tech} marginal-cost override hides fuel/efficiency assumptions")
    checks = costs.loc[sorted(required), ["discount rate", "capital_cost", "marginal_cost"]].astype(object)
    checks = checks.where(pd.notna(checks), None)
    return {"price_year": cost_cfg["price_year"], "currency": cost_cfg["output_currency"],
            "gas_fuel_usd_per_mwh": float(costs.at["gas", "fuel"]),
            "raw_costs_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "raw_costs": str(path.relative_to(ROOT)),
            "processed_checks": checks.to_dict("index")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", nargs="+", help="Codes such as B2 D2 C01; default: all")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    manifest_path = ROOT / "configs/nigeria_study/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if args.scenarios:
        unknown = set(args.scenarios)-{row["scenario"] for row in manifest}
        if unknown:
            parser.error(f"Unknown scenarios: {sorted(unknown)}")
        manifest = [row for row in manifest if row["scenario"] in args.scenarios]
    logdir = ROOT / "logs/nigeria_consistent"
    logdir.mkdir(parents=True, exist_ok=True)
    # Validate ALL selected inputs before starting any expensive run.
    for row in manifest:
        path = ROOT / row["config"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["config_sha256"]:
            raise ValueError(f"{path} changed since generation. Edit the builder and regenerate, so the manifest remains consistent.")
        cfg = merge(yaml.safe_load((ROOT / "config.default.yaml").read_text()), yaml.safe_load(path.read_text()))
        check = preflight(cfg)
        check.update(config_sha256=row["config_sha256"], scenario=row["scenario"])
        (logdir / (row["scenario"]+"_inputs.json")).write_text(json.dumps(check, indent=2))
    if args.preflight_only:
        print("Input checks passed. No networks were run.")
        return
    for row in manifest:
        cmd = ["snakemake", "--cores", str(args.cores), "solve_all_networks", "--configfile", row["config"], "--rerun-incomplete", "--latency-wait", "60"]
        if args.dry_run:
            cmd.append("--dry-run")
        print("Running:", " ".join(cmd), flush=True)
        log = logdir / (row["scenario"] + ("_dryrun.log" if args.dry_run else ".log"))
        with log.open("w") as stream:
            process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
            code = process.wait()
        if code:
            sys.exit(f"Stopped at {row['scenario']}; inspect {log}. Other results are preserved.")
        if not args.dry_run:
            import pypsa
            sys.path.insert(0, str(ROOT / "analysis"))
            from nigeria_results import extract_metrics, validate_metadata
            network = pypsa.Network(ROOT / row["network"])
            current = yaml.safe_load((ROOT / row["config"]).read_text())
            validate_metadata(network, current)
            if current["nigeria_study"].get("preserve_existing_renewables"):
                stock = network.generators.query("carrier in ['solar', 'onwind', 'ror'] and p_nom > 0")
                if (stock.p_nom_opt < stock.p_nom - 1e-4).any():
                    sys.exit("Existing renewable stock was reduced; stopped before the next scenario")
            metrics = extract_metrics(network)
            (logdir / (row["scenario"] + "_results.json")).write_text(json.dumps(metrics, indent=2))
            print(f"CHECKED {row['scenario']}: served={metrics['served_twh']:.6f} TWh; CO2={metrics['emissions_mt']:.4f} Mt; cost residual=${metrics['objective_residual_usd']:.4f}", flush=True)
            if metrics["unserved_share"] > .001:
                print("REVIEW: unmet demand exceeds 0.1%; inspect this scenario before interpreting policy results", flush=True)


if __name__ == "__main__":
    main()
