"""Build the final tables and figures from all revised solved networks."""
from pathlib import Path
import zipfile
import matplotlib
matplotlib.use("Agg")
from nigeria_results import build_results, plot_results


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "analysis/output/nigeria_consistent"
    df = build_results(root)
    plot_results(df, output / "figures")
    base = df.set_index("scenario").loc["B2"]
    comparison = df.loc[df.scenario.isin(["B2", "D2", "P1", "P1D", "P2", "P3", "P4", "S2a", "S2b"])].copy()
    comparison["cost_change_pct"] = 100 * (comparison.planning_supply_cost_usd / base.planning_supply_cost_usd - 1)
    comparison["emissions_change_mt"] = comparison.emissions_mt - base.emissions_mt
    comparison["renewable_change_pp"] = 100 * (comparison.renewable_share - base.renewable_share)
    comparison.to_csv(output / "policy_comparison.csv", index=False)
    archive = output.parent / "Nigeria_WACC_Results.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                stream.write(path, path.relative_to(output))
    print(f"RESULTS_READY: {archive}")
    print("Upload Nigeria_WACC_Results.zip to the chat for interpretation and chart review.")


if __name__ == "__main__":
    main()
