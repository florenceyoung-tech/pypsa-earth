"""
Generates configs/cap_exp_2030_C1.yaml through C9.yaml, the WACC sweep
(solar/wind WACC 7% to 15% in 1pp steps, gas fixed at Hatton's 14.68%),
per Chapter 5, Table 5.1 of the scenario framework.

Starts from cap_exp_2030_split_wacc.yaml (B2) and edits only the run name
and the renewable discount rate, using targeted string replacement so all
existing comments and structure are preserved -- the same principle used
to build B2 from A.

Run once: python3 generate_wacc_sweep_configs.py
"""

import re
from pathlib import Path

BASE = Path("configs/cap_exp_2030_split_wacc.yaml")
OUT_DIR = Path("configs")

# solar/wind WACC sweep, 7% to 15% in 1pp steps. C1 = 7%, ..., C9 = 15%.
SWEEP = {f"C{i+1}": rate for i, rate in enumerate(range(7, 16))}

# gas WACC held fixed at Hatton's estimate throughout the sweep.
FOSSIL_RATE = "0.1468"

base_text = BASE.read_text()

# Sanity check: confirm the two lines we're about to target exist exactly once,
# so a change in the base file doesn't silently mis-target a replacement.
name_pattern = re.compile(r'name: "cap_exp_2030_split_wacc"')
renewable_rate_pattern = re.compile(r'(renewable:\s*\n\s*rate: )0\.\d+')

assert len(name_pattern.findall(base_text)) == 1, "run.name line not found or not unique"
assert len(renewable_rate_pattern.findall(base_text)) == 1, "renewable rate line not found or not unique"

for scenario_id, wacc_pct in SWEEP.items():
    rate = f"{wacc_pct / 100:.2f}"
    run_name = f"cap_exp_2030_{scenario_id}"

    text = name_pattern.sub(f'name: "{run_name}"', base_text)
    text = renewable_rate_pattern.sub(rf'\g<1>{rate}', text)

    # Add a marker comment at the top so each file states its place in the sweep.
    header = (
        f"# WACC SWEEP: {scenario_id}. Solar/wind WACC = {wacc_pct}%, "
        f"gas WACC fixed at {float(FOSSIL_RATE)*100:.2f}% (Hatton).\n"
        f"# Generated from cap_exp_2030_split_wacc.yaml by "
        f"generate_wacc_sweep_configs.py -- do not hand-edit, regenerate instead.\n"
    )
    text = header + text

    out_path = OUT_DIR / f"cap_exp_2030_{scenario_id}.yaml"
    out_path.write_text(text)
    print(f"wrote {out_path}  (solar/wind {wacc_pct}%, gas {float(FOSSIL_RATE)*100:.2f}%)")

print(f"\n{len(SWEEP)} configs written. Verify one against the base before running the sweep:")
print(f"  diff configs/cap_exp_2030_split_wacc.yaml configs/cap_exp_2030_C5.yaml")
