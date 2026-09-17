#!/bin/bash
CORES=4
mkdir -p logs/final
LOG=logs/final_master.log

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a $LOG; }

run() {
    local name=$1
    log "START: $name"
    snakemake --cores $CORES --configfile configs/${name}.yaml -- solve_all_networks > logs/final/${name}.log 2>&1
    if [ $? -eq 0 ]; then log "OK:    $name"; else log "FAIL:  $name"; fi
}

# Phase 1 - baselines
log "=== PHASE 1: BASELINES ==="
run cap_exp_2030
run cap_exp_2030_uniform_WACC_NDC
run cap_exp_2030_split_wacc
run cap_exp_2030_split_wacc_NDC

# Phase 2 - core sweep
log "=== PHASE 2: CORE SWEEP ==="
for t in 0700 0900 1100 1200 1300 1379 1468 1600 1800 2000 2300 2700; do
    run config.nigeria.2030_wacc_${t}
    run config.nigeria.2030_wacc_${t}_ndc
done

# Phase 3 - battery sensitivity (needs configs generated first)
log "=== PHASE 3: BATTERY SENSITIVITY ==="
for t in 0900 1100; do
    run config.nigeria.2030_wacc_${t}_battery_hatton
done

# Phase 4 - gas price sensitivity (needs configs generated first)
log "=== PHASE 4: GAS PRICE SENSITIVITY ==="
for cfg in config.nigeria.2030_wacc_1379_gas_218 config.nigeria.2030_wacc_1379_gas_400 config.nigeria.2030_wacc_1379_gas_600; do
    run $cfg
done

log "=== ALL RUNS COMPLETE ==="
