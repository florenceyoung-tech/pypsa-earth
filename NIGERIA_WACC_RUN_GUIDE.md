# Nigeria WACC study: update and rerun guide

This update was merged with the local code archive you supplied, including your brownfield split.
It creates a separate 2030 run set and a new results notebook. Legacy scenarios,
notebooks and result files remain available. No 2040 expansion or new capital-structure
estimation is introduced. The code has local regression tests, including small
solved PyPSA networks. The full Nigeria rerun requires your local cost, plant,
weather and network inputs; those data are not included in this package.

## 1. Install the update merged with your local code

Download and extract `Nigeria_WACC_Sweep_Update.zip` in Downloads. Open your
existing VS Code Terminal in the project root, activate the pypsa-earth conda
environment, and run:

```bash
python ~/Downloads/Nigeria_WACC_Sweep_Update/install_update.py --run-all
```

This checks your code against the archive you supplied, backs up every replaced
file, installs the merged code, generates scenarios, checks your raw cost file,
previews the Snakemake workflow, runs a corrected B2, then the full scenario set and results extraction. It preserves your current Git
branch and does not commit or push anything. The original notebook remains intact.

If your code has changed since the upload, it stops rather than overwriting
those changes. Send the Terminal output if that happens. The source update may
install successfully while a later input check fails; the message distinguishes
these outcomes. A failed price-year check requires source-data review, not simply
changing a year label.

If you want only installation and input checks, omit `--run-all`.
Use `--install-only` to replace source files without running any model step.
The optional `--cores 4` sets the number of Snakemake cores.

The dated backup folder is printed in Terminal. It holds originals and a restore
manifest. Repeating the installer recognises already-installed files.

This package has not been pushed to GitHub. No Git patch commands are needed.
Do not retry the earlier patch. The installed `scripts/prepare_network.py` retains
your local brownfield split before applying the Nigeria consistency settings.

Use your existing working PyPSA-Earth environment. Model tests used PyPSA 0.30.3.
Fourteen regression tests passed, including a test of your local brownfield block.
If you want to run the tests yourself and pytest is available:

```bash
python -m pytest test/test_nigeria_study.py -q
```

The small tests use HiGHS; the full scenarios retain your Gurobi configuration.

## 2. Generate the revised scenarios

The reviewed source CSV is supplied at `data/nigeria_study/costs_source.csv`. It is a byte-for-byte copy of your uploaded input. The previous cost file and symlink remain untouched. It uses the original long-format columns.

```bash
python scripts/build_nigeria_study.py --cost-file data/nigeria_study/costs_source.csv
python scripts/run_nigeria_study.py --scenarios B2 --preflight-only
```

If your raw file has a different name, pass that path to `--cost-file` instead.
The supplied source snapshot contains mixed price years. The loader rebases the selected 2013 EUR monetary rows using the documented factor and then converts currency. Entries already in 2024 USD remain unchanged. Do not simply change a price-year label. See COST_REVIEW.md for the gas-price correction and source limitations.

The generator writes `configs/nigeria_study/` and its manifest. Change assumptions
in `scripts/build_nigeria_study.py` and regenerate; do not hand-edit a generated
YAML without updating the manifest. To change the common inflation assumption:

```bash
python scripts/build_nigeria_study.py --cost-file data/nigeria_study/costs_source.csv --inflation 0.02
```

Two percent is an explicit long-run USD inflation assumption, not observed
Nigerian project inflation or a claim about Hatton's own deflator. The Fed's 2%
long-run inflation objective provides context, not a project-specific estimate.
The additional 4% case tests sensitivity to this assumption.

## 3. Run ONE scenario first

```bash
python scripts/run_nigeria_study.py --scenarios B2 --cores 4 --dry-run
python scripts/run_nigeria_study.py --scenarios B2 --cores 4
```

The dry run previews the workflow. It does not solve it. The second command runs
the differentiated-financing baseline. Increase cores only if appropriate for
your computer and solver licence. Logs are in `logs/nigeria_consistent/`.

