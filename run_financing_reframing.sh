#!/bin/bash
# Financing Reframing — Paper 1, PhD thesis
# 20 runs: 12 WACC sweep + 3 export parity ($6.00) + 3 NDC + 2 baselines
# All unconstrained except Phase 3 (NDC)
# Corrected gas marginal costs: OCGT 6.18, CCGT 4.15 EUR/MWh ($3.39 baseline)
#                              OCGT 8.04, CCGT 5.14 EUR/MWh ($6.00 export parity)
# Corrected discountrate_groups: solar/onwind/hydro/battery/CCGT/OCGT
cd /Users/fowfloi/Documents/pypsa-earth

CORES=4
LOGDIR="logs/financing_reframing_v2"
mkdir -p "$LOGDIR"

MASTER="$LOGDIR/master_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$MASTER") 2>&1

echo "########################################################"
echo "# Financing Reframing — 20-run batch (v2)"
echo "# Started: $(date)"
echo "# Cores:   $CORES"
echo "# Log:     $MASTER"
echo "########################################################"

run_one() {
    local cfgfile=$1
    local runname=$2
    if [ ! -f "$cfgfile" ]; then
        echo "SKIP $runname — config not found: $cfgfile"
        return
    fi
    echo ""
    echo "=============================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] START $runname"
    echo "  config: $cfgfile"
    echo "=============================================="
    rm -rf "resources/${runname}" "results/${runname}"
    snakemake --cores "$CORES" --configfile "$cfgfile" -- solve_all_networks \
        > "$LOGDIR/${runname}.log" 2>&1
    local rc=$?
    if [ $rc -eq 0 ]; then
        echo "[$(date '+%H:%M:%S')] OK   $runname"
    else
        echo "[$(date '+%H:%M:%S')] FAIL $runname (exit $rc) — see $LOGDIR/${runname}.log"
    fi
}

echo ""
echo "=== PHASE 1: WACC sweep, unconstrained ==="
for tag in 0700 0900 1100 1200 1300 1379 1468 1600 1800 2000 2300 2700; do
    run_one "configs/config.nigeria.2030_wacc_${tag}.yaml" \
            "nigeria_2030_wacc_${tag}"
done

echo ""
echo "=== PHASE 2: Export-parity gas ($6.00), unconstrained ==="
for tag in 0700 1379 2000; do
    run_one "configs/config.nigeria.2030_wacc_${tag}_gas_600.yaml" \
            "nigeria_2030_wacc_${tag}_gas_600"
done

echo ""
echo "=== PHASE 3: NDC constraint ==="
for tag in 1000 1379 2700; do
    run_one "configs/config.nigeria.2030_wacc_${tag}_ndc.yaml" \
            "nigeria_2030_wacc_${tag}_ndc"
done

echo ""
echo "=== PHASE 4: Baselines, unconstrained ==="
run_one "configs/cap_exp_2030_uniform_wacc.yaml" "cap_exp_2030_uniform_wacc"
run_one "configs/cap_exp_2030_split_wacc.yaml"   "cap_exp_2030_split_wacc"

echo ""
echo "########################################################"
echo "# ALL RUNS COMPLETE"
echo "# Finished: $(date)"
echo "# Master log: $MASTER"
echo "########################################################"

echo ""
echo "=== SUMMARY ==="
for f in "$LOGDIR"/nigeria_*.log "$LOGDIR"/cap_exp_*.log; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .log)
    if grep -q "FAIL" "$f" 2>/dev/null; then
        echo "FAIL  $name"
    elif [ -s "$f" ]; then
        echo "OK    $name"
    fi
done
