#!/bin/bash
cd /Users/fowfloi/Documents/pypsa-earth

if pgrep -f "run_final.sh" | grep -v "$$" > /dev/null; then
    echo "ERROR: another run_final.sh is already running. Aborting."
    exit 1
fi

CORES=4
mkdir -p logs/final

run() {
    local name="$1"
    echo "=== $name ==="
    snakemake --cores "$CORES" --configfile "configs/${name}.yaml" -- solve_all_networks \
        > "logs/final/${name}.log" 2>&1
    if [ $? -eq 0 ]; then echo "OK: $name"; else echo "FAIL: $name"; fi
}

for tag in 0700 0900 1100 1379 1800 2700; do
    run "config.nigeria.2030_wacc_${tag}"
done

for tag in 1000 1379 2700; do
    run "config.nigeria.2030_wacc_${tag}_ndc"
done

run "config.nigeria.2030_wacc_1379_gas_600"

echo "ALL RUNS COMPLETE"
