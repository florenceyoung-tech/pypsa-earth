#!/usr/bin/env python3
"""Add electricity.split_existing: true to all 24 scenario YAMLs.

This enables the brownfield split in prepare_network.py so that existing
conventional capacity stays fixed and new capacity is built on top.
"""
from pathlib import Path
import yaml

SCEN = Path("scripts/scenarios")

for f in sorted(SCEN.glob("*.yaml")):
    cfg = yaml.safe_load(f.read_text()) or {}
    if "electricity" not in cfg:
        print(f"skip (no electricity block): {f.name}")
        continue
    if cfg["electricity"].get("split_existing") is True:
        print(f"already has flag: {f.name}")
        continue
    cfg["electricity"]["split_existing"] = True
    f.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"updated: {f.name}")