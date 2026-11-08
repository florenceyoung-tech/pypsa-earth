# Cost-file review and corrections

The supplied raw file contains 215 rows covering 58 technologies. Its `year=2030` column is the planning horizon; `currency_year` is the monetary price year. The corrected
electricity workflow selects 18 relevant technologies before cost conversion.
Unrelated technologies such as DAC, heating and hydrogen conversion no longer
block this electricity-only study. The original CSV is preserved byte-for-byte
as `data/nigeria_study/costs_source.csv`; the existing `data/costs_gas_339.csv` is
not edited or replaced.

## What the actual file establishes

- Solar utility, onshore wind, gas plant and battery investment costs are already
  labelled 2024 USD and include rebasing calculations in their descriptions.
  The workflow does not deflate these entries again.
- Hydro, run-of-river and transmission capital costs remain in 2013 EUR.
  These are rebased to 2024 EUR before converting to USD.
- The inherited solar cost formula mixed 14% rooftop with 86% utility-scale
  solar. The rooftop cost was an older 2013 input. Since the study models
  utility-scale solar, `rooftop_share` is now explicitly zero. Solar investment
  therefore uses the supplied 814 USD2024/kW utility-scale value.
- FOM percentages, efficiencies and lifetimes are ratios or technical assumptions
  and are not multiplied by price indices.
- The raw discount-rate descriptions incorrectly call the Hatton reference
  values real. They are overridden by the documented nominal-to-real conversion
  in each scenario. The raw source file is retained as evidence, not silently
  relabelled.

## Gas price: correction to the earlier diagnosis

The source file already adjusts a 3.39 USD/MMBtu quote stated in 2026 prices
to 10.96 USD2024/MWh of fuel. Its description includes the factor 0.94716.
The earlier diagnosis that 10.96 necessarily represented a unit-conversion
error was incorrect: it omitted that price-year adjustment.

The revised baseline preserves 10.96 USD2024/MWh. The 6.00 USD/MMBtu case is
defined on the same quote-price basis and uses:

```text
high-price fuel cost = 10.96 * (6.00 / 3.39)
                     = 19.3982301 USD2024/MWh_fuel
```

At the common HHV efficiencies and source VOM of 4.74 USD2024/MWh_e:

| Technology | Baseline marginal cost (USD2024/MWh_e) | High-gas-price case |
|---|---:|---:|
| CCGT, efficiency 0.53 | 25.4192 | 41.3404 |
| OCGT, efficiency 0.37 | 34.3616 | 57.1676 |

The gas quote's 2026 price year is recorded separately from the model's 2024
cost basis. The source's 2025/2026-to-2024 adjustment factors are retained as
author-provided assumptions. Their calculations can be checked arithmetically;
the file does not identify the underlying index series, so they should not be
described as independently verified inflation observations. This particularly
matters for a full-year 2026 deflator before the year is complete.

## Historical euro costs

The Eurostat all-items HICP annual-average series used is `prc_hicp_aind`,
`geo=EA20`, `coicop=CP00`, `unit=INX_A_AVG`. Its annual index values are:

| Year | Index |
|---|---:|
| 2013 | 99.39 |
| 2024 | 126.08 |

The 2013-to-2024 factor is `126.08 / 99.39`, followed by the already documented
2024 exchange-rate assumption of 1.0824 USD per EUR. For example:

```text
AC transmission: 400 EUR2013/(MW km)
    * (126.08 / 99.39) * 1.0824
    = approximately 549.23 USD2024/(MW km)
```

This is a general-price adjustment, not a new equipment quotation or a
technology-specific cost forecast. Keeping those distinctions explicit is
adequate for the financing focus of the study. A snapshot of the returned
Eurostat data accompanies this update for reproducibility.

## Source checks and limitations

The official IRENA page confirms publication of *Renewable power generation
costs in 2025* in July 2026. The official Lazard 2026 report confirms the cited
new gas capex ranges: 1,100–1,650 USD/kW for gas peaking and 1,450–2,100 USD/kW
for combined cycle; see its printed page 28 (PDF page index 27). The upper
ends used in this model are study assumptions, not demonstrated Nigerian
minimum construction costs.

The arithmetic in the main capex descriptions is consistent within rounding:
1550*0.97247 is approximately 1507.3 for wind; 837*0.97247 is approximately
814.0 for solar; 1650*0.94716 is approximately 1562.8 for OCGT; and
2100*0.94716 is approximately 1989.0 for CCGT. This does not independently
validate every source-table entry or the choice of deflator.

Battery input values are retained. At a four-hour duration they imply
98.6 + 152.1/4 = 136.625 USD2024/kWh. At the configured six-hour duration,
investment is 152.1 + 6*98.6 = 743.7 USD2024/kW. The component lifetimes
remain 20 years for the inverter and 15 years for energy storage, each
annualised separately. The six-hour design is an extrapolation of the
component model, not a new six-hour empirical quote.

Sources:

- Eurostat API (retrieved 29 October 2026):
  https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_aind?geo=EA20&coicop=CP00&unit=INX_A_AVG&lang=EN
- IRENA publication page:
  https://www.irena.org/Publications/2026/Jul/Renewable-Power-Generation-Costs-in-2025
- Lazard official report:
  https://lazard.com/media/kcfconhf/lazards-lcoeplus_vf.pdf

## Verification

All 27 revised scenarios passed cost preflight using the actual supplied CSV.
Fourteen model regression tests passed, including the reviewed source-file pipeline,
historical-price rebasing, untouched dimensionless ratios, gas marginal costs,
emissions constraints, battery accounting and the local brownfield split.
These checks do not constitute a full Nigeria network rerun or validation of
every original empirical assumption.
