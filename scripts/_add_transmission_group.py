#!/usr/bin/env python3
"""Add a transmission group to discountrate_groups in all scenario YAMLs.

Lines currently fall through to the top-level `discountrate` (solar WACC),
which makes line capex vary across WACC sweeps. This pins transmission
WACC at 14.68% across all scenarios.
"""
from pathlib import Path
import yaml

SCEN = Path("scripts/scenarios")
TRANSMISSION_CARRIERS = [
    "HVAC overhead",
    "HVDC overhead",
    "HVDC submarine",
    "HVDC inverter pair",
]
TRANSMISSION_RATE = 0.1468

for f in sorted(SCEN.glob("*.yaml")):
    cfg = yaml.safe_load(f.read_text()) or {}
    costs = cfg.get("costs")
    if not costs or "discountrate_groups" not in costs:
        print(f"skip (no discountrate_groups): {f.name}")
        continue
    groups = costs["discountrate_groups"]
    if "transmission" in groups:
        print(f"already has transmission group: {f.name}")
        continue
    groups["transmission"] = {
        "rate": TRANSMISSION_RATE,
        "carriers": TRANSMISSION_CARRIERS,
    }
    f.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"updated: {f.name}")