"""Regression checks on physical/financial invariants, including a solved LP."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pypsa
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "analysis"))
from nigeria_consistency import apply_nigeria_assumptions, convert_explicit_currency, real_rate
from build_nigeria_study import make_config, scenarios, MWH_PER_MMBTU
from nigeria_results import extract_metrics, plot_results
from add_co2_constraint import add_constraint


def template():
    return yaml.safe_load((ROOT / "scripts/scenarios/cap_exp_2030_split_wacc.yaml").read_text())


def config(code="B2"):
    return make_config(template(), next(r for r in scenarios() if r[0] == code))


def test_financing_and_fuel_units():
    assert real_rate(.1379, .02) == pytest.approx(.115588235294)
    a, b = config("C01"), config("C11")
    assert a["costs"]["discountrate"] == b["costs"]["discountrate"]
    assert a["costs"]["discountrate_groups"]["fossil"] == b["costs"]["discountrate_groups"]["fossil"]
    assert config("B2")["costs"]["fuel"]["gas"] == pytest.approx(10.96)
    assert config("P1")["costs"]["fuel"]["gas"] == pytest.approx(10.96 * 6 / 3.39)
    assert config("B2")["co2"]["limit"] is None
    assert config("D2")["co2"]["limit"] == 8.8e6


def test_explicit_currency_and_price_year():
    costs = pd.DataFrame({"value": [100., 100., 25.], "unit": ["USD/kW", "EUR/kW", "years"], "currency_year": [2024, 2024, np.nan]})
    out = convert_explicit_currency(costs, config()["costs"])
    assert out.value.tolist() == pytest.approx([100, 108.24, 25])
    costs.loc[0, "currency_year"] = 2020
    with pytest.raises(ValueError, match="rebased"):
        convert_explicit_currency(costs, config()["costs"])


def gas_costs():
    return pd.DataFrame({"efficiency": [.53, .37, 1.], "marginal_cost": [30., 40., 10.], "co2_emissions": [.2, .2, .2]}, index=["CCGT", "OCGT", "gas"])


def test_boundary_gas_and_effective_time_series():
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-01-01", periods=2, freq="h"))
    for bus in ("A", "B", "island"):
        n.add("Bus", bus)
    n.add("Line", "AB", bus0="A", bus1="B", x=.1, s_nom=100)
    n.add("Load", "main", bus="A", p_set=100)
    n.add("Load", "remote", bus="island", p_set=5)
    n.add("Generator", "old", bus="A", carrier="CCGT", p_nom=100)
    n.add("Generator", "new", bus="A", carrier="CCGT", p_nom_extendable=True, p_max_pu=[.306, .306])
    cfg = config()
    cfg["nigeria_study"]["annual_demand_twh"] = .0003
    audit = apply_nigeria_assumptions(n, cfg, gas_costs())
    assert audit["excluded_buses"] == ["island"]
    assert "remote" not in n.loads.index
    assert audit["annual_demand_mwh"] == pytest.approx(300)
    assert n.generators.at["old", "p_max_pu"] == .306
    assert n.generators.at["new", "p_max_pu"] == 1.
    assert (n.generators_t.p_max_pu["new"] == 1.).all()
    assert n.generators.at["new", "efficiency"] == .53
    assert n.carriers.at["CCGT", "co2_emissions"] == .2


def solved_network():
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-01-01", periods=2, freq="h"))
    n.add("Carrier", "AC")
    n.add("Bus", "A", carrier="AC")
    for carrier, co2 in (("solar", 0), ("CCGT", .2), ("battery", 0), ("hydro", 0), ("load shedding", 0)):
        n.add("Carrier", carrier, co2_emissions=co2)
    n.add("Load", "demand", bus="A", p_set=[10, 10])
    n.add("Generator", "solar", bus="A", carrier="solar", p_nom_extendable=True, capital_cost=2, p_max_pu=[1, 0], marginal_cost=.01)
    n.add("Generator", "gas", bus="A", carrier="CCGT", p_nom_extendable=True, capital_cost=1, efficiency=.5, marginal_cost=50)
    n.add("Generator", "shed", bus="A", carrier="load shedding", p_nom=1000, marginal_cost=1000)
    n.add("StorageUnit", "battery", bus="A", carrier="battery", p_nom_extendable=True, capital_cost=2, max_hours=2, efficiency_store=.9, efficiency_dispatch=.9, cyclic_state_of_charge=True)
    n.add("StorageUnit", "hydro", bus="A", carrier="hydro", p_nom=1, max_hours=2, inflow=.5, p_min_pu=0, efficiency_store=0, cyclic_state_of_charge=True)
    n.add("GlobalConstraint", "cap", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=1.)
    from run_nigeria_study import merge
    n.meta = merge(yaml.safe_load((ROOT / "config.default.yaml").read_text()), config())
    status, condition = n.optimize(solver_name="highs", solver_options={"threads": 1})
    assert (status, condition) == ("ok", "optimal")
    return n


def test_solved_accounting_storage_and_export(tmp_path):
    n = solved_network()
    row = extract_metrics(n)
    assert row["battery_discharge_twh"] > 0
    assert row["primary_generation_twh"] > row["served_twh"]  # storage losses
    assert row["renewable_share"] == pytest.approx(1.)
    assert row["generation_hydro_twh"] > 0
    assert row["unserved_twh"] == pytest.approx(0, abs=1e-10)
    assert row["objective_residual_usd"] == pytest.approx(0, abs=1e-6)
    path = tmp_path / "solved.nc"
    n.export_to_netcdf(path)
    saved = extract_metrics(pypsa.Network(path))
    assert saved["system_lcoe_usd_mwh"] == pytest.approx(row["system_lcoe_usd_mwh"])
    # Exercise plotting using actual solved LP output, not fabricated thesis results.
    df = pd.DataFrame([row, dict(row, scenario="C01", group="sweep")])
    plot_results(df, tmp_path / "figures")
    assert len(list((tmp_path / "figures").glob("*.pdf"))) == 4


def test_load_shedding_not_generation():
    n = solved_network()
    n.generators_t.p.loc[:, "shed"] = 1.
    n.loads_t.p_set.loc[:, "demand"] += 1.
    # Maintain objective consistency in this deliberate post-solve metric fixture.
    n.objective += 2000
    row = extract_metrics(n)
    assert row["unserved_twh"] == pytest.approx(2e-6)
    assert row["renewable_share"] == pytest.approx(1.)
    assert row["unserved_penalty_usd"] == pytest.approx(2000)


def test_cap_uses_fuel_factor_once(tmp_path):
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-01-01", periods=1, freq="h"))
    n.add("Bus", "A")
    n.add("Carrier", "CCGT")
    n.add("Carrier", "load shedding")
    n.add("Generator", "gas", bus="A", carrier="CCGT", p_nom=10, efficiency=.5, marginal_cost=10)
    n.add("Generator", "shed", bus="A", carrier="load shedding", p_nom=10, marginal_cost=1000)
    n.add("Load", "demand", bus="A", p_set=10)
    path, target, costs = tmp_path / "in.nc", tmp_path / "out.nc", tmp_path / "costs.csv"
    n.export_to_netcdf(path)
    gas_costs().to_csv(costs)
    add_constraint(path, target, 2., costs)
    capped = pypsa.Network(target)
    assert capped.carriers.at["CCGT", "co2_emissions"] == .2
    capped.optimize(solver_name="highs", solver_options={"threads": 1})
    assert capped.generators_t.p["gas"].sum() == pytest.approx(5.)
    assert capped.generators_t.p["shed"].sum() == pytest.approx(5.)


def test_actual_cost_processor(tmp_path):
    from process_cost_data import load_costs, annuity
    from run_nigeria_study import merge
    techs = ["solar-utility", "solar-rooftop", "offwind", "onwind", "hydro", "ror", "PHS", "OCGT", "CCGT", "gas", "battery storage", "battery inverter", "hydrogen storage tank", "fuel cell", "electrolysis", "csp-tower", "HVAC overhead"]
    rows = []
    for tech in techs:
        for parameter, value, unit in [("investment", 100., "EUR/kW"), ("FOM", 2., "%/year"), ("VOM", 1., "USD/MWh"), ("efficiency", .9, "per unit"), ("lifetime", 20., "years"), ("fuel", 0., "USD/MWh"), ("CO2 intensity", .2 if tech == "gas" else 0., "tCO2/MWh")]:
            rows.append(dict(technology=tech, parameter=parameter, value=value, unit=unit, currency_year=2024))
    path = tmp_path / "costs.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    cfg = merge(yaml.safe_load((ROOT / "config.default.yaml").read_text()), config())
    costs = load_costs(path, cfg["costs"], cfg["electricity"]["max_hours"], 1.)
    assert costs.at["CCGT", "efficiency"] == .53
    assert costs.at["CCGT", "marginal_cost"] == pytest.approx(1+10.96/.53)
    assert costs.at["CCGT", "co2_emissions"] == .2
    expected = (annuity(20, real_rate(.1379, .02))+.02)*100000*1.0824
    assert costs.at["solar-utility", "capital_cost"] == pytest.approx(expected)
    assert costs.at["battery", "capital_cost"] == pytest.approx(7*expected)
    assert costs.at["HVAC overhead", "discount rate"] == pytest.approx(real_rate(.1468, .02))


def test_local_brownfield_split_then_availability():
    import ast
    import logging
    from types import SimpleNamespace
    tree = ast.parse((ROOT / "scripts/prepare_network.py").read_text())
    block = next(node for node in ast.walk(tree) if isinstance(node, ast.If) and "split_existing" in ast.unparse(node.test))
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-01-01", periods=2, freq="h"))
    n.add("Bus", "A")
    n.add("Load", "demand", bus="A", p_set=10.)
    n.add("Generator", "fleet", bus="A", carrier="CCGT", p_nom=100., p_nom_extendable=True, p_max_pu=[.306, .306])
    cfg = config()
    exec(compile(ast.Module(body=[block], type_ignores=[]), "local_brownfield", "exec"),
         dict(n=n, pd=pd, snakemake=SimpleNamespace(config=cfg), logger=logging.getLogger(__name__)))
    assert not n.generators.at["fleet", "p_nom_extendable"]
    assert n.generators.at["fleet", "p_nom"] == 100.
    assert n.generators.at["fleet new", "p_nom"] == 0.
    apply_nigeria_assumptions(n, cfg, gas_costs())
    assert n.generators.at["fleet", "p_max_pu"] == .306
    assert n.generators.at["fleet new", "p_max_pu"] == 1.
    assert cfg["solving"]["options"]["load_shedding"] == 10.
    assert cfg["electricity"]["split_existing"]


def test_reviewed_source_full_cost_pipeline():
    from process_cost_data import load_costs
    from run_nigeria_study import merge
    source = ROOT / "data/nigeria_study/costs_source.csv"
    original_bytes = source.read_bytes()
    cfg = merge(yaml.safe_load((ROOT / "config.default.yaml").read_text()), config())
    costs = load_costs(source, cfg["costs"], cfg["electricity"]["max_hours"], 1.)
    assert "DAC" not in costs.index
    assert "solar-rooftop" not in costs.index
    assert "electrolysis" not in costs.index
    assert costs.at["solar", "investment"] == 814000.
    assert costs.at["solar", "capital_cost"] == costs.at["solar-utility", "capital_cost"]
    assert costs.at["HVAC overhead", "investment"] == pytest.approx(400 * 126.08/99.39 * 1.0824)
    assert costs.at["hydro", "investment"] == pytest.approx(2000000 * 126.08/99.39 * 1.0824)
    assert costs.at["hydro", "FOM"] == 1.0
    assert costs.at["gas", "fuel"] == pytest.approx(10.96)
    assert costs.at["CCGT", "marginal_cost"] == pytest.approx(4.74+10.96/.53)
    assert costs.at["OCGT", "marginal_cost"] == pytest.approx(4.74+10.96/.37)
    assert source.read_bytes() == original_bytes


def test_price_rebasing_precedes_fx_and_does_not_change_ratios():
    costs = pd.DataFrame({"value": [400., 2., .53], "unit": ["EUR/MW/km", "%/year", "per unit"], "currency_year": [2013, 2013, float("nan")]})
    out = convert_explicit_currency(costs, config()["costs"])
    assert out.at[0, "value"] == pytest.approx(400 * 126.08/99.39 * 1.0824)
    assert out.at[0, "currency_year"] == 2024
    assert out.at[1, "value"] == 2.
    assert out.at[2, "value"] == .53


def test_saved_metadata_year_keys_are_equivalent():
    import copy
    from nigeria_results import validate_metadata
    from types import SimpleNamespace
    cfg = config()
    saved = copy.deepcopy(cfg)
    saved["costs"]["price_year_factors"] = {"EUR": {"2013": 126.08/99.39}}
    validate_metadata(SimpleNamespace(meta=saved), cfg)
    saved["costs"]["price_year_factors"]["EUR"]["2013"] = 9.0
    with pytest.raises(ValueError, match="price_year_factors"):
        validate_metadata(SimpleNamespace(meta=saved), cfg)


def test_existing_renewable_stock_is_preserved():
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-01-01", periods=2, freq="h"))
    n.add("Bus", "A")
    n.add("Load", "demand", bus="A", p_set=10.)
    n.add("Generator", "solar", bus="A", carrier="solar", p_nom=20., p_nom_min=0., p_nom_max=100., p_nom_extendable=True)
    audit = apply_nigeria_assumptions(n, config(), gas_costs())
    assert n.generators.at["solar", "p_nom_min"] == 20.
    assert audit["preserved_existing_renewable_mw"] == 20.


def test_full_stock_cost_values_existing_hydro():
    n = solved_network()
    row = extract_metrics(n)
    assert row["fixed_hydro_replacement_annuity_usd"] > 0
    assert row["replacement_system_cost_usd"] > row["planning_supply_cost_usd"]
    assert n.storage_units.at["hydro", "capital_cost"] == 0.


def test_time_limit_is_not_accepted_as_optimal():
    import ast, logging
    from types import SimpleNamespace
    tree = ast.parse((ROOT / "scripts/solve_network.py").read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "solve_network")
    env = dict(logger=logging.getLogger(__name__), opts=[], extra_functionality=lambda *a: None)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "solver_guard", "exec"), env)
    n = SimpleNamespace(lines=SimpleNamespace(s_nom_extendable=pd.Series([False])), meta={}, optimize=lambda **kw: ("ok", "time_limit"))
    with pytest.raises(RuntimeError, match="optimal termination"):
        env["solve_network"](n, {"nigeria_study": {"enabled": True}}, {"solver": {"name": "highs", "options": None}, "options": {"skip_iterations": True}})