Expected output:

```text
results/nigeria_consistent_B2/networks/elec_s_10_ec_lcopt_1h.nc
```

Open `analysis/Nigeria_WACC_results.ipynb` with your PyPSA environment's Python
kernel. Temporarily set `ALLOW_PARTIAL = True` and run the notebook. Check:

- requested demand is 78 TWh;
- `nigeria_audit` lists the removed disconnected location(s), original excluded
  demand and scaling factor;
- existing CCGT/OCGT have maximum fractions 0.306/0.217; extendable gas has 1.0;
- effective CCGT/OCGT efficiencies are 0.53/0.37 on the stated HHV basis;
- new real WACC is approximately 11.5588% for renewables and 12.4314% for gas;
- annual hydro output is plausible against the retained calibration (the old
  0.476/0.756 claim is not a second applied correction);
- unmet demand is separately reported and small enough for the intended comparison;
- objective reconstruction residual is effectively zero.

The notebook stops on missing emissions factors or material cost/cap mismatches.
These checks do not prove that the source data are correct, but prevent several
silent inconsistencies in the previous analysis.

## 4. Run the capped case, then the complete set

```bash
python scripts/run_nigeria_study.py --scenarios D2 --cores 4
python scripts/run_nigeria_study.py --cores 4
```

The full set contains 27 configurations: three baselines, eleven sweep points
(including 17% nominal), three cap cases, five gas/policy cases, two battery cases
and three additional sensitivities. B2 and C06 intentionally share assumptions:
one is the comparison baseline and one places the point in the sweep.

Completed up-to-date runs can be skipped by Snakemake. The runner stops at failures.
It does not delete results, swap cost-file symlinks or automatically remove locks.
If Snakemake reports a stale lock, first establish that no other workflow is
running; use your normal Snakemake unlock procedure only then.

If Gurobi is unavailable, change the builder's solver name to `highs` and solver
options to `highs-default`, regenerate and repeat the dry run. Do not mix solver
changes with claims that old results have been reproduced exactly.

## 5. Produce the results

In `analysis/Nigeria_WACC_results.ipynb`, set `ALLOW_PARTIAL = False` and select
Restart Kernel and Run All. Outputs go to `analysis/output/nigeria_consistent/`:

- `metrics.csv`: recalculated results with solved-network hashes;
- `coverage.json`: explicit scenario coverage;
- `policy_comparison.csv`: changes relative to B2;
- `figures/`: publication-use PNG and PDF versions of the four figure groups.

The notebook deliberately does not display saved old charts. Missing scenarios
are not replaced by zero values. Do not mix `analysis/final_analysis.ipynb` or
the old `analysis/metrics.csv` with these runs.

## Changes and rationale

