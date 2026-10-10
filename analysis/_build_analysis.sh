cat > analysis/_build_figures.sh <<'BASH'
#!/usr/bin/env bash
# Builds all figure and table modules under analysis/figures and analysis/tables.
set -euo pipefail
cd "$(dirname "$0")"

# =========================================================================
# SHARED HELPERS
# =========================================================================
cat > lib/plot_utils.py <<'PYEOF'
"""Shared plotting helpers for all figure modules."""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd


CARRIER_ORDER = [
    "solar", "onwind", "offwind", "hydro", "ror", "PHS",
    "battery", "CCGT", "OCGT", "oil", "coal", "biomass",
    "load shedding",
]

CARRIER_LABELS = {
    "solar": "Solar",
    "onwind": "Onshore wind",
    "offwind": "Offshore wind",
    "hydro": "Hydro",
    "ror": "Run-of-river",
    "PHS": "Pumped hydro",
    "battery": "Battery",
    "CCGT": "CCGT",
    "OCGT": "OCGT",
    "oil": "Oil",
    "coal": "Coal",
    "biomass": "Biomass",
    "load shedding": "Load shedding",
}


def cap_cols(df):
    return [c for c in df.columns if c.startswith("cap_") and c.endswith("_gw")]


def gen_cols(df):
    return [c for c in df.columns if c.startswith("gen_") and c.endswith("_twh")]


def carrier_from_col(col):
    return col.replace("cap_", "").replace("gen_", "").replace("_gw", "").replace("_twh", "")


def pivot_cap(df):
    """Return a DataFrame indexed by run_name, columns carriers, values GW."""
    cols = cap_cols(df)
    p = df.set_index("run_name")[cols].copy()
    p.columns = [carrier_from_col(c) for c in cols]
    return p


def pivot_gen(df):
    cols = gen_cols(df)
    p = df.set_index("run_name")[cols].copy()
    p.columns = [carrier_from_col(c) for c in cols]
    return p


def ordered_carriers(df_carriers):
    """Filter to CARRIER_ORDER and drop zeros."""
    return [c for c in CARRIER_ORDER if c in df_carriers.columns and df_carriers[c].sum() > 0]


