"""Matplotlib style, palette, labels."""
import matplotlib as mpl
import matplotlib.pyplot as plt


PALETTE = {
    "solar":        "#f4a300",
    "onwind":       "#3d9970",
    "offwind":      "#2e86ab",
    "hydro":        "#1e6fa8",
    "ror":          "#5fa8d3",
    "PHS":          "#7fb3d5",
    "CCGT":         "#c0392b",
    "OCGT":         "#e67e22",
    "oil":          "#5d4037",
    "coal":         "#424242",
    "biomass":      "#8bc34a",
    "battery":      "#9b59b6",
    "load":         "#000000",
    "load shedding": "#000000",
    "nuclear":      "#16a085",
    "geothermal":   "#af7ac5",
    "csp":          "#f1c40f",
}


def apply_style():
    mpl.rcParams.update({
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "legend.frameon": False,
        "figure.autolayout": False,
    })


def save(fig, name: str, outdir="analysis/output/figures"):
    """Save a figure as both PDF and PNG."""
    import os
    os.makedirs(outdir, exist_ok=True)
    pdf = f"{outdir}/{name}.pdf"
    png = f"{outdir}/{name}.png"
    fig.savefig(pdf)
    fig.savefig(png)
    plt.close(fig)
    return pdf
