"""
Insert electricity.co2limit into all NDC configs.
Run once from the pypsa-earth root directory.
"""
import yaml
from pathlib import Path

CO2_LIMIT = 8_800_000   # 8.8 Mt grid-proxy NDC cap
CO2_BASE = 0.0

CONFIGS = (
    list(Path("configs").glob("config.nigeria.2030_wacc_*_ndc.yaml"))
    + [
        Path("configs/cap_exp_2030_NDC.yaml"),
        Path("configs/cap_exp_2030_split_wacc_NDC.yaml"),
    ]
)

for f in CONFIGS:
    with open(f) as fh:
        cfg = yaml.safe_load(fh) or {}

    if "electricity" not in cfg:
        cfg["electricity"] = {}

    cfg["electricity"]["co2limit"] = CO2_LIMIT
    cfg["electricity"]["co2base"] = CO2_BASE

    # Remove any stray co2.limit key from previous attempts
    if "co2" in cfg and isinstance(cfg["co2"], dict):
        cfg["co2"].pop("limit", None)
        cfg["co2"].pop("enable", None)
        if not cfg["co2"]:
            del cfg["co2"]

    with open(f, "w") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)

    print(f"Updated: {f}")