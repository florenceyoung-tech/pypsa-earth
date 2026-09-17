#!/bin/bash
# Nigeria 2030 supplementary rerun — corrected fuel prices, battery rates, combined instrument
CORES=4
mkdir -p logs/final

run() {
    local cfgfile=$1
    local runname=$2
    echo "=============================================="
    echo "[$(date '+%H:%M:%S')] $runname"
    echo "=============================================="
    snakemake --cores $CORES --configfile "$cfgfile" -- solve_all_networks > logs/final/${runname}.log 2>&1
    if [ $? -eq 0 ]; then
        echo "OK: $runname"
    else
        echo "FAIL: $runname"
    fi
}

# ---------------------------------------------------------------------------
# PHASE 1: Battery sensitivity (2 runs) — clear old results first
# ---------------------------------------------------------------------------
echo ""
echo "=== PHASE 1: BATTERY SENSITIVITY ==="
rm -rf resources/nigeria_2030_wacc_0900_battery_hatton resources/nigeria_2030_wacc_1100_battery_hatton
rm -rf results/nigeria_2030_wacc_0900_battery_hatton results/nigeria_2030_wacc_1100_battery_hatton

run configs/config.nigeria.2030_wacc_0900_battery_hatton.yaml nigeria_2030_wacc_0900_battery_hatton
run configs/config.nigeria.2030_wacc_1100_battery_hatton.yaml nigeria_2030_wacc_1100_battery_hatton

# ---------------------------------------------------------------------------
# PHASE 2: Gas pricing sensitivity (3 runs) — clear old results first
# ---------------------------------------------------------------------------
echo ""
echo "=== PHASE 2: GAS PRICING SENSITIVITY ==="
rm -rf resources/nigeria_2030_wacc_1379_gas_218 resources/nigeria_2030_wacc_1379_gas_400 resources/nigeria_2030_wacc_1379_gas_600
rm -rf results/nigeria_2030_wacc_1379_gas_218 results/nigeria_2030_wacc_1379_gas_400 results/nigeria_2030_wacc_1379_gas_600

run configs/config.nigeria.2030_wacc_1379_gas_218.yaml nigeria_2030_wacc_1379_gas_218
run configs/config.nigeria.2030_wacc_1379_gas_400.yaml nigeria_2030_wacc_1379_gas_400
run configs/config.nigeria.2030_wacc_1379_gas_600.yaml nigeria_2030_wacc_1379_gas_600

# ---------------------------------------------------------------------------
# PHASE 3: Combined instrument run (1 run) — renewable 7% + gas $4.50
# ---------------------------------------------------------------------------
echo ""
echo "=== PHASE 3: COMBINED INSTRUMENT ==="

# Generate the config from the base 7% NDC config
python - <<'PY'
import yaml
from pathlib import Path

base = Path("configs/config.nigeria.2030_wacc_0700_ndc.yaml")
out  = Path("configs/config.nigeria.2030_wacc_0700_gas_450_ndc.yaml")

with open(base) as f:
    cfg = yaml.safe_load(f)

cfg["run"]["name"] = "nigeria_2030_wacc_0700_gas_450_ndc"
cfg["costs"]["marginal_cost"]["OCGT"] = 5.42
cfg["costs"]["marginal_cost"]["CCGT"] = 5.71

with open(out, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
print(f"Wrote {out}")
PY

rm -rf resources/nigeria_2030_wacc_0700_gas_450_ndc
rm -rf results/nigeria_2030_wacc_0700_gas_450_ndc
run configs/config.nigeria.2030_wacc_0700_gas_450_ndc.yaml nigeria_2030_wacc_0700_gas_450_ndc

echo ""
echo "=== ALL 6 RUNS COMPLETE ==="
