#!/bin/bash
CORES=4
TAGS="0700 0900 1100 1200 1300 1379 1468 1600 1800 2000 2300 2700"
mkdir -p logs/sweep

for t in $TAGS; do
  echo "=== NDC $t ==="
  snakemake --cores $CORES \
    --configfile configs/config.nigeria.2030_wacc_${t}_ndc.yaml \
    -- solve_all_networks > logs/sweep/wacc_${t}_ndc.log 2>&1
  if [ $? -eq 0 ]; then echo "OK: wacc_${t}_ndc"; else echo "FAIL: wacc_${t}_ndc"; fi
done

echo "=== NDC baseline: uniform ==="
snakemake --cores $CORES --configfile configs/cap_exp_2030_NDC.yaml \
  -- solve_all_networks > logs/sweep/cap_exp_2030_NDC.log 2>&1
if [ $? -eq 0 ]; then echo "OK: cap_exp_2030_NDC"; else echo "FAIL: cap_exp_2030_NDC"; fi

echo "=== NDC baseline: differentiated ==="
snakemake --cores $CORES --configfile configs/cap_exp_2030_split_wacc_NDC.yaml \
  -- solve_all_networks > logs/sweep/cap_exp_2030_split_wacc_NDC.log 2>&1
if [ $? -eq 0 ]; then echo "OK: cap_exp_2030_split_wacc_NDC"; else echo "FAIL: cap_exp_2030_split_wacc_NDC"; fi

echo "NDC RERUN DONE"
