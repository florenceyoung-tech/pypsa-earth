"""Auditable results for the revised Nigeria study (PyPSA 0.30.x).

Recompute from solved networks every time. No hard-coded emissions efficiencies,
FX conversions, synthetic generation from load shedding, or stale metric cache.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import pypsa
import yaml

RENEWABLE = {"solar", "onwind", "offwind", "offwind-ac", "offwind-dc", "hydro", "ror"}
SHEDDING = {"load", "load shedding"}
NOMINAL = {"Generator": "p_nom", "StorageUnit": "p_nom", "Store": "e_nom", "Line": "s_nom", "Link": "p_nom", "Transformer": "s_nom"}


def canonical(value):
    """NetCDF JSON turns numeric dictionary keys into strings."""
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def validate_metadata(n, current):
    if canonical(n.meta.get("nigeria_study")) != canonical(current["nigeria_study"]):
        raise ValueError("Saved network differs from current study assumptions; rerun")
    keys = ("output_currency", "price_year", "exchange_rates", "discountrate", "discountrate_groups", "fuel", "efficiency", "price_year_factors", "included_technologies", "rooftop_share", "reference_year_hours")
    for key in keys:
        if canonical(n.meta.get("costs", {}).get(key)) != canonical(current["costs"][key]):
            raise ValueError(f"Saved cost setting {key} differs; rerun")


def processed_reporting_costs(n):
    """Reconstruct technology coefficients for stock-cost accounting only.

    Existing hydro has zero capital_cost in the optimisation network. A full-
    stock replacement-cost measure must value it explicitly from the same input.
    """
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from process_cost_data import load_costs
    config = n.meta["costs"]
    source = root / config["input_file"]
    if not source.is_file():
        raise FileNotFoundError(f"Stock-cost accounting requires the reviewed raw cost input: {source}")
    years = float(n.snapshot_weightings.objective.sum()) / float(config["reference_year_hours"])
    return load_costs(source, config, n.meta["electricity"]["max_hours"], years)


def dense(n, component, attr):
    return n.get_switchable_as_dense(component, attr)


def extract_metrics(n):
    if not np.isfinite(getattr(n, "objective", np.nan)) or n.generators_t.p.empty:
        raise ValueError("Network has no usable optimisation result")
    cfg = n.meta.get("nigeria_study", {})
    if not cfg.get("enabled"):
        raise ValueError("Use revised networks, not legacy runs")
    solver_result = n.meta.get("solver_result")
    if solver_result and solver_result.get("termination_condition") != "optimal":
        raise ValueError("Network does not have optimal solver termination")
    if n.stores.shape[0] or n.links.shape[0]:
        raise ValueError("This reporting boundary expects generators, StorageUnits and AC lines; review Stores/Links explicitly")
    w = n.snapshot_weightings.generators
    wo = n.snapshot_weightings.objective
    out = {"scenario": cfg["scenario"], "group": cfg["group"], "rate_basis": cfg["rate_basis"],
           "renewable_wacc": n.meta["costs"]["discountrate_groups"]["renewable"]["rate"],
           "gas_wacc": n.meta["costs"]["discountrate_groups"]["fossil"]["rate"],
           "gas_price": cfg["gas_usd_per_mmbtu"], "gas_quote_price_year": cfg.get("gas_quote_price_year", 2026), "gas_real_2024_usd_per_mwh": cfg.get("gas_real_2024_usd_per_mwh", np.nan), "objective_usd": float(n.objective)}
    if n.meta["costs"]["output_currency"] != "USD":
        raise ValueError("Expected real 2024 USD cost accounting")
    generation = n.generators_t.p.mul(w, axis=0).sum()
    shed = n.generators.carrier.isin(SHEDDING)
    primary = generation.loc[~shed].groupby(n.generators.loc[~shed, "carrier"]).sum()
    # Reservoir hydro is primary generation; batteries and pumped storage are not.
    hydro = n.storage_units.index[n.storage_units.carrier.isin({"hydro", "ror"})]
    discharge = n.storage_units_t.p_dispatch
    if len(hydro):
        if (n.storage_units_t.p_store.reindex(columns=hydro, fill_value=0).abs().max().max() > 1e-6):
            raise ValueError("Hydro charges from grid: split pumped energy before counting primary generation")
        hydro_energy = discharge[hydro].mul(w, axis=0).sum().groupby(n.storage_units.loc[hydro, "carrier"]).sum()
        primary = primary.add(hydro_energy, fill_value=0)
    q = float(primary.sum())
    for carrier, energy in primary.items():
        out[f"generation_{carrier}_twh"] = float(energy / 1e6)
    out["primary_generation_twh"] = q / 1e6
    out["renewable_share"] = float(primary.reindex(list(RENEWABLE), fill_value=0).sum() / q) if q else np.nan
    requested = float(dense(n, "Load", "p_set").mul(w, axis=0).sum().sum())
    physical_supply = n.generators_t.p.mul(n.generators.sign, axis=1).sum(axis=1) + n.storage_units_t.p.sum(axis=1)
    branch_loss = n.lines_t.p0.sum(axis=1) + n.lines_t.p1.sum(axis=1)
    branch_loss = branch_loss + n.transformers_t.p0.sum(axis=1) + n.transformers_t.p1.sum(axis=1)
    load_t = dense(n, "Load", "p_set").sum(axis=1)
    balance_residual = float((physical_supply - load_t - branch_loss).abs().max())
    if not np.isfinite(balance_residual) or balance_residual > max(.001, float(load_t.max()) * 1e-6):
        raise ValueError(f"Physical power balance fails: maximum residual {balance_residual} MW")
    out["power_balance_residual_mw"] = balance_residual
    signs = n.generators.loc[shed, "sign"]
    unserved = float((generation.loc[shed] * signs).sum())
    out.update(demand_twh=requested / 1e6, unserved_twh=unserved / 1e6,
               served_twh=(requested-unserved) / 1e6, unserved_share=unserved/requested)
    factor = n.generators.carrier.map(n.carriers.co2_emissions)
    if factor.isna().any():
        raise ValueError("Unspecified carrier emissions factor")
    eff = dense(n, "Generator", "efficiency")
    if (eff <= 0).any().any():
        raise ValueError("Nonpositive generator efficiency")
    out["emissions_mt"] = float(n.generators_t.p.div(eff).mul(factor, axis=1).mul(w, axis=0).sum().sum() / 1e6)
    caps = n.global_constraints.query("type == 'primary_energy' and carrier_attribute == 'co2_emissions'")
    out["cap_mt"] = float(caps.constant.min() / 1e6) if len(caps) else np.nan
    out["cap_shadow_usd_tco2"] = float(-caps.mu.iloc[0]) if len(caps) else np.nan
    if len(caps) and out["emissions_mt"] > out["cap_mt"] + 1e-5:
        raise ValueError("Reported emissions exceed effective CO2 cap")
    investment = 0.0
    replacement = 0.0
    replacement_adjustment = 0.0
    reporting_costs = None
    for component, attr in NOMINAL.items():
        table = n.df(component)
        if table.empty:
            continue
        opt = table[attr + "_opt"]
        ext = table[attr + "_extendable"]
        investment += float(((opt - table[attr]) * table.capital_cost).loc[ext].sum())
        stock_coeff = table.capital_cost.copy()
        if component == "StorageUnit":
            ids = table.index[table.carrier.isin({"hydro", "ror"}) & ~ext & table.p_nom.gt(0) & table.capital_cost.eq(0)]
            if len(ids):
                if reporting_costs is None:
                    reporting_costs = processed_reporting_costs(n)
                for name in ids:
                    carrier = table.at[name, "carrier"]
                    stock_coeff[name] = float(reporting_costs.at[carrier, "capital_cost"])
                replacement_adjustment += float((opt.loc[ids] * stock_coeff.loc[ids]).sum())
        replacement += float((opt * stock_coeff).sum())
        if component in {"Generator", "StorageUnit"}:
            physical = ~table.carrier.isin(SHEDDING)
            for carrier, ids in table.loc[physical].groupby("carrier").groups.items():
                out[f"capacity_{carrier}_gw"] = out.get(f"capacity_{carrier}_gw", 0) + float(opt.loc[ids].sum() / 1e3)
                # Existing extendable VRE may have a nonzero minimum. Count additions above stock.
                added = (opt - table[attr]).clip(lower=0).where(ext, 0)
                out[f"new_{carrier}_gw"] = out.get(f"new_{carrier}_gw", 0) + float(added.loc[ids].sum() / 1e3)
    gen_op = n.generators_t.p * dense(n, "Generator", "marginal_cost")
    penalty = float(gen_op.loc[:, shed].mul(wo, axis=0).sum().sum())
    operating = float(gen_op.mul(wo, axis=0).sum().sum())
    for attr, dispatch_attr in (("marginal_cost", "p_dispatch"), ("marginal_cost_storage", "state_of_charge"), ("spill_cost", "spill")):
        cost = dense(n, "StorageUnit", attr)
        panel = n.pnl("StorageUnit")[dispatch_attr].reindex(columns=cost.columns, fill_value=0)
        operating += float((panel * cost).mul(wo, axis=0).sum().sum())
    reconstructed = investment + operating
    residual = reconstructed - n.objective
    if abs(residual) > max(1., 1e-5 * abs(n.objective)):
        raise ValueError(f"Objective accounting differs by USD {residual:,.2f}; do not publish approximate costs")
    out.update(investment_annuity_usd=investment, operating_usd=operating-penalty,
               unserved_penalty_usd=penalty, objective_residual_usd=float(residual),
               planning_supply_cost_usd=reconstructed-penalty,
               replacement_system_cost_usd=replacement+operating-penalty,
               fixed_hydro_replacement_annuity_usd=replacement_adjustment)
    out["planning_cost_per_served_mwh"] = (reconstructed-penalty)/(requested-unserved) if requested > unserved else np.nan
    # Full-stock equivalent annual cost: explicitly NOT the optimisation objective.
    out["system_lcoe_usd_mwh"] = (replacement+operating-penalty)/q if q > 0 else np.nan
    batteries = n.storage_units.index[n.storage_units.carrier.eq("battery")]
    out["battery_energy_gwh"] = float((n.storage_units.loc[batteries, "p_nom_opt"] * n.storage_units.loc[batteries, "max_hours"]).sum()/1e3)
    out["battery_discharge_twh"] = float(discharge.reindex(columns=batteries, fill_value=0).mul(w, axis=0).sum().sum()/1e6)
    out["line_expansion_gw_km"] = float(((n.lines.s_nom_opt-n.lines.s_nom).clip(lower=0)*n.lines.length).sum()/1e3)
    vre = n.generators.index[n.generators.carrier.isin({"solar", "onwind", "offwind", "offwind-ac", "offwind-dc"})]
    potential = float(dense(n, "Generator", "p_max_pu")[vre].mul(n.generators.loc[vre, "p_nom_opt"], axis=1).mul(w, axis=0).sum().sum())
    curtailed = max(0., potential - generation.reindex(vre).sum())
    out["vre_curtailment_share"] = curtailed/potential if potential > 0 else 0.
    for carrier in ("CCGT", "OCGT"):
        ids = n.generators.index[n.generators.carrier.eq(carrier) & n.generators.p_nom_extendable]
        denom = float(n.generators.loc[ids, "p_nom_opt"].sum()*w.sum())
        out[f"new_{carrier}_utilisation"] = float(generation.reindex(ids).sum()/denom) if denom > 1e-3 else np.nan
    return out


def build_results(root, allow_partial=False):
    root = Path(root)
    manifest = json.loads((root / "configs/nigeria_study/manifest.json").read_text())
    rows, missing = [], []
    for entry in manifest:
        path = root / entry["network"]
        if not path.exists():
            missing.append(entry["scenario"])
            continue
        n = pypsa.Network(path)
        current = yaml.safe_load((root / entry["config"]).read_text())
        validate_metadata(n, current)
        row = extract_metrics(n)
        row["network_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        row["network_path"] = entry["network"]
        rows.append(row)
    if missing and not allow_partial:
        raise FileNotFoundError(f"Missing scenarios: {', '.join(missing)}. Finish runs, or explicitly use allow_partial=True for preliminary inspection.")
    if not rows:
        raise FileNotFoundError("No revised solved networks yet. Run B2 first.")
    df = pd.DataFrame(rows)
    # Missing technologies are zero, but missing scenarios are never zero-filled.
    quantity_cols = [c for c in df if c.startswith(("generation_", "capacity_", "new_")) and not c.endswith("utilisation")]
    df[quantity_cols] = df[quantity_cols].fillna(0)
    output = root / "analysis/output/nigeria_consistent"
    output.mkdir(parents=True, exist_ok=True)
    df.to_csv(output / "metrics.csv", index=False)
    (output / "coverage.json").write_text(json.dumps({"missing": missing, "available": df.scenario.tolist()}, indent=2))
    return df


def plot_results(df, output):
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"solar": "#e8ac22", "onwind": "#4a9a85", "hydro": "#337eae", "ror": "#78b6cf", "CCGT": "#735d78", "OCGT": "#b38b92", "battery": "#758453"}
    figures = []
    def save(fig, name):
        fig.tight_layout()
        fig.savefig(output / (name+".png"), dpi=220, bbox_inches="tight")
        fig.savefig(output / (name+".pdf"), bbox_inches="tight")
        figures.append(fig)
    sweep = df.loc[df.group.eq("sweep")].sort_values("renewable_wacc")
    if len(sweep):
        x = 100*sweep.renewable_wacc
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, prefix, ylabel in ((axes[0], "new_", "New capacity (GW)"), (axes[1], "generation_", "Primary generation (TWh)")):
            for tech, color in colors.items():
                suffix = "gw" if prefix == "new_" else "twh"
                col = f"{prefix}{tech}_{suffix}"
                if col in sweep and sweep[col].abs().sum() > 1e-8:
                    ax.plot(x, sweep[col], marker="o", label=tech, color=color)
            ax.set(xlabel="Renewable-group real WACC (%)", ylabel=ylabel)
            ax.legend(fontsize=8)
        save(fig, "01_wacc_capacity_generation")
        fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
        axes[0].plot(x, sweep.renewable_share*100, "o-")
        axes[0].axhline(50, color="gray", ls="--", label="National 50% benchmark")
        axes[0].set_ylabel("Renewable generation (%)")
        axes[0].legend(fontsize=7)
        axes[1].plot(x, sweep.planning_supply_cost_usd/1e9, "o-")
        axes[1].set_ylabel("Annual planning supply cost (USD bn)")
        axes[2].plot(x, sweep.emissions_mt, "o-")
        axes[2].axhline(8.8, color="gray", ls=":", label="Analytical allocation")
        axes[2].set_ylabel("Operational CO₂ (Mt)")
        axes[2].legend(fontsize=7)
        for ax in axes:
            ax.set_xlabel("Renewable-group real WACC (%)")
        save(fig, "02_wacc_policy_outcomes")
    selected = df.loc[df.scenario.isin(["B1", "B2", "B3", "D2", "P1", "P1D", "P2", "P3", "P4"])].set_index("scenario")
    if len(selected):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        selected[["investment_annuity_usd", "operating_usd", "unserved_penalty_usd"]].div(1e9).rename(columns={"investment_annuity_usd":"New investment + FOM coefficient", "operating_usd":"Operation", "unserved_penalty_usd":"Unmet-demand penalty"}).plot.bar(stacked=True, ax=axes[0], color=["#337eae", "#a2b8ba", "#bb5548"])
        axes[0].set_ylabel("Annual objective components (USD bn)")
        axes[0].legend(fontsize=7)
        selected.emissions_mt.plot.bar(ax=axes[1], color="#735d78")
        axes[1].set_ylabel("Operational CO₂ (Mt)")
        axes[1].axhline(8.8, color="gray", ls="--")
        save(fig, "03_scenario_costs_emissions")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    df.set_index("scenario").unserved_share.mul(100).plot.bar(ax=axes[0], color="#bb5548")
    axes[0].set_ylabel("Demand unserved (%)")
    df.set_index("scenario").battery_energy_gwh.plot.bar(ax=axes[1], color="#758453")
    axes[1].set_ylabel("Battery energy capacity (GWh)")
    save(fig, "04_adequacy_storage")
    return figures
