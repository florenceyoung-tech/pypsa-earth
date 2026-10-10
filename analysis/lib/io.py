"""
Load networks and extract metrics. Cached to analysis/metrics.csv so
subsequent runs of the figure modules are instant.
"""
from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import pypsa
import yaml

from .manifest import build_manifest


RESULTS_DIR = Path("results")
CACHE = Path("analysis/metrics.csv")
HOURLY_CACHE = Path("analysis/hourly")


# ---------------------------------------------------------------------------
# Scenario lookup
# ---------------------------------------------------------------------------
def scenario_manifest() -> pd.DataFrame:
    return build_manifest()


def network_path(run_name: str) -> Path:
    return RESULTS_DIR / run_name / "networks" / "elec_s_10_ec_lcopt_1h.nc"


def load_network(run_name: str) -> pypsa.Network:
    p = network_path(run_name)
    if not p.exists():
        raise FileNotFoundError(f"Missing network for {run_name}: {p}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pypsa.Network(str(p))


# ---------------------------------------------------------------------------
# Per-scenario metrics
# ---------------------------------------------------------------------------
def extract_metrics(n: pypsa.Network, meta: dict) -> dict:
    """One row of the summary metrics table."""
    out = dict(meta)

    # --- Objective -----------------------------------------------------
    out["objective"] = float(n.objective)

    # --- Capacity by carrier (GW) --------------------------------------
    gen_cap = (n.generators.groupby("carrier")["p_nom_opt"].sum() / 1e3)
    su_cap = (n.storage_units.groupby("carrier")["p_nom_opt"].sum() / 1e3)
    cap = gen_cap.add(su_cap, fill_value=0.0)
    for carrier, v in cap.items():
        out[f"cap_{carrier}_gw"] = float(v)
    out["cap_total_gw"] = float(cap.sum())

    # --- Generation by carrier (TWh) -----------------------------------
    # Generators: energy = sum(p * dt) / 1e6 to get TWh
    dt = n.snapshot_weightings["generators"]
    gen_twh = (n.generators_t.p.mul(dt, axis=0).sum() / 1e6)
    gen_twh_by_carrier = gen_twh.groupby(n.generators.carrier).sum()

    # Storage units: discharge - charge (net)
    su_discharge = n.storage_units_t.p.mul(dt, axis=0).clip(lower=0).sum() / 1e6
    su_discharge_carrier = su_discharge.groupby(n.storage_units.carrier).sum()

    gen_total = gen_twh_by_carrier.add(su_discharge_carrier, fill_value=0.0)
    for carrier, v in gen_total.items():
        out[f"gen_{carrier}_twh"] = float(v)
    out["gen_total_twh"] = float(gen_total.sum())

    # --- Renewable share -----------------------------------------------
    renewable_carriers = {"solar", "onwind", "offwind", "hydro", "ror"}
    ren = sum(v for c, v in gen_total.items() if c in renewable_carriers)
    out["renewable_share"] = float(ren / out["gen_total_twh"]) if out["gen_total_twh"] > 0 else np.nan

    # --- Emissions (Mt) ------------------------------------------------
    # Compute from generation and fuel-based EFs, not from the network's
    # co2_emissions column (which is only populated when the cap is active).
    # EF_e = CO2_intensity_fuel / efficiency, using values from costs.csv.
    EF_E = {
        "CCGT": 0.181 / 0.53,   # 0.3415 tCO2/MWh_e
        "OCGT": 0.181 / 0.37,   # 0.4892 tCO2/MWh_e
        "oil":  0.248 / 0.393,  # 0.6310
        "coal": 0.354 / 0.464,  # 0.7629
    }
    gen_by_carrier = n.generators_t.p.mul(dt, axis=0).sum().groupby(
        n.generators.carrier).sum()  # MWh_e
    emis = 0.0
    for carrier, ef in EF_E.items():
        if carrier in gen_by_carrier.index:
            emis += float(gen_by_carrier[carrier]) * ef
    out["emissions_mt"] = emis / 1e6

    # --- Load shedding (TWh) -------------------------------------------
    ls = n.generators.query("carrier == 'load'")
    if len(ls):
        ls_twh = float(n.generators_t.p[ls.index].mul(dt, axis=0).sum().sum() / 1e6)
    else:
        ls_twh = 0.0
    out["load_shedding_twh"] = ls_twh

    # --- Curtailment ----------------------------------------------------
    # Curtailment = available - dispatched, for VRE carriers only
    curtail_twh = 0.0
    for tech in ["solar", "onwind", "offwind"]:
        gens = n.generators.query("carrier == @tech")
        if len(gens) == 0:
            continue
        p_max = n.generators_t.p_max_pu[gens.index].mul(gens.p_nom_opt, axis=1)
        avail = p_max.mul(dt, axis=0).sum().sum() / 1e6
        actual = n.generators_t.p[gens.index].mul(dt, axis=0).sum().sum() / 1e6
        curtail_twh += max(0.0, avail - actual)
    out["curtailment_twh"] = float(curtail_twh)
    out["curtailment_pct"] = (
        float(curtail_twh / (curtail_twh + out["gen_total_twh"]))
        if (curtail_twh + out["gen_total_twh"]) > 0 else np.nan
    )

    # --- Average marginal price (EUR/MWh) ------------------------------
    # Load-weighted price at the transmission buses
    buses = n.buses.query("carrier == 'AC'").index
    prices = n.buses_t.marginal_price[buses]
    load_p = n.loads_t.p[buses.intersection(n.loads_t.p.columns)]
    if load_p.shape[1] > 0:
        weights = load_p.sum(axis=1)
        avg_price = float((prices.mean(axis=1) * weights).sum() / weights.sum())
    else:
        avg_price = float(prices.mean().mean())
    out["avg_price_eur_mwh"] = avg_price

    # --- Cost breakdown -------------------------------------------------
    # PyPSA objective decomposes into capex, opex, etc. For the electricity
    # only model the objective is the total system cost, which is the
    # annuity-weighted capex + opex. We can approximate the split:
    # annualized capex = objective - variable opex
    # Variable opex = sum(marginal_cost * dispatch) + load shedding penalty
    var_opex = (
        (n.generators_t.p.mul(dt, axis=0) * n.generators.marginal_cost).sum().sum()
        + (n.storage_units_t.p.mul(dt, axis=0).clip(lower=0)
           * n.storage_units.marginal_cost).sum().sum()
    )
    out["var_opex_eur"] = float(var_opex)
    out["capex_eur"] = float(out["objective"] - var_opex)
    out["capex_share"] = float(out["capex_eur"] / out["objective"]) if out["objective"] else np.nan

    # --- Battery throughput --------------------------------------------
    su = n.storage_units.query("carrier == 'battery'")
    if len(su):
        throughput = float(
            n.storage_units_t.p[su.index].mul(dt, axis=0).clip(lower=0).sum().sum() / 1e6
        )
    else:
        throughput = 0.0
    out["battery_throughput_twh"] = throughput

    return out


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
def build_metrics(force: bool = False) -> pd.DataFrame:
    """Extract metrics from all networks. Cached to analysis/metrics.csv."""
    if CACHE.exists() and not force:
        return pd.read_csv(CACHE)

    manifest = scenario_manifest()
    rows = []
    for _, meta in manifest.iterrows():
        try:
            n = load_network(meta["run_name"])
            rows.append(extract_metrics(n, meta.to_dict()))
        except Exception as e:
            print(f"!! {meta['run_name']}: {e}")
            rows.append({**meta.to_dict(), "error": str(e)})

    df = pd.DataFrame(rows)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE, index=False)
    print(f"Wrote {len(df)} rows to {CACHE}")
    return df


# ---------------------------------------------------------------------------
# Hourly extraction (only for figures that need it)
# ---------------------------------------------------------------------------
def extract_hourly(run_name: str) -> dict:
    """Return dict of hourly series for a single scenario."""
    n = load_network(run_name)
    dt = n.snapshot_weightings["generators"]

    gen_t = n.generators_t.p
    carriers = n.generators.carrier
    dispatch_by_carrier = (
        gen_t.T.groupby(carriers).sum().T
    )
    dispatch_by_carrier.index = n.snapshots

    # Price at transmission buses
    buses = n.buses.query("carrier == 'AC'").index
    prices = n.buses_t.marginal_price[buses].mean(axis=1)

    return {
        "snapshots": n.snapshots,
        "dispatch_by_carrier": dispatch_by_carrier,
        "prices": prices,
        "network": n,
    }