| Issue | Implemented treatment |
|---|---|
| Nominal rates on real costs | Main cases use `(1+nominal)/(1+inflation)-1`; original direct-rate convention is an explicit stress case. |
| Currency | Real 2024 USD throughout. EUR inputs use 1 EUR = 1.0824 USD, the 2024 annual reference average. USD inputs remain USD. Only selected electricity technologies are processed; 2013 EUR rows use the documented Eurostat price factor before FX conversion. Other unexplained price years stop processing. |
| Transmission WACC moving with renewables | Transmission stays at your local 14.68% nominal-equivalent rate, converted consistently to real; unlisted technologies use the common 10% comparator. These are assumptions, not measured transmission WACC. |
| Gas availability | At the final prepared-network stage, historical derating proxies apply only to fixed gas units; new gas is 100% available. An 85% new-gas case tests this simplifying assumption. |
| Derating provenance | 0.306/0.217 remain historical utilisation-based operational proxies. They are not renamed measured availability. |
| Gas efficiency | Explicit 0.53/0.37 HHV assumptions in processed costs and effective network; both fuel costs and CO2 use the same efficiency. The prior `conventional_efficiency` config field was unused. |
| Gas price conversion | The source already rebases the 3.39 USD/MMBtu quote to 10.96 USD2024/MWh fuel. Retain that baseline and scale by 6/3.39 for the high-price case (19.3982 USD2024/MWh fuel). Do not deflate it twice. |
| Emissions constraint | Carrier-level fuel CO2 intensity; PyPSA divides by generator efficiency once. No fallback electrical emissions factor is silently substituted. |
| 8.8 Mt | Retained rounded analytical allocation. The 12.4 Mt baseline needs a traceable source before presenting the cap as evidence-based. This is not an official grid target. |
| Isolated node | Remove components outside the largest connected component, then allocate 78 TWh over retained loads in proportion to their existing profiles. Stop if excluded input demand exceeds 10%. No physical line is invented. |
| Hydro | Keep committed EIA normalization and multiplier 1.268. Record that setting and inspect output; do not apply the untraced 0.476/0.756 correction as well. |
| Leap year | The 8,784 weather snapshots have total weights of 8,760 hours. Use 8,760 as the annual cost reference; demand and the annual emissions cap use the same weighted year. |
| Numerical perturbations | Disable random marginal-cost noise for these scenarios. |
| Unmet demand | Keep a finite penalty of USD 10,000/MWh as a modelling assumption, report any unmet demand and its penalty separately; this is not an estimated Nigerian value of lost load. |
| Results accounting | Exclude storage discharge from primary generation, exclude load shedding from generation/capacity, include hydro StorageUnits, use solved efficiencies and distinguish planning cost from full-stock equivalent annual cost. |

The 10% and 20% comparison cases change generation and battery financing together;
transmission stays at the locally selected common 14.68% nominal-equivalent rate. The main sweep continues to
vary the renewable group, including battery financing, while gas is fixed. S2a/S2b
separate battery financing. A battery WACC is not claimed to come directly from
Hatton's generation-technology dataset.

The new-gas site set remains the existing eligible gas locations. No new gas
pipeline siting model, detailed outage simulation, tax cash-flow model, endogenous
capital structure, network remapping or 2040 pathway is added.

## What still needs evidence, rather than another code change

1. The source and derivation of the 2018 grid-only 12.4 MtCO2 baseline. Until
   supplied, interpret D1–D3 as illustrative cap scenarios.
2. The actual raw cost CSV and its inflation rebasing record. Preflight checks
   metadata and calculations, not the truth of a cited source.
3. The hydro adjustment history. Use the committed implementation as the record
   for this version; review the first rerun's annual hydro output before publication.
4. Historical validation: the old 2024 notebook remains unchanged. If its published
   metrics are retained, recompute them on its stated connected boundary and do not
   describe 2030 demand profiles as observed 2024 TCN demand. The 2030 code update
   does not independently validate inflows or hourly dispatch.

## Updating the methodology after rerunning

Report the new real rates, USD price basis, explicit inflation assumption, fixed
transmission financing, gas efficiency and availability conventions, connected-grid
demand allocation, cap provenance and exact cost metrics. State that annual
generation is primary generation; battery throughput is a separate result.
Describe the policy cases as assumed financing changes, not causally estimated
effects of policy instruments. Keep the 2040 extension outside the paper's scope.

## Sources for conventions

- Hatton et al.: https://www.nature.com/articles/s41597-025-06177-0
- PyPSA 0.30.3 optimisation and primary-energy constraint:
  https://docs.pypsa.org/v0.30.3/user-guide/optimal-power-flow.html
- Federal Reserve 2024 longer-run 2% inflation objective:
  https://www.federalreserve.gov/monetarypolicy/files/FOMC_LongerRunGoals_202401.pdf
- Central Bank of Malta 2024 annual average EUR exchange rates:
  https://mtca.gov.mt/docs/default-source/documents/legislative-developments/2025/2024-annual-average-exchange-rates-pdf.pdf?sfvrsn=4eefd906_2
- Nigeria NDC 3.0 registry: https://unfccc.int/node/649915


The baseline review and final corrections are documented in B2_REVIEW.md. The full-run installer produces analysis/output/Nigeria_WACC_Results.zip for upload after the sweep.