def short_label(run_name: str) -> str:
    """Short label for x-axis ticks."""
    s = run_name
    for prefix in ("cap_exp_2030_", "config.nigeria.2030_"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


def wacc_pct(x):
    return 100 * x
PYEOF

# =========================================================================
# FIGURE 5.1 — Installed capacity stack
# =========================================================================
cat > figures/fig_5_01_capacity.py <<'PYEOF'
"""Fig 5.1: Installed capacity by scenario (stacked bar)."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.plot_utils import pivot_cap, ordered_carriers, short_label, CARRIER_LABELS
from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    cap = pivot_cap(metrics)
    cap = cap.loc[metrics["run_name"]]
    carriers = ordered_carriers(cap)
    cap = cap[carriers]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    bottom = pd.Series(0.0, index=cap.index)
    for c in carriers:
        ax.bar(range(len(cap)), cap[c].values, bottom=bottom.values,
               color=PALETTE.get(c, "#999"), label=CARRIER_LABELS.get(c, c),
               width=0.8, edgecolor="white", linewidth=0.3)
        bottom += cap[c].fillna(0)

    ax.set_xticks(range(len(cap)))
    ax.set_xticklabels([short_label(r) for r in cap.index], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Installed capacity (GW)")
    ax.set_title("Fig 5.1  Installed capacity by scenario, Nigeria 2030")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, ncol=1)
    fig.subplots_adjust(right=0.78, bottom=0.28)
    return Path(save(fig, "fig_5_01_capacity"))
PYEOF

# =========================================================================
# FIGURE 5.2 — Generation mix
# =========================================================================
cat > figures/fig_5_02_generation.py <<'PYEOF'
"""Fig 5.2: Generation mix by scenario (stacked bar)."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.plot_utils import pivot_gen, ordered_carriers, short_label, CARRIER_LABELS
from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    gen = pivot_gen(metrics).loc[metrics["run_name"]]
    carriers = ordered_carriers(gen)
    gen = gen[carriers]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    bottom = pd.Series(0.0, index=gen.index)
    for c in carriers:
        ax.bar(range(len(gen)), gen[c].values, bottom=bottom.values,
               color=PALETTE.get(c, "#999"), label=CARRIER_LABELS.get(c, c),
               width=0.8, edgecolor="white", linewidth=0.3)
        bottom += gen[c].fillna(0)

    ax.set_xticks(range(len(gen)))
    ax.set_xticklabels([short_label(r) for r in gen.index], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Generation (TWh)")
    ax.set_title("Fig 5.2  Generation mix by scenario, Nigeria 2030")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
    fig.subplots_adjust(right=0.78, bottom=0.28)
    return Path(save(fig, "fig_5_02_generation"))
PYEOF

# =========================================================================
# FIGURE 5.3 — WACC sweep with tipping point
# =========================================================================
cat > figures/fig_5_03_wacc_sweep.py <<'PYEOF'
"""Fig 5.3: Solar generation and renewable share vs WACC (C vs D)."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy()

    # C-sweep (no NDC) — sorted by solar WACC
    C = df[df["group"] == "C"].sort_values("wacc_solar")
    D = df[df["group"] == "D"].sort_values("wacc_solar")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel 1 — solar generation
    ax = axes[0]
    ax.plot(100 * C["wacc_solar"], C["gen_solar_twh"],
            "o-", color=PALETTE["solar"], label="C-sweep (no NDC)")
    ax.plot(100 * D["wacc_solar"], D["gen_solar_twh"],
            "s--", color=PALETTE["CCGT"], label="D-sweep (NDC 8.8 Mt)")
    ax.axvline(17, color="gray", linestyle=":", linewidth=1)
    ax.text(17.2, ax.get_ylim()[1]*0.9, "tipping\npoint", fontsize=8, color="gray")
    ax.set_xlabel("Solar / hydro / battery WACC (%)")
    ax.set_ylabel("Solar generation (TWh)")
    ax.set_title("Solar collapses above ~17% WACC\nunless the NDC cap forces it")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel 2 — renewable share
    ax = axes[1]
    ax.plot(100 * C["wacc_solar"], 100 * C["renewable_share"],
            "o-", color=PALETTE["onwind"], label="C-sweep (no NDC)")
    ax.plot(100 * D["wacc_solar"], 100 * D["renewable_share"],
            "s--", color=PALETTE["CCGT"], label="D-sweep (NDC 8.8 Mt)")
    ax.axvline(17, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("Solar / hydro / battery WACC (%)")
    ax.set_ylabel("Renewable share of generation (%)")
    ax.set_title("The NDC cap holds the renewable\nshare flat across all WACC")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    fig.suptitle("Fig 5.3  WACC sweep: unconstrained vs NDC-constrained", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_03_wacc_sweep"))
PYEOF

# =========================================================================
# FIGURE 5.4 — Emissions vs NDC cap
# =========================================================================
cat > figures/fig_5_04_emissions.py <<'PYEOF'
"""Fig 5.4: Emissions by scenario, with NDC cap as a line."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from lib.plot_utils import short_label
from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy().sort_values(["group", "wacc_solar", "ndc"])

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ["#c0392b" if n else "#7f8c8d" for n in df["ndc"]]
    ax.bar(range(len(df)), df["emissions_mt"].values, color=colors,
           edgecolor="white", linewidth=0.3)
    ax.axhline(8.8, color="black", linewidth=1.5, linestyle="--",
               label="NDC 3.0 cap (8.8 Mt)")

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels([short_label(r) for r in df["run_name"]],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Annual CO$_2$ emissions (Mt)")
    ax.set_title("Fig 5.4  Emissions by scenario. Grey = no cap. Red = NDC-constrained.")

    for i, (e, g) in enumerate(zip(df["emissions_mt"], df["group"])):
        ax.text(i, e + 0.3, f"{e:.1f}", ha="center", fontsize=7)

    ax.legend(fontsize=9)
    fig.subplots_adjust(bottom=0.28)
    return Path(save(fig, "fig_5_04_emissions"))
PYEOF

# =========================================================================
# FIGURE 5.5 — System cost
# =========================================================================
cat > figures/fig_5_05_system_cost.py <<'PYEOF'
"""Fig 5.5: Total system cost by scenario."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.plot_utils import short_label
from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy().sort_values(["group", "wacc_solar", "ndc"])

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = {"B": "#34495e", "C": "#3498db", "D": "#c0392b",
              "P-a": "#16a085", "P-b": "#e67e22", "S": "#9b59b6"}
    bar_colors = [colors.get(g, "#999") for g in df["group"]]
    ax.bar(range(len(df)), df["objective"] / 1e9, color=bar_colors,
           edgecolor="white", linewidth=0.3)

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels([short_label(r) for r in df["run_name"]],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Total system cost (bn EUR)")
    ax.set_title("Fig 5.5  Annualised total system cost by scenario")

    handles = [plt.Rectangle((0, 0), 1, 1, color=v) for v in colors.values()]
    labels = ["Baseline (B)", "WACC sweep (C)", "NDC (D)",
              "Policy de-risking (P-a)", "Gas price (P-b)", "Sensitivity (S)"]
    ax.legend(handles, labels, fontsize=8, loc="upper left", ncol=2)

    fig.subplots_adjust(bottom=0.28)
    return Path(save(fig, "fig_5_05_system_cost"))
PYEOF

# =========================================================================
# FIGURE 5.6 — Cost of the NDC cap
# =========================================================================
cat > figures/fig_5_06_cost_of_cap.py <<'PYEOF'
"""Fig 5.6: Cost of the NDC cap = D - C at matched WACC."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from lib.style import save


# Pairs of (C-run, D-run) at the same WACC levels
PAIRS = [
    ("config.nigeria.2030_C2_wacc_0900", "config.nigeria.2030_D1_wacc_1000_ndc", 0.10),
    ("config.nigeria.2030_C6_wacc_1379", "config.nigeria.2030_D2_wacc_1379_ndc", 0.1379),
    ("config.nigeria.2030_C10_wacc_2000", "config.nigeria.2030_D3_wacc_2000_ndc", 0.20),
]


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")
    rows = []
    for c_run, d_run, wacc in PAIRS:
        c_cost = df.at[c_run, "objective"] / 1e9
        d_cost = df.at[d_run, "objective"] / 1e9
        c_emis = df.at[c_run, "emissions_mt"]
        d_emis = df.at[d_run, "emissions_mt"]
        rows.append({
            "wacc": wacc,
            "C_cost": c_cost,
            "D_cost": d_cost,
            "cost_of_cap_bn": d_cost - c_cost,
            "C_emis": c_emis,
            "D_emis": d_emis,
            "abatement_Mt": c_emis - d_emis,
        })
    t = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    x = np.arange(len(t))
    ax.bar(x - 0.2, t["C_cost"], 0.4, label="C — no NDC", color="#7f8c8d")
    ax.bar(x + 0.2, t["D_cost"], 0.4, label="D — NDC 8.8 Mt", color="#c0392b")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{100*w:.1f}%" for w in t["wacc"]])
    ax.set_ylabel("System cost (bn EUR)")
    ax.set_xlabel("Solar WACC")
    ax.legend(fontsize=8)
    ax.set_title("Cost with and without the cap")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    ax.bar(x, t["cost_of_cap_bn"], color="#c0392b")
    for i, v in enumerate(t["cost_of_cap_bn"]):
        ax.text(i, v + 0.05, f"{v:+.2f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{100*w:.1f}%" for w in t["wacc"]])
    ax.set_xlabel("Solar WACC")
    ax.set_ylabel("Cost of the cap (bn EUR/yr)")
    ax.set_title("Annual cost of meeting the 8.8 Mt cap")
    ax.grid(alpha=0.3, axis="y")

    fig.suptitle("Fig 5.6  Cost of the NDC cap at matched WACC", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_06_cost_of_cap"))
PYEOF

# =========================================================================
# FIGURE 5.7 — Financing gap
# =========================================================================
cat > figures/fig_5_07_financing_gap.py <<'PYEOF'
"""Fig 5.7: Financing gap — cost premium over the 7% WACC optimum."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.plot_utils import short_label
from lib.style import save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy()

    # Baseline = C1 (7% WACC, no cap)
    baseline = df.query("run_name == 'config.nigeria.2030_C1_wacc_0700'")["objective"].iloc[0]

    df["financing_gap_bn"] = (df["objective"] - baseline) / 1e9
    df["financing_gap_pct"] = 100 * (df["objective"] - baseline) / baseline

    df = df.sort_values(["group", "wacc_solar", "ndc"])

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = {"B": "#34495e", "C": "#3498db", "D": "#c0392b",
              "P-a": "#16a085", "P-b": "#e67e22", "S": "#9b59b6"}
    bar_colors = [colors.get(g, "#999") for g in df["group"]]
    ax.bar(range(len(df)), df["financing_gap_bn"], color=bar_colors)

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels([short_label(r) for r in df["run_name"]],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Financing gap (bn EUR/yr)")
    ax.set_title("Fig 5.7  Financing gap: cost premium over the 7% WACC unconstrained optimum")
    fig.subplots_adjust(bottom=0.28)
    return Path(save(fig, "fig_5_07_financing_gap"))
PYEOF

# =========================================================================
# FIGURE 5.8 — LCOE curves with carbon-price bands
# =========================================================================
cat > figures/fig_5_08_lcoe_curves.py <<'PYEOF'
"""Fig 5.8: LCOE by technology vs WACC, with three carbon-price bands."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from lib.lcoe import lcoe_curve, default_tech_params
from lib.style import PALETTE, save


CARBON_PRICES = [0, 50, 100]   # USD/tCO2


def _ccgt_lcoe_with_carbon(r, carbon_usd_per_t, gas_usd, cf=0.65):
    """
    CCGT LCOE including carbon cost. Carbon scales with fuel MWh_th.
    carbon_cost (EUR/MWh_e) = carbon_usd/tCO2 * EF_tCO2/MWh_th / eff * USD_to_EUR
    """
    params = default_tech_params()
    p = dict(params["CCGT"])
    if gas_usd != 3.39:
        p["fuel"] = p["fuel"] * (gas_usd / 3.39)
    USD_TO_EUR = 0.7532
    carbon_eur_per_mwh_e = carbon_usd_per_t * 0.181 / p["efficiency"] * USD_TO_EUR
    from lib.lcoe import lcoe
    base = lcoe(p, r, cf)
    return base + carbon_eur_per_mwh_e


def make(metrics) -> Path:
    waccs = np.linspace(0.05, 0.22, 40)

    fig, ax = plt.subplots(figsize=(8, 5))

    # Renewables — invariant to carbon price
    for tech, cf, color in [("solar", 0.25, PALETTE["solar"]),
                             ("onwind", 0.35, PALETTE["onwind"])]:
        y = lcoe_curve(tech, waccs, cf)
        ax.plot(100 * waccs, y, color=color, linewidth=2, label=tech.capitalize())

    # Gas — three carbon bands
    band_colors = ["#e67e22", "#c0392b", "#7b241c"]
    for cp, color in zip(CARBON_PRICES, band_colors):
        y = np.array([_ccgt_lcoe_with_carbon(r, cp, 3.39) for r in waccs])
        ax.plot(100 * waccs, y, color=color, linewidth=2,
                linestyle="-", label=f"CCGT, ${cp}/tCO$_2$")

    ax.set_xlabel("WACC (%)")
    ax.set_ylabel("LCOE (EUR/MWh$_e$)")
    ax.set_title("Fig 5.8  LCOE by technology vs WACC, with carbon-price sensitivity")
    ax.set_ylim(0, 160)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    return Path(save(fig, "fig_5_08_lcoe_curves"))
PYEOF

# =========================================================================
# FIGURE 5.9 — LCOE crossover
# =========================================================================
cat > figures/fig_5_09_lcoe_crossover.py <<'PYEOF'
"""Fig 5.9: Solar-CCGT LCOE crossover as a function of WACC and carbon price."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from lib.lcoe import lcoe_curve, default_tech_params, lcoe
from lib.style import PALETTE, save


CARBON_PRICES = [0, 50, 100]
USD_TO_EUR = 0.7532


def _ccgt_lcoe(r, carbon_usd_per_t, gas_usd=3.39, cf=0.65):
    p = dict(default_tech_params()["CCGT"])
    if gas_usd != 3.39:
        p["fuel"] = p["fuel"] * (gas_usd / 3.39)
    carbon = carbon_usd_per_t * 0.181 / p["efficiency"] * USD_TO_EUR
    return lcoe(p, r, cf) + carbon


def make(metrics) -> Path:
    waccs = np.linspace(0.03, 0.25, 100)
    solar = lcoe_curve("solar", waccs, 0.25)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(100 * waccs, solar, color=PALETTE["solar"], linewidth=2.5, label="Solar PV")

    for cp, color in zip(CARBON_PRICES, ["#e67e22", "#c0392b", "#7b241c"]):
        y = np.array([_ccgt_lcoe(r, cp, 3.39) for r in waccs])
        ax.plot(100 * waccs, y, color=color, linewidth=2,
                label=f"CCGT, ${cp}/tCO$_2$")
        # Crossover
        idx = np.argmin(np.abs(solar - y))
        if 0.03 < waccs[idx] < 0.25:
            xw = 100 * waccs[idx]
            yw = solar[idx]
            ax.plot([xw], [yw], "o", color=color, markersize=6)
            ax.annotate(f"{xw:.1f}%",
                        xy=(xw, yw), xytext=(xw + 1, yw + 6),
                        fontsize=8, color=color)

    ax.set_xlabel("WACC (%)")
    ax.set_ylabel("LCOE (EUR/MWh$_e$)")
    ax.set_title("Fig 5.9  Solar vs CCGT LCOE crossover at three carbon prices")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 160)
    ax.grid(alpha=0.3)
    return Path(save(fig, "fig_5_09_lcoe_crossover"))
PYEOF

# =========================================================================
# FIGURE 5.10 — Policy de-risking
# =========================================================================
cat > figures/fig_5_10_policy_derisking.py <<'PYEOF'
"""Fig 5.10: P-a scenarios vs equivalent C-sweep points."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")

    # P-a points (solar WACC, renewable share, cost)
    pa = [
        ("config.nigeria.2030_P4_wacc_0779", "P4 (7.79% solar)"),
        ("config.nigeria.2030_P3_wacc_0979", "P3 (9.79% solar)"),
        ("config.nigeria.2030_P2_wacc_1179", "P2 (11.79% solar)"),
    ]
    c_sweep = df[df["group"] == "C"].sort_values("wacc_solar")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel 1 — solar WACC vs solar capacity
    ax = axes[0]
    ax.plot(100 * c_sweep["wacc_solar"], c_sweep["cap_solar_gw"],
            "o-", color="#3498db", label="C-sweep")
    for run, label in pa:
        ax.scatter(100 * df.at[run, "wacc_solar"], df.at[run, "cap_solar_gw"],
                   s=100, color="#16a085", zorder=5, edgecolor="black",
                   linewidth=0.6)
        ax.annotate(label.split()[0], xy=(100 * df.at[run, "wacc_solar"],
                                          df.at[run, "cap_solar_gw"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Solar WACC (%)")
    ax.set_ylabel("Solar capacity (GW)")
    ax.set_title("P-a points sit on the C-sweep\n(no independent capacity effect)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)

    # Panel 2 — cost vs solar WACC
    ax = axes[1]
    ax.plot(100 * c_sweep["wacc_solar"], c_sweep["objective"] / 1e9,
            "o-", color="#3498db", label="C-sweep")
    for run, label in pa:
        ax.scatter(100 * df.at[run, "wacc_solar"], df.at[run, "objective"] / 1e9,
                   s=100, color="#16a085", zorder=5, edgecolor="black",
                   linewidth=0.6)
    ax.set_xlabel("Solar WACC (%)")
    ax.set_ylabel("System cost (bn EUR/yr)")
    ax.set_title("Cost trajectory is the same\nas the WACC sweep")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)

    fig.suptitle("Fig 5.10  Policy de-risking: P-a equivalent to a WACC reduction", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_10_policy_derisking"))
PYEOF

# =========================================================================
# FIGURE 5.11 — Gas price + non-substitutability
# =========================================================================
cat > figures/fig_5_11_gas_price.py <<'PYEOF'
"""Fig 5.11: Gas price interaction and non-substitutability test."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel 1 — gas price effect at matched WACC 13.79%
    ax = axes[0]
    runs = [
        ("config.nigeria.2030_C6_wacc_1379", "C6\n$3.39\nno NDC"),
        ("config.nigeria.2030_P1_wacc_1379_gas_600", "P1\n$6.00\nno NDC"),
        ("config.nigeria.2030_D2_wacc_1379_ndc", "D2\n$3.39\nNDC"),
        ("config.nigeria.2030_P1D_wacc_1379_gas_600_ndc", "P1D\n$6.00\nNDC"),
    ]
    labels = [r[1] for r in runs]
    solar = [df.at[r[0], "cap_solar_gw"] for r in runs]
    ccgt = [df.at[r[0], "cap_CCGT_gw"] for r in runs]
    x = np.arange(len(runs))
    ax.bar(x - 0.2, solar, 0.4, label="Solar", color=PALETTE["solar"])
    ax.bar(x + 0.2, ccgt, 0.4, label="CCGT", color=PALETTE["CCGT"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Installed capacity (GW)")
    ax.set_title("Gas price barely shifts the mix")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # Panel 2 — non-substitutability
    ax = axes[1]
    # Solar GW change per pp WACC reduction (from C-sweep, going from C10 to C1)
    C = df.loc[[r for r in df.index if r.startswith("config.nigeria.2030_C")]].copy()
    C = C.sort_values("wacc_solar")
    dwacc = 100 * (C["wacc_solar"].iloc[-1] - C["wacc_solar"].iloc[0])  # 20 - 7 = 13
    dsolar_wacc = C["cap_solar_gw"].iloc[0] - C["cap_solar_gw"].iloc[-1]
    gw_per_pp_wacc = dsolar_wacc / dwacc

    # Solar GW change per $/MMBtu gas price increase (P1 vs C6)
    dsolar_gas = df.at["config.nigeria.2030_P1_wacc_1379_gas_600", "cap_solar_gw"] - \
                 df.at["config.nigeria.2030_C6_wacc_1379", "cap_solar_gw"]
    dgas = 6.00 - 3.39
    gw_per_usd_gas = dsolar_gas / dgas

    ax.bar([0, 1], [gw_per_pp_wacc, gw_per_usd_gas],
           color=["#3498db", "#e67e22"], width=0.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([f"per pp\nWACC reduction\n({gw_per_pp_wacc:+.3f} GW/pp)",
                        f"per $/MMBtu\ngas price rise\n({gw_per_usd_gas:+.3f} GW/$)"],
                       fontsize=8)
    ax.set_ylabel("Solar capacity response (GW)")
    ax.set_title("WACC reduction dominates gas pricing\n(non-substitutability test)")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.grid(alpha=0.3, axis="y")

    fig.suptitle("Fig 5.11  Gas price vs WACC as competing levers", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_11_gas_price"))
PYEOF

# =========================================================================
# FIGURE 5.12 — Battery sensitivity
# =========================================================================
cat > figures/fig_5_12_battery.py <<'PYEOF'
"""Fig 5.12: S2a/S2b vs C6 and C3 (battery WACC effect)."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.style import PALETTE, save


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")

    runs = [
        ("config.nigeria.2030_C6_wacc_1379", "C6\n13.79/13.79\nbattery = solar"),
        ("config.nigeria.2030_S2a_battery_1468", "S2a\n13.79/14.68\nbattery higher"),
        ("config.nigeria.2030_C3_wacc_1100", "C3\n11/11\nbattery = solar"),
        ("config.nigeria.2030_S2b_battery_1468_wacc11", "S2b\n11/14.68\nbattery higher"),
    ]

    labels = [r[1] for r in runs]
    cap_bat = [df.at[r[0], "cap_battery_gw"] for r in runs]
    dis_bat = [df.at[r[0], "battery_throughput_twh"] for r in runs]
    obj = [df.at[r[0], "objective"] / 1e9 for r in runs]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    ax = axes[0]
    ax.bar(range(len(runs)), cap_bat, color=PALETTE["battery"])
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Battery capacity (GW)")
    ax.set_title("Battery p_nom")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    ax.bar(range(len(runs)), dis_bat, color=PALETTE["battery"])
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Discharge (TWh)")
    ax.set_title("Battery throughput")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[2]
    ax.bar(range(len(runs)), obj, color="#7f8c8d")
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("System cost (bn EUR)")
    ax.set_title("Total cost")
    ax.grid(alpha=0.3, axis="y")

    fig.suptitle("Fig 5.12  Battery WACC sensitivity", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_12_battery"))
PYEOF

# =========================================================================
# FIGURE 5.13 — Dispatch panels for four weeks
# =========================================================================
cat > figures/fig_5_13_dispatch_weeks.py <<'PYEOF'
"""Fig 5.13: Dispatch for four representative weeks at 3 WACC levels."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from lib.io import extract_hourly
from lib.plot_utils import CARRIER_ORDER, CARRIER_LABELS
from lib.style import PALETTE, save


WEEKS = [
    ("2024-01-15", "2024-01-22", "Dry / Harmattan"),
    ("2024-03-15", "2024-03-22", "Peak solar"),
    ("2024-04-15", "2024-04-22", "Peak demand"),
    ("2024-07-15", "2024-07-22", "Wet season"),
]

RUNS = [
    ("config.nigeria.2030_C1_wacc_0700", "7% WACC"),
    ("config.nigeria.2030_C6_wacc_1379", "13.79% WACC"),
    ("config.nigeria.2030_C10_wacc_2000", "20% WACC"),
]


def _plot_panel(ax, run_name, week_start, week_end, title):
    data = extract_hourly(run_name)
    disp = data["dispatch_by_carrier"]
    mask = (disp.index >= week_start) & (disp.index < week_end)
    sub = disp.loc[mask]
    if sub.empty:
        ax.set_title(f"{title}\n(no data)")
        return

    carriers = [c for c in CARRIER_ORDER if c in sub.columns and sub[c].sum() > 0]
    x = np.arange(len(sub))
    bottom = np.zeros(len(sub))
    for c in carriers:
        ax.bar(x, sub[c].values, bottom=bottom,
               color=PALETTE.get(c, "#999"), label=CARRIER_LABELS.get(c, c),
               width=1.0, edgecolor="none")
        bottom += sub[c].values
    ax.set_xlim(0, len(sub))
    ax.set_title(title, fontsize=9)
    ax.set_ylabel("MW", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_xticks([0, len(sub) // 2, len(sub) - 1])
    ax.set_xticklabels(["d0", "d3", "d6"])


def make(metrics: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(len(RUNS), len(WEEKS), figsize=(13, 8), sharex=False)
    for i, (run, run_label) in enumerate(RUNS):
        for j, (ws, we, wlabel) in enumerate(WEEKS):
            ax = axes[i, j]
            _plot_panel(ax, run, ws, we, f"{run_label}\n{wlabel}" if i == 0 else wlabel)

    # legend on the right
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Fig 5.13  Dispatch for representative weeks at three WACC levels", y=0.995)
    fig.tight_layout(rect=[0, 0, 0.9, 0.97])
    return Path(save(fig, "fig_5_13_dispatch_weeks"))
PYEOF

# =========================================================================
# FIGURE 5.14 — Generator duration curves
# =========================================================================
cat > figures/fig_5_14_gen_duration.py <<'PYEOF'
"""Fig 5.14: Generator duration curves (sorted dispatch per carrier)."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from lib.io import extract_hourly
from lib.plot_utils import CARRIER_ORDER, CARRIER_LABELS
from lib.style import PALETTE, save


RUNS = [
    ("config.nigeria.2030_C1_wacc_0700", "7% WACC"),
    ("config.nigeria.2030_C6_wacc_1379", "13.79% WACC"),
    ("config.nigeria.2030_C10_wacc_2000", "20% WACC"),
]


def make(metrics) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)

    for ax, (run, label) in zip(axes, RUNS):
        data = extract_hourly(run)
        disp = data["dispatch_by_carrier"]
        carriers = [c for c in CARRIER_ORDER if c in disp.columns and disp[c].sum() > 0]

        # Sort total dispatch per snapshot, plot each carrier's contribution stacked
        total = disp[carriers].sum(axis=1)
        order = np.argsort(total.values)[::-1]
        x = np.arange(len(order))
        bottom = np.zeros(len(order))
        for c in carriers:
            vals = disp[c].values[order]
            ax.fill_between(x, bottom, bottom + vals,
                            color=PALETTE.get(c, "#999"), label=CARRIER_LABELS.get(c, c),
                            linewidth=0)
            bottom += vals

        ax.set_xlabel("Hours (sorted by total dispatch)", fontsize=8)
        ax.set_title(label, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)

    axes[0].set_ylabel("Dispatch (MW)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Fig 5.14  Generator duration curves at three WACC levels", y=1.02)
    fig.tight_layout(rect=[0, 0, 0.9, 0.97])
    return Path(save(fig, "fig_5_14_gen_duration"))
PYEOF

# =========================================================================
# FIGURE 5.15 — Price duration curves
# =========================================================================
cat > figures/fig_5_15_price_duration.py <<'PYEOF'
"""Fig 5.15: Hourly price duration curves."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from lib.io import extract_hourly
from lib.style import PALETTE, save


RUNS = [
    ("config.nigeria.2030_C1_wacc_0700", "7% WACC", "#3498db"),
    ("config.nigeria.2030_C6_wacc_1379", "13.79% WACC", "#16a085"),
    ("config.nigeria.2030_C10_wacc_2000", "20% WACC", "#c0392b"),
    ("config.nigeria.2030_D2_wacc_1379_ndc", "13.79% WACC + NDC", "#7b241c"),
]


def make(metrics) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))

    for run, label, color in RUNS:
        data = extract_hourly(run)
        prices = data["prices"].dropna()
        sorted_p = np.sort(prices.values)[::-1]
        x = 100 * np.arange(len(sorted_p)) / len(sorted_p)
        ax.plot(x, sorted_p, label=label, color=color, linewidth=1.8)

    ax.set_xlabel("Share of hours (%)")
    ax.set_ylabel("Marginal price (EUR/MWh)")
    ax.set_title("Fig 5.15  Price duration curves")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return Path(save(fig, "fig_5_15_price_duration"))
PYEOF

# =========================================================================
# FIGURE 5.16 — Curtailment by bus
# =========================================================================
cat > figures/fig_5_16_curtailment_map.py <<'PYEOF'
"""Fig 5.16: Curtailment by bus (bar, since maps require geodata)."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from lib.io import load_network
from lib.plot_utils import CARRIER_ORDER
from lib.style import PALETTE, save


RUNS = [
    ("config.nigeria.2030_C1_wacc_0700", "7% WACC"),
    ("config.nigeria.2030_C6_wacc_1379", "13.79% WACC"),
    ("config.nigeria.2030_C10_wacc_2000", "20% WACC"),
]


def _curtail_per_bus(n):
    dt = n.snapshot_weightings["generators"]
    out = {}
    for tech in ["solar", "onwind"]:
        gens = n.generators.query("carrier == @tech")
        if len(gens) == 0:
            continue
        p_max = n.generators_t.p_max_pu[gens.index].mul(gens.p_nom_opt, axis=1)
        avail = p_max.mul(dt, axis=0).sum()
        actual = n.generators_t.p[gens.index].mul(dt, axis=0).sum()
        curtail = (avail - actual).clip(lower=0)
        for bus in gens.bus.unique():
            idx = gens.query("bus == @bus").index
            c = curtail[idx].sum() / 1e6  # TWh
            out.setdefault(bus, {})[tech] = float(c)
    return out


def make(metrics) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True)
    for ax, (run, label) in zip(axes, RUNS):
        n = load_network(run)
        c = _curtail_per_bus(n)
        buses = sorted(c.keys())
        x = np.arange(len(buses))
        solar = [c[b].get("solar", 0) for b in buses]
        wind = [c[b].get("onwind", 0) for b in buses]
        ax.bar(x - 0.2, solar, 0.4, color=PALETTE["solar"], label="Solar")
        ax.bar(x + 0.2, wind, 0.4, color=PALETTE["onwind"], label="Wind")
        ax.set_xticks(x)
        ax.set_xticklabels([b.replace("NG ", "") for b in buses], rotation=45, ha="right", fontsize=7)
        ax.set_title(label, fontsize=9)
        ax.grid(alpha=0.3, axis="y")

    axes[0].set_ylabel("Curtailment (TWh)")
    axes[0].legend(fontsize=8)
    fig.suptitle("Fig 5.16  Curtailment by bus", y=1.02)
    fig.tight_layout()
    return Path(save(fig, "fig_5_16_curtailment_map"))
PYEOF

# =========================================================================
# TABLES
# =========================================================================
cat > tables/tbl_5_01_headline.py <<'PYEOF'
"""Table 5.1: Headline metrics, one row per scenario."""
from pathlib import Path
import pandas as pd

OUT = Path("analysis/output/tables")


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy()
    cols = [
        "run_name", "group", "wacc_solar", "wacc_battery", "wacc_gas",
        "ndc", "gas_usd_per_mmbtu",
        "objective", "cap_total_gw", "gen_total_twh", "emissions_mt",
        "renewable_share", "curtailment_twh", "curtailment_pct",
        "avg_price_eur_mwh", "battery_throughput_twh",
        "capex_eur", "var_opex_eur", "capex_share",
    ]
    cols = [c for c in cols if c in df.columns]
    out = df[cols]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_01_headline.csv"
    out.to_csv(p, index=False)
    return p
PYEOF

cat > tables/tbl_5_02_lcoe.py <<'PYEOF'
"""Table 5.2: LCOE by technology at each WACC point."""
from pathlib import Path
import numpy as np
import pandas as pd

from lib.lcoe import lcoe_curve, default_tech_params

OUT = Path("analysis/output/tables")

WACCS = [0.07, 0.09, 0.11, 0.12, 0.13, 0.1379, 0.1468, 0.16, 0.18, 0.20]
TECHS = {"solar": 0.25, "onwind": 0.35, "CCGT": 0.65, "OCGT": 0.15, "battery": 0.20}


def make(metrics) -> Path:
    rows = []
    for tech, cf in TECHS.items():
        lcoes = lcoe_curve(tech, np.array(WACCS), cf, gas_usd=3.39)
        for w, l in zip(WACCS, lcoes):
            rows.append({"technology": tech, "wacc": w, "cf": cf, "lcoe_eur_mwh": l})
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_02_lcoe.csv"
    out.to_csv(p, index=False)
    return p
PYEOF

cat > tables/tbl_5_03_instrument_effectiveness.py <<'PYEOF'
"""Table 5.3: Instrument effectiveness — GW per pp WACC vs GW per $/MMBtu."""
from pathlib import Path
import pandas as pd

OUT = Path("analysis/output/tables")


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")

    C = df.loc[[r for r in df.index if r.startswith("config.nigeria.2030_C")]]
    C = C.sort_values("wacc_solar")
    dwacc_pp = 100 * (C["wacc_solar"].iloc[-1] - C["wacc_solar"].iloc[0])
    dsolar_wacc = C["cap_solar_gw"].iloc[0] - C["cap_solar_gw"].iloc[-1]
    dsolar_wacc_per_pp = dsolar_wacc / dwacc_pp

    dsolar_gas = df.at["config.nigeria.2030_P1_wacc_1379_gas_600", "cap_solar_gw"] - \
                 df.at["config.nigeria.2030_C6_wacc_1379", "cap_solar_gw"]
    dgas = 6.00 - 3.39
    dsolar_gas_per_usd = dsolar_gas / dgas

    rows = [
        {"instrument": "WACC reduction", "unit": "GW per pp",
         "response": dsolar_wacc_per_pp,
         "note": f"from C10 to C1, {dwacc_pp:.1f} pp"},
        {"instrument": "Gas price rise", "unit": "GW per $/MMBtu",
         "response": dsolar_gas_per_usd,
         "note": f"P1 vs C6, ${dgas:.2f}/MMBtu"},
    ]
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_03_instrument_effectiveness.csv"
    out.to_csv(p, index=False)
    return p
PYEOF

cat > tables/tbl_5_04_debt_equity.py <<'PYEOF'
"""Table 5.4: Implied debt-equity ratio at each WACC point.

Assumes a translation from observed WACC to a debt/equity split, using
a fixed cost of debt r_d = 6% and cost of equity r_e consistent with
a corporate-finance Modigliani-Miller weighted average:

    WACC = (1 - D) * r_e + D * r_d  ->  D = (r_e - WACC) / (r_e - r_d)

Here we use r_e = 20% (typical EM infrastructure equity) and r_d = 6%.
"""
from pathlib import Path
import pandas as pd

OUT = Path("analysis/output/tables")

R_D = 0.06
R_E = 0.20


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.copy()
    df["implied_debt_share"] = (R_E - df["wacc_solar"]) / (R_E - R_D)
    df["implied_debt_share"] = df["implied_debt_share"].clip(0, 1)
    df["implied_equity_share"] = 1 - df["implied_debt_share"]
    cols = ["run_name", "group", "wacc_solar", "implied_debt_share", "implied_equity_share"]
    out = df[cols]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_04_debt_equity.csv"
    out.to_csv(p, index=False)
    return p
PYEOF

cat > tables/tbl_5_05_gas_price_effect.py <<'PYEOF'
"""Table 5.5: Gas price effect on the tipping point and the mix."""
from pathlib import Path
import pandas as pd

OUT = Path("analysis/output/tables")


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")
    runs = [
        "config.nigeria.2030_C6_wacc_1379",
        "config.nigeria.2030_P1_wacc_1379_gas_600",
        "config.nigeria.2030_D2_wacc_1379_ndc",
        "config.nigeria.2030_P1D_wacc_1379_gas_600_ndc",
    ]
    cols = ["group", "gas_usd_per_mmbtu", "ndc", "cap_solar_gw", "cap_CCGT_gw",
            "gen_solar_twh", "gen_CCGT_twh", "emissions_mt", "objective"]
    out = df.loc[runs, [c for c in cols if c in df.columns]]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_05_gas_price_effect.csv"
    out.to_csv(p)
    return p
PYEOF

cat > tables/tbl_5_06_battery_wacc.py <<'PYEOF'
"""Table 5.6: Battery WACC effect."""
from pathlib import Path
import pandas as pd

OUT = Path("analysis/output/tables")


def make(metrics: pd.DataFrame) -> Path:
    df = metrics.set_index("run_name")
    runs = [
        "config.nigeria.2030_C6_wacc_1379",
        "config.nigeria.2030_S2a_battery_1468",
        "config.nigeria.2030_C3_wacc_1100",
        "config.nigeria.2030_S2b_battery_1468_wacc11",
    ]
    cols = ["wacc_solar", "wacc_battery", "cap_battery_gw",
            "battery_throughput_twh", "renewable_share", "emissions_mt",
            "objective"]
    out = df.loc[runs, [c for c in cols if c in df.columns]]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "tbl_5_06_battery_wacc.csv"
    out.to_csv(p)
    return p
PYEOF

echo "Built all figure and table modules."
echo ""
echo "Now run: python analysis/run_all.py --force"
BASH

chmod +x analysis/_build_figures.sh
bash analysis/_build_figures.sh