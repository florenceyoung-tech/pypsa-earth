import yaml
from pathlib import Path

# Delivered gas price: $3.39/MMBtu (NMDPRA regulated + transport)
# Thermal = 3.39 * 0.293071 * 0.7532 = 0.748 EUR/MWh_th
# VOM: CCGT 3.20 EUR/MWh, OCGT 3.77 EUR/MWh  (Lazard new-build)
# Efficiency: CCGT 0.58, OCGT 0.41 (fleet weighted)

def mc_ccgt(fuel_eur, vom=3.20, eta=0.58):
    return round(vom + fuel_eur / eta, 2)

def mc_ocgt(fuel_eur, vom=3.77, eta=0.41):
    return round(vom + fuel_eur / eta, 2)

# $3.39/MMBtu primary price
fuel_339 = 3.39 * 0.293071 * 0.7532
GAS_MC_339 = {"CCGT": mc_ccgt(fuel_339), "OCGT": mc_ocgt(fuel_339)}
print(f"$3.39: CCGT={GAS_MC_339['CCGT']}, OCGT={GAS_MC_339['OCGT']}")

# $6.00/MMBtu sensitivity
fuel_600 = 6.00 * 0.293071 * 0.7532
GAS_MC_600 = {"CCGT": mc_ccgt(fuel_600), "OCGT": mc_ocgt(fuel_600)}
print(f"$6.00: CCGT={GAS_MC_600['CCGT']}, OCGT={GAS_MC_600['OCGT']}")

# WACC points
WACC_POINTS = [0.07, 0.09, 0.11, 0.1379, 0.18, 0.27]
NDC_POINTS  = [0.10, 0.1379, 0.27]

with open("configs/cap_exp_2030_split_wacc.yaml") as f:
    base = yaml.safe_load(f)

def apply_gas_mc(cfg, mc):
    cfg["costs"]["marginal_cost"]["CCGT"] = mc["CCGT"]
    cfg["costs"]["marginal_cost"]["OCGT"] = mc["OCGT"]

def apply_wacc(cfg, wacc):
    cfg["costs"]["discountrate_groups"]["renewable"]["rate"] = wacc
    cfg["costs"]["discountrate_groups"]["hydro"]["rate"]     = wacc
    cfg["costs"]["discountrate_groups"]["battery"]["rate"]   = wacc
    cfg["costs"]["discountrate_groups"]["fossil"]["rate"]    = 0.1468

# 6 unconstrained WACC sweep configs
for wacc in WACC_POINTS:
    tag = f"{int(round(wacc * 10000)):04d}"
    cfg = yaml.safe_load(yaml.safe_dump(base))
    cfg["run"]["name"] = f"nigeria_2030_wacc_{tag}"
    apply_wacc(cfg, wacc)
    apply_gas_mc(cfg, GAS_MC_339)
    cfg.pop("co2", None)
    out = Path(f"configs/config.nigeria.2030_wacc_{tag}.yaml")
    with open(out, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    print(f"Wrote {out.name}")

# 3 NDC WACC sweep configs
for wacc in NDC_POINTS:
    tag = f"{int(round(wacc * 10000)):04d}"
    cfg = yaml.safe_load(yaml.safe_dump(base))
    cfg["run"]["name"] = f"nigeria_2030_wacc_{tag}_ndc"
    apply_wacc(cfg, wacc)
    apply_gas_mc(cfg, GAS_MC_339)
    cfg["co2"] = {"limit": 8.8e6, "base": 0.0}
    out = Path(f"configs/config.nigeria.2030_wacc_{tag}_ndc.yaml")
    with open(out, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    print(f"Wrote {out.name}")

# 2 gas price sensitivity configs (at Hatton WACC 13.79%)
for price_key, mc in [("600", GAS_MC_600)]:
    cfg = yaml.safe_load(yaml.safe_dump(base))
    cfg["run"]["name"] = f"nigeria_2030_wacc_1379_gas_{price_key}"
    apply_wacc(cfg, 0.1379)
    apply_gas_mc(cfg, mc)
    cfg.pop("co2", None)
    out = Path(f"configs/config.nigeria.2030_wacc_1379_gas_{price_key}.yaml")
    with open(out, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    print(f"Wrote {out.name}")

print("\nAll configs generated.")