#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
SCEN_DIR="scripts/scenarios"
COSTS_LINK="data/costs.csv"
COSTS_339="costs_gas_339.csv"
COSTS_600="costs_gas_600.csv"
TARGET="solve_all_networks"

SCENARIOS=(
  "config.nigeria.2030_C8_5_wacc_1700.yaml|339"
  "config.nigeria.2030_C9_wacc_1800.yaml|339"
  "config.nigeria.2030_C10_wacc_2000.yaml|339"
  "config.nigeria.2030_D1_wacc_1000_ndc.yaml|339"
  "config.nigeria.2030_D2_wacc_1379_ndc.yaml|339"
  "config.nigeria.2030_D3_wacc_2000_ndc.yaml|339"
  "config.nigeria.2030_P4_wacc_0779.yaml|339"
  "config.nigeria.2030_P3_wacc_0979.yaml|339"
  "config.nigeria.2030_P2_wacc_1179.yaml|339"
  "config.nigeria.2030_P1_wacc_1379_gas_600.yaml|600"
  "config.nigeria.2030_P1D_wacc_1379_gas_600_ndc.yaml|600"
  "config.nigeria.2030_S2a_battery_1468.yaml|339"
  "config.nigeria.2030_S2b_battery_1468_wacc11.yaml|339"
)

swap_costs () {
  local variant="$1" target
  case "$variant" in
    339) target="$COSTS_339" ;;
    600) target="$COSTS_600" ;;
    *) echo "!! unknown costs variant: $variant" >&2; exit 1 ;;
  esac
  ln -sf "$target" "$COSTS_LINK"
  touch -h "$COSTS_LINK"
}

CURRENT_VARIANT=""
mkdir -p logs/sweep_resume
for entry in "${SCENARIOS[@]}"; do
  scen="${entry%%|*}"; variant="${entry##*|}"
  scen_path="$SCEN_DIR/$scen"

  if [[ "$variant" != "$CURRENT_VARIANT" ]]; then
    echo "=== Switching costs to variant: $variant ==="
    swap_costs "$variant"
    CURRENT_VARIANT="$variant"
  fi

  if [[ -d .snakemake/locks ]] || [[ -f .snakemake/lock ]]; then
    if ! pgrep -f "snakemake" >/dev/null 2>&1; then
      snakemake --unlock -c 1 >/dev/null 2>&1 || true
    fi
  fi

  log="logs/sweep_resume/${scen%.yaml}.log"
  echo "=== $scen (costs=$variant) ==="
  if snakemake -call "$TARGET" --configfile "$scen_path" \
       --rerun-incomplete --latency-wait 60 > "$log" 2>&1; then
    echo "  OK: $scen"
  else
    echo "  FAILED: $scen (see $log)"
    exit 1
  fi
done

swap_costs 339
echo "Done."
