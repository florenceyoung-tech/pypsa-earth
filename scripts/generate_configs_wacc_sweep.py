# generate_wacc_sweep_configs.py
import yaml
from pathlib import Path

WACC_POINTS = [
    0.07, 0.09, 0.11, 0.12, 0.13, 0.1379,
    0.1468, 0.16, 0.18, 0.20, 0.23, 0.27,
]

base_path = Path("configs/cap_exp_2030_split_wacc.yaml")
with open(base_path) as f:
    base = yaml.safe_load(f)

for wacc in WACC_POINTS:
    cfg = yaml.safe_load(yaml.safe_dump(base))  # deep copy
    tag = f"{int(round(wacc * 10000)):04d}"
    cfg["run"]["name"] = f"nigeria_2030_wacc_{tag}"
    cfg["costs"]["discountrate_groups"]["renewable"]["rate"] = wacc
    out = Path(f"configs/config.nigeria.2030_wacc_{tag}.yaml")
    with open(out, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    print(f"Wrote {out} with renewable rate = {wacc}")