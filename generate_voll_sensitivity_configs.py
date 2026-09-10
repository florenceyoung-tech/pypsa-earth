"""
Generates configs for a VOLL sensitivity test: how much does the build and
the amount of unserved energy change as the value of lost load moves across
the range supported by Nigerian self-generation cost data?

Runs on top of B2 (Hatton differentiated WACC), since that is the financing
scenario your supervisor's question was raised against. Change BASE below
to cap_exp_2030.yaml if you want the sensitivity run against B1 instead.

Four points, drawn from the self-generation cost range discussed earlier:
  V1  0.13 EUR/kWh   CNG self-generation, the cheapest fuel-switched option
  V2  0.32 EUR/kWh   diesel, the dominant self-generation fuel (your B2 default)
  V3  0.55 EUR/kWh   petrol, smaller/backup generation
  V4  0.0001 EUR/kWh near-zero, the lower bound (see the earlier note on why
                      literal 0 disables the shedding mechanism entirely
                      rather than making it free)

Run once: python3 generate_voll_sensitivity_configs.py
"""

import re
from pathlib import Path

BASE = Path("configs/cap_exp_2030_split_wacc.yaml")
OUT_DIR = Path("configs")

VOLL_POINTS = {
    "V1_cng": "0.13",
    "V2_diesel": "0.32",
    "V3_petrol": "0.55",
    "V4_nearzero": "0.0001",
}

base_text = BASE.read_text()

name_pattern = re.compile(r'name: "cap_exp_2030_split_wacc"')
voll_pattern = re.compile(r'(load_shedding: )[0-9.]+')

assert len(name_pattern.findall(base_text)) == 1, "run.name line not found or not unique"
assert len(voll_pattern.findall(base_text)) == 1, "load_shedding line not found or not unique"

for scenario_id, voll in VOLL_POINTS.items():
    run_name = f"cap_exp_2030_voll_{scenario_id}"

    text = name_pattern.sub(f'name: "{run_name}"', base_text)
    text = voll_pattern.sub(rf'\g<1>{voll}', text)

    header = (
        f"# VOLL SENSITIVITY: {scenario_id}. load_shedding = {voll} EUR/kWh.\n"
        f"# WACC held at B2 (Hatton). Generated from cap_exp_2030_split_wacc.yaml\n"
        f"# by generate_voll_sensitivity_configs.py -- do not hand-edit.\n"
    )
    text = header + text

    out_path = OUT_DIR / f"cap_exp_2030_voll_{scenario_id}.yaml"
    out_path.write_text(text)
    print(f"wrote {out_path}  (VOLL = {voll} EUR/kWh)")

print(f"\n{len(VOLL_POINTS)} configs written. Verify one against the base:")
print(f"  diff configs/cap_exp_2030_split_wacc.yaml configs/cap_exp_2030_voll_V2_diesel.yaml")
