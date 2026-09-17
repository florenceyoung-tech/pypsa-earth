#!/bin/bash
CORES=4
TAGS="0700 0900 1100 1200 1300 1379 1468 1600 1800 2000 2300 2700"
mkdir -p logs/sweep

run_one() {
  local cfg="$1"
  local name=$(basename "$cfg" .yaml)
  echo "=== $name ==="
  snakemake --cores $CORES --configfile "$cfg" -- solve_all_networks \
    > "logs/sweep/${name}.log" 2>&1
  if [ $? -eq 0 ]; then echo "OK: $name"; else echo "FAIL: $name"; fi
}

for t in $TAGS; do
  run_one "configs/config.nigeria.2030_wacc_${t}.yaml"
  run_one "configs/config.nigeria.2030_wacc_${t}_ndc.yaml"
done

run_one "configs/cap_exp_2030.yaml"
run_one "configs/cap_exp_2030_NDC.yaml"
run_one "configs/cap_exp_2030_split_wacc.yaml"
run_one "configs/cap_exp_2030_split_wacc_NDC.yaml"

echo "SWEEP DONE"
