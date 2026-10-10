"""LCOE computations for technologies across WACC.

Uses the same capital recovery factor convention as PyPSA-Earth:
    annuity(r, n) = r / (1 - (1 + r)^{-n})
    LCOE = (capex * annuity(r, lifetime) + FOM * capex + VOM) / (CF * 8760) + fuel/eff
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def annuity(r, n):
    return r / (1 - (1 + r) ** (-n))


def lcoe(tech_params: dict, r: float, cf: float) -> float:
    """
    tech_params keys:
        capex (EUR/MW)
        fom_pct (fraction of capex per year)
        vom (EUR/MWh_e)
        lifetime (years)
        fuel (EUR/MWh_th)
        efficiency (MWh_e/MWh_th)
    cf : capacity factor (fraction)
    """
    capex = tech_params["capex"]
    fom = tech_params.get("fom_pct", 0.0) * capex
    vom = tech_params.get("vom", 0.0)
    n = tech_params["lifetime"]
    a = annuity(r, n)
    capex_annual = capex * a
    variable = vom
    if "fuel" in tech_params and "efficiency" in tech_params:
        variable += tech_params["fuel"] / tech_params["efficiency"]
    return (capex_annual + fom) / (cf * 8760) + variable


def default_tech_params() -> dict:
    """
    Tech parameters as used in the scenarios. Read from the processed
    costs CSV for realism; fall back to constants.
    """
    return {
        "solar":  {"capex": 814e3 / 0.7532, "fom_pct": 0.0134, "vom": 0.015,
                   "lifetime": 25},
        "onwind": {"capex": 1507e3 / 0.7532, "fom_pct": 0.0234, "vom": 0.015,
                   "lifetime": 30},
        "CCGT":   {"capex": 1989e3 / 0.7532, "fom_pct": 0.0121, "vom": 4.158,
                   "lifetime": 30, "fuel": 9.614, "efficiency": 0.53},
        "OCGT":   {"capex": 1563e3 / 0.7532, "fom_pct": 0.0103, "vom": 4.158,
                   "lifetime": 30, "fuel": 9.614, "efficiency": 0.37},
        "battery": {"capex": (98.6 + 152.1) * 1e3 / 0.7532, "fom_pct": 0.02,
                    "vom": 0.0, "lifetime": 20},
    }


def lcoe_curve(tech: str, waccs: np.ndarray, cf: float,
               params: dict | None = None, gas_usd: float = 3.39) -> np.ndarray:
    """LCOE for a technology across an array of WACC values."""
    p = dict((params or default_tech_params())[tech])
    if gas_usd != 3.39:
        # Scale gas fuel price proportionally
        p["fuel"] = p["fuel"] * (gas_usd / 3.39)
    return np.array([lcoe(p, r, cf) for r in waccs])
