#!/usr/bin/env python3
"""
_fix_co2_disable.py

Adds an explicit co2 disable block to all NON-NDC Nigeria 2030 scenario YAMLs.

Why: config.default.yaml sets co2.limit = 7.75e+7 (European default).
Because CLI --configfile extends rather than replaces config.default.yaml,
any scenario that omits the co2: block silently inherits the 77.5 Mt cap.

Setting co2.limit: null makes the Snakefile guard
    if config["co2"].get("limit"):
falsy, so the add_co2_constraint rule does not fire at all for these
scenarios.

NDC scenarios (D1, D2, D3, P1D) are NOT touched.
"""

from pathlib import Path
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

SCEN = Path("scripts/scenarios")

NON_NDC = [
    "cap_exp_2030_uniform_wacc.yaml",
    "cap_exp_2030_split_wacc.yaml",
    "config.nigeria.2030_B3_high_fin_2000.yaml",
    "config.nigeria.2030_C1_wacc_0700.yaml",
    "config.nigeria.2030_C2_wacc_0900.yaml",
    "config.nigeria.2030_C3_wacc_1100.yaml",
    "config.nigeria.2030_C4_wacc_1200.yaml",
    "config.nigeria.2030_C5_wacc_1300.yaml",
    "config.nigeria.2030_C6_wacc_1379.yaml",
    "config.nigeria.2030_C7_wacc_1468.yaml",
    "config.nigeria.2030_C8_wacc_1600.yaml",
    "config.nigeria.2030_C9_wacc_1800.yaml",
    "config.nigeria.2030_C10_wacc_2000.yaml",
    "config.nigeria.2030_P1_wacc_1379_gas_600.yaml",
    "config.nigeria.2030_P2_wacc_1179.yaml",
    "config.nigeria.2030_P3_wacc_0979.yaml",
    "config.nigeria.2030_P4_wacc_0779.yaml",
    "config.nigeria.2030_S2a_battery_1468.yaml",
    "config.nigeria.2030_S2b_battery_1468_wacc11.yaml",
]

NDC = [
    "config.nigeria.2030_D1_wacc_1000_ndc.yaml",
    "config.nigeria.2030_D2_wacc_1379_ndc.yaml",
    "config.nigeria.2030_D3_wacc_2000_ndc.yaml",
    "config.nigeria.2030_P1D_wacc_1379_gas_600_ndc.yaml",
]

DISABLE_BLOCK = (
    "\n"
    "# Explicitly disable the CO2 cap. Without this block, this scenario\n"
    "# inherits co2.limit from config.default.yaml (7.75e+7 tCO2/yr) and the\n"
    "# add_co2_constraint rule fires with the European default.\n"
    "# null makes `if config['co2'].get('limit'):` falsy in the Snakefile.\n"
    "co2:\n"
    "  limit: null\n"
    "  base: 0.0\n"
)


def has_co2_block(path):
    cfg = yaml.safe_load(path.read_text()) or {}
    return "co2" in cfg


def main():
    changed, skipped = [], []
    for name in NON_NDC:
        p = SCEN / name
        if not p.exists():
            print(f"  !! MISSING: {name}")
            continue
        if has_co2_block(p):
            skipped.append(name)
            continue
        text = p.read_text().rstrip("\n") + "\n" + DISABLE_BLOCK
        p.write_text(text)
        changed.append(name)

    for name in NDC:
        p = SCEN / name
        if not p.exists():
            print(f"  !! MISSING (NDC): {name}")
            continue
        if not has_co2_block(p):
            print(f"  !! WARNING: NDC file has no co2 block: {name}")

    print(f"\nAdded disable block to {len(changed)} non-NDC scenarios.")
    for n in changed:
        print(f"  + {n}")
    if skipped:
        print(f"\nSkipped (already had co2 block): {len(skipped)}")
        for n in skipped:
            print(f"  = {n}")


if __name__ == "__main__":
    main()