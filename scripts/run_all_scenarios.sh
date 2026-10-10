#!/usr/bin/env bash
# =============================================================================
# run_all_scenarios.sh
#
# Runs all 23 Nigeria 2030 scenarios via CLI --configfile.
# Costs file swaps between $3.39 and $6.00 gas via data/costs.csv symlink.
# Auto-unlocks the working directory before each run.
#
# Usage:
#   cd /Users/fowfloi/Documents/pypsa-earth
#   conda activate pypsa-earth
#   bash scripts/run_all_scenarios.sh 2>&1 | tee logs/sweep_$(date +%Y%m%d_%H%M%S).log
# =============================================================================

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SCEN_DIR="scripts/scenarios"
COSTS_LINK="data/costs.csv"
COSTS_339="costs_gas_339.csv"
COSTS_600="costs_gas_600.csv"
TARGET="solve_all_networks"

mkdir -p logs/sweep_$(date +%Y%m%d)

# -----------------------------------------------------------------------------
# 23 scenarios. Format: "<filename>|<costs_variant>"
# -----------------------------------------------------------------------------
SCENARIOS=(
  # Baselines (B) — $3.39
  "cap_exp_2030_uniform_wacc.yaml|339"
  "cap_exp_2030_split_wacc.yaml|339"
  "config.nigeria.2030_B3_high_fin_2000.yaml|339"

  # WACC sweep (C) — $3.39
  "config.nigeria.2030_C1_wacc_0700.yaml|339"
  "config.nigeria.2030_C2_wacc_0900.yaml|339"
  "config.nigeria.2030_C3_wacc_1100.yaml|339"
  "config.nigeria.2030_C4_wacc_1200.yaml|339"
  "config.nigeria.2030_C5_wacc_1300.yaml|339"
  "config.nigeria.2030_C6_wacc_1379.yaml|339"
  "config.nigeria.2030_C7_wacc_1468.yaml|339"
  "config.nigeria.2030_C8_wacc_1600.yaml|339"
  "config.nigeria.2030_C9_wacc_1800.yaml|339"
  "config.nigeria.2030_C10_wacc_2000.yaml|339"

  # NDC (D) — $3.39
  "config.nigeria.2030_D1_wacc_1000_ndc.yaml|339"
  "config.nigeria.2030_D2_wacc_1379_ndc.yaml|339"
  "config.nigeria.2030_D3_wacc_2000_ndc.yaml|339"

  # Policy de-risking (P-a) — $3.39
  "config.nigeria.2030_P2_wacc_1179.yaml|339"
  "config.nigeria.2030_P3_wacc_0979.yaml|339"
  "config.nigeria.2030_P4_wacc_0779.yaml|339"

  # Gas pricing (P-b) — $6.00
  "config.nigeria.2030_P1_wacc_1379_gas_600.yaml|600"
  "config.nigeria.2030_P1D_wacc_1379_gas_600_ndc.yaml|600"

  # Sensitivity (S) — $3.39
  "config.nigeria.2030_S2a_battery_1468.yaml|339"
  "config.nigeria.2030_S2b_battery_1468_wacc11.yaml|339"
)

# -----------------------------------------------------------------------------
swap_costs () {
  local variant="$1"
  local target
  case "$variant" in
    339) target="$COSTS_339" ;;
    600) target="$COSTS_600" ;;
    *) echo "!! unknown costs variant: $variant" >&2; exit 1 ;;
  esac
  ln -sf "$target" "$COSTS_LINK"
  touch -h "$COSTS_LINK"
}

# Unlock the working dir if a stale lock exists.
# Safe: we check that no other snakemake process is running first.
unlock_if_needed () {
  if [[ -d .snakemake/locks ]] || [[ -f .snakemake/lock ]]; then
    if ! pgrep -f "snakemake" >/dev/null 2>&1; then
      echo "[lock] removing stale lock"
      snakemake --unlock -c 1 >/dev/null 2>&1 || true
    else
      echo "[lock] another snakemake is running — aborting"
      exit 1
    fi
  fi
}

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------
CURRENT_VARIANT=""
TOTAL=${#SCENARIOS[@]}
IDX=0

for entry in "${SCENARIOS[@]}"; do
  IDX=$((IDX + 1))
  scen="${entry%%|*}"
  variant="${entry##*|}"
  scen_path="$SCEN_DIR/$scen"

  if [[ ! -f "$scen_path" ]]; then
    echo "!! missing scenario file: $scen_path" >&2
    exit 1
  fi

  if [[ "$variant" != "$CURRENT_VARIANT" ]]; then
    echo ""
    echo "=== Switching costs to variant: $variant ==="
    swap_costs "$variant"
    CURRENT_VARIANT="$variant"
  fi

  unlock_if_needed

  log="logs/sweep_$(date +%Y%m%d)/${scen%.yaml}.log"
  echo ""
  echo "=============================================================="
  echo "  [$IDX/$TOTAL] $scen   (costs=$variant)"
  echo "  Log: $log"
  echo "=============================================================="

  if snakemake -call "$TARGET" \
      --configfile "$scen_path" \
      --rerun-incomplete \
      --latency-wait 60 \
      2>&1 | tee "$log"; then
    echo "  OK: $scen"
  else
    echo "  FAILED: $scen (see $log)"
    echo "  Stopping sweep. Fix and re-run from: $scen"
    exit 1
  fi
done

# Restore baseline
echo ""
echo "=== Restoring baseline costs ($COSTS_339) ==="
swap_costs 339
echo "Done. All $TOTAL scenarios complete."