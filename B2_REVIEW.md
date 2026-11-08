# Review of the uploaded B2 solved network

Reviewed input: `B2_solved.nc`, SHA256
`37d2ccbd5aa330fd8e6f4b18cee590bb4eda28bd107d96d530a9ad9e480f7535`.

The uploaded run uses 9 connected buses, 10 lines and 8,784 weather snapshots.
Snapshot weights sum to 8,760 hours. It excludes the disconnected NG1 0 bus
and allocates 78 TWh demand to the connected system.

## Confirmed results from the uploaded file, before the final corrections

| Quantity | Result |
|---|---:|
| Requested demand | 78.0000 TWh |
| Demand served | 77.999963 TWh |
| Unmet demand | 37.11 MWh, or approximately 0.0000476% |
| CCGT generation | 57.6675 TWh |
| OCGT generation | 10.7949 TWh |
| Hydro generation | 8.4280 TWh |
| Solar generation | 1.1096 TWh |
| Renewable share of primary generation | 12.2277% |
| Direct CO2 emissions | 24.9747 Mt |
| Optimisation objective | 3.443075 billion USD2024 |
| Planning supply cost excluding unmet-demand penalty | 3.442704 billion USD2024 |
| New CCGT capacity | 5.5537 GW |
| Battery and wind additions | Numerically negligible |

The hourly global power-balance residual is below 0.000001 MW. Cost
reconstruction differs from the stored objective by approximately 0.003 USD.
The baseline has no CO2 cap, as intended. Gas fuel intensity is 0.181
tCO2/MWh_fuel; effective CCGT/OCGT efficiencies are 0.53/0.37. Existing gas
has 0.306/0.217 maximum-output fractions; new gas has 1.0. Renewable and gas
reference WACC are 11.5588% and 12.4314% real.

## Corrections made after examining the actual network

1. **Retain existing renewable stock.** Existing solar totalled 164.658 MW, but
   most sites had zero investment lower bounds and the solution could remove
   them. The final preparation step now sets the renewable investment minimum
   at least equal to starting capacity. Existing gas remains fixed as before.
2. **Use the saved annual weighting.** The 8,784 snapshots are already normalised
   to 8,760 weighted hours. The prior 8,784 cost reference applied a second
   factor of 8760/8784 to annual costs. The final reference is 8,760. This removes
   an approximately 0.27% annual-capital-cost discrepancy.
3. **Compare saved metadata consistently.** NetCDF JSON stores the 2013 price-year
   dictionary key as text. The results reader now normalises keys before checking
   assumptions; a true factor change still fails the check.
4. **Value hydro in the optional full-stock cost measure.** The optimisation
   network stores zero capital cost for fixed hydro. The optional full-stock
   replacement-cost accounting now reconstructs hydro's coefficient from the
   reviewed input, rather than treating it as free. This does not alter dispatch
   costs or the optimisation objective. Planning cost and full-stock equivalent
   annual cost remain distinct quantities.
5. **Require solver completion.** Future study runs must terminate optimally
   before export. Each scenario is checked for metadata consistency, physical
   balance, fleet retention, emissions compliance and objective reconciliation.

The reported uploaded B2 numbers above are a review record; the corrected B2
will supersede them. Do not combine this baseline with corrected sweep results.

## Validation and scope

Fourteen regression tests pass, including existing-solar retention, saved
metadata keys, fixed-hydro cost accounting and rejection of a solver time limit.
All 27 revised scenario cost preflights pass with the supplied raw CSV.

A separate full-size HiGHS re-solve was attempted here and reached its 240-second
time limit. Its solution was not accepted or used for reported results. The
installer reruns corrected B2 with your configured Gurobi solver, then proceeds
through the sweep only after the result checks pass.

Hydro profiles retain the committed normalization and 1.268 multiplier. The
8.428 TWh result is a model dispatch outcome, not a new validation against TCN.
New CCGT utilisation is close to 100%; this follows the full-availability
assumption. The existing S_gas85 scenario tests an 85% new-gas availability case.
Neither case is claimed to measure the reliability of a specific Nigerian plant.

The scope remains a 2030 financing and policy sensitivity study. No additional
transmission-detail model, plant-level outage model or 2040 pathway is added.
