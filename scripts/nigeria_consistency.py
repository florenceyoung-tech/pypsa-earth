"""Explicit, opt-in assumptions for the Nigeria electricity-only paper.

No project-finance estimates or topology connections are inferred here.
"""
import re

import networkx as nx
import numpy as np
import pandas as pd


def real_rate(nominal, inflation):
    if nominal <= -1 or inflation <= -1:
        raise ValueError("Rates must exceed -100%")
    return (1 + nominal) / (1 + inflation) - 1


def convert_explicit_currency(costs, config):
    """Rebase monetary rows with explicit factors, then convert currency.

    exchange_rates maps source currency to output currency per source unit.
    price_year_factors are source-currency price adjustments to price_year.
    Dimensionless ratios (e.g. FOM %) and technical parameters are unchanged.
    """
    out = costs.copy()
    target = config["output_currency"]
    rates = config["exchange_rates"]
    year = int(config["price_year"])
    for idx, row in out.iterrows():
        match = re.match(r"^([A-Z]{3})(?:/|$)", str(row["unit"]))
        if not match:
            continue
        source = match.group(1)
        if source not in rates:
            raise ValueError(f"Missing explicit {source}->{target} FX rate for {idx}")
        source_year = row.get("currency_year")
        if pd.isna(source_year):
            raise ValueError(f"{idx}: missing monetary price year")
        source_year = int(source_year)
        price_factor = 1.0
        if source_year != year:
            factors = config.get("price_year_factors", {}).get(source, {})
            price_factor = factors.get(source_year, factors.get(str(source_year)))
            if price_factor is None:
                raise ValueError(f"{idx}: monetary cost must be independently rebased to {year}; currency_year={source_year}; no documented factor")
            price_factor = float(price_factor)
            if price_factor <= 0:
                raise ValueError("Price adjustment factors must be positive")
        rate = 1.0 if source == target else float(rates[source])
        if rate <= 0:
            raise ValueError("FX rates must be positive")
        out.at[idx, "value"] = float(row["value"]) * price_factor * rate
        out.at[idx, "unit"] = target + str(row["unit"])[3:]
        out.at[idx, "currency_year"] = year
    return out


def set_emission_factors(n, costs):
    """PyPSA primary_energy reads CARRIER fuel factors, then divides by efficiency."""
    zero = {"solar", "onwind", "offwind", "offwind-ac", "offwind-dc", "hydro", "ror", "PHS", "battery", "load", "load shedding"}
    for carrier in n.generators.carrier.unique():
        if carrier not in n.carriers.index:
            n.add("Carrier", carrier)
        key = "gas" if carrier in {"CCGT", "OCGT"} else carrier
        if key in costs.index and pd.notna(costs.at[key, "co2_emissions"]):
            factor = float(costs.at[key, "co2_emissions"])
        elif carrier in zero:
            factor = 0.0
        else:
            raise ValueError(f"Missing fuel CO2 factor for {carrier}; no silent fallback")
        if factor < 0 or (carrier in {"CCGT", "OCGT", "coal", "oil"} and factor <= 0):
            raise ValueError(f"Invalid fuel CO2 factor for {carrier}: {factor}")
        n.carriers.at[carrier, "co2_emissions"] = factor


def apply_nigeria_assumptions(n, config, costs):
    """After clustering: one consistent network boundary and effective gas inputs."""
    cfg = config.get("nigeria_study", {})
    if not cfg.get("enabled", False):
        return {}
    audit = {}
    # No fictitious transmission line. Retain the largest connected component.
    graph = nx.Graph()
    graph.add_nodes_from(n.buses.index)
    for table in (n.lines, n.transformers, n.links):
        graph.add_edges_from(zip(table.bus0, table.bus1))
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    keep = components[0]
    drop = n.buses.index.difference(list(keep))
    load = n.get_switchable_as_dense("Load", "p_set")
    weights = n.snapshot_weightings.generators
    total = float(load.mul(weights, axis=0).sum().sum())
    excluded = float(load.loc[:, n.loads.bus.isin(drop)].mul(weights, axis=0).sum().sum())
    if total <= 0:
        raise ValueError("No positive annual demand")
    if excluded / total > cfg.get("max_excluded_load_share", 0.10):
        raise ValueError("More than 10% of load lies outside the main component; inspect topology before proceeding")
    audit.update(excluded_buses=list(drop), excluded_input_load_mwh=excluded,
                 input_load_mwh=total)
    for component in ("Generator", "Load", "StorageUnit", "Store", "ShuntImpedance"):
        table = n.df(component)
        n.mremove(component, table.index[table.bus.isin(drop)])
    for component in ("Line", "Link", "Transformer"):
        table = n.df(component)
        n.mremove(component, table.index[table.bus0.isin(drop) | table.bus1.isin(drop)])
    n.mremove("Bus", drop)
    target = cfg.get("annual_demand_twh")
    if target is not None:
        load = n.get_switchable_as_dense("Load", "p_set")
        factor = float(target) * 1e6 / float(load.mul(weights, axis=0).sum().sum())
        n.loads_t.p_set = load * factor
        audit["connected_load_scale"] = factor
    if cfg.get("preserve_existing_renewables", False):
        stock = n.generators.index[
            n.generators.carrier.isin(["solar", "onwind", "offwind", "offwind-ac", "offwind-dc", "ror"])
            & n.generators.p_nom_extendable & n.generators.p_nom.gt(0)
        ]
        n.generators.loc[stock, "p_nom_min"] = n.generators.loc[stock, ["p_nom", "p_nom_min"]].max(axis=1)
        if (n.generators.loc[stock, "p_nom_max"] < n.generators.loc[stock, "p_nom_min"]).any():
            raise ValueError("Existing renewable capacity exceeds a model investment bound; inspect rather than retire it silently")
        audit["preserved_existing_renewable_mw"] = float(n.generators.loc[stock, "p_nom"].sum())
    # Historical generation/installed-capacity ratios are proxies, not measured availability.
    for carrier, existing_limit in cfg["existing_gas_derating"].items():
        idx = n.generators.index[n.generators.carrier.eq(carrier)]
        new = n.generators.loc[idx, "p_nom_extendable"]
        limits = pd.Series(np.where(new, cfg["new_gas_availability"], existing_limit), index=idx)
        n.generators.loc[idx, "p_max_pu"] = limits
        for name in idx.intersection(n.generators_t.p_max_pu.columns):
            n.generators_t.p_max_pu[name] = limits[name]
        # One explicit HHV efficiency basis for fuel costs and emissions.
        efficiency = float(costs.at[carrier, "efficiency"])
        if not 0 < efficiency <= 1:
            raise ValueError(f"Invalid {carrier} efficiency: {efficiency}")
        n.generators.loc[idx, "efficiency"] = efficiency
        n.generators.loc[idx, "marginal_cost"] = float(costs.at[carrier, "marginal_cost"])
        for attr, value in (("efficiency", efficiency), ("marginal_cost", float(costs.at[carrier, "marginal_cost"]))):
            panel = n.pnl("Generator")[attr]
            for name in idx.intersection(panel.columns):
                panel[name] = value
    set_emission_factors(n, costs)
    audit["annual_demand_mwh"] = float(n.get_switchable_as_dense("Load", "p_set").mul(weights, axis=0).sum().sum())
    audit["hydro_multiplier"] = config["renewable"]["hydro"].get("multiplier", 1.0)
    return audit
