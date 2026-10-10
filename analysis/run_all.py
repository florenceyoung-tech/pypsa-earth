#!/usr/bin/env python3
"""
Run all analyses: build manifest, extract metrics, produce all figures and tables.

Usage:
    cd /Users/fowfloi/Documents/pypsa-earth
    python analysis/run_all.py [--force]

Outputs:
    analysis/output/figures/*.pdf, *.png
    analysis/output/tables/*.csv
    analysis/output/README.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd

from lib.io import build_metrics
from lib.manifest import write_manifest
from lib.style import apply_style
import figures
import tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Rebuild metrics cache from scratch")
    args = ap.parse_args()

    apply_style()

    print("=== Building scenario manifest ===")
    manifest = write_manifest()
    print(f"    {len(manifest)} scenarios")

    print("\n=== Extracting metrics ===")
    metrics = build_metrics(force=args.force)
    print(f"    {len(metrics)} rows")

    print("\n=== Producing figures ===")
    fig_outputs = []
    for mod in figures.all_figures():
        try:
            path = mod.make(metrics)
            fig_outputs.append((mod.__name__, path))
            print(f"    OK  {mod.__name__}")
        except Exception as e:
            print(f"    !!  {mod.__name__}: {e}")

    print("\n=== Producing tables ===")
    tbl_outputs = []
    for mod in tables.all_tables():
        try:
            path = mod.make(metrics)
            tbl_outputs.append((mod.__name__, path))
            print(f"    OK  {mod.__name__}")
        except Exception as e:
            print(f"    !!  {mod.__name__}: {e}")

    print(f"\n=== Done: {len(fig_outputs)} figures, {len(tbl_outputs)} tables ===")
    print("    See analysis/output/README.md")


if __name__ == "__main__":
    main()
