#!/usr/bin/env python3
"""Add electricity.allow_retirement: true to all scenario YAMLs.

This enables the model to retire existing conventional capacity.
The actual enforcement happens in scripts/prepare_network.py.
"""
from pathlib import Path
import yaml

SCEN = Path("scripts/scenarios")

for f in sorted(SCEN.glob("*.yaml")):
    cfg = yaml.safe_load(f.read_text()) or {}
    if "electricity" not in cfg:
        print(f"skip (no electricity block): {f.name}")
        continue
    elec = cfg["electricity"]
    if "allow_retirement" in elec:
        print(f"already has flag: {f.name}")
        continue
    elec["allow_retirement"] = True
    f.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"updated: {f.name}")