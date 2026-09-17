"""
Generate 12 NDC-constrained sweep config files from the
unconstrained versions by adding a CO2 limit.
"""
import yaml
from pathlib import Path

WACC_POINTS = [0.07, 0.09, 0.11, 0.12, 0.13, 0.1379,
               0.1468, 0.16, 0.18, 0.20, 0.23, 0.27]

CONFIG_DIR = Path("configs")
CO2_LIMIT = 57_000_000   # tonnes CO2/yr; NDC 3.0 national power sector

for wacc in WACC_POINTS:
    tag = f"{int(round(wacc * 10000)):04d}"
    src = CONFIG_DIR / f"config.nigeria.2030_wacc_{tag}.yaml"
    dst = CONFIG_DIR / f"config.nigeria.2030_wacc_{tag}_ndc.yaml"

    if not src.exists():
        print(f"MISSING SOURCE: {src}")
        continue

    with open(src) as f:
        cfg = yaml.safe_load(f)

    # Rename the run
    cfg["run"]["name"] = f"nigeria_2030_wacc_{tag}_ndc"

    # Add the CO2 constraint
    if "electricity" not in cfg:
        cfg["electricity"] = {}
    cfg["electricity"]["co2limit"] = CO2_LIMIT

    # Ensure load shedding is the 2030 policy value
    if "solving" not in cfg:
        cfg["solving"] = {}
    if "options" not in cfg["solving"]:
        cfg["solving"]["options"] = {}
    cfg["solving"]["options"]["load_shedding"] = 1.0

    with open(dst, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    print(f"Wrote {dst}")