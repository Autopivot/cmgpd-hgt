"""Disaggregate the headline metrics by cohort era.

Reads `per_cohort.csv` (and optionally `metrics.json`) from a run directory and
prints / saves a breakdown of recall@1 weighted by cohort size, grouped into
era buckets that reveal the underlying structure the macro average hides.

The original analysis showed test recall@1 = 0.77 was driven mostly by the
catch-up 1903 cohort (12k marriages, recall=0.73) drowning out the smaller
regular cohorts (recall = 0.88–0.92). This script makes that explicit.

Usage:
    python scripts/analyze_cohorts.py                                  # latest run
    python scripts/analyze_cohorts.py --run runs/20260425_193821/      # specific run
    python scripts/analyze_cohorts.py --pass test --pass train         # which passes
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

# Era bucketing reflects what showed up in the first run's metrics:
#   pre-1780     — earliest panel years, sparse ancestry, recall = 0.30–0.45
#   1780-1855    — mature train regime, recall climbs from 0.55 to 0.89
#   1856-1879    — val cohorts (24-year span)
#   1882-1888    — regular test cohorts (close to the train regime)
#   1903         — catch-up cohort after the 1888-1900 registration gap
#   1906-1909    — late post-gap cohorts
ERA_BUCKETS = [
    ("pre-1780",     1700, 1779),
    ("1780-1855",    1780, 1855),
    ("1856-1879",    1856, 1879),
    ("1882-1888",    1882, 1888),
    ("1903",         1903, 1903),
    ("1906-1909",    1906, 1909),
]


def _bucket(year: int) -> str:
    for name, lo, hi in ERA_BUCKETS:
        if lo <= year <= hi:
            return name
    return "OTHER"


def _weighted(df: pd.DataFrame, value: str) -> float:
    n = df["n_men"]
    if n.sum() == 0:
        return float("nan")
    return float((df[value] * n).sum() / n.sum())


def analyze(per_cohort: pd.DataFrame, passes: list[str]) -> pd.DataFrame:
    """Group per-cohort rows by era × pass, weighted by n_men."""
    df = per_cohort[per_cohort["pass"].isin(passes)].copy()
    df["era"] = df["year"].apply(_bucket)
    rows = []
    for (pass_name, era), g in df.groupby(["pass", "era"]):
        rows.append({
            "pass": pass_name,
            "era": era,
            "n_cohorts": len(g),
            "n_marriages": int(g["n_men"].sum()),
            "min_year": int(g["year"].min()),
            "max_year": int(g["year"].max()),
            "hungarian_recall@1_weighted": _weighted(g, "hungarian_recall@1"),
            "hungarian_recall@1_unweighted": float(g["hungarian_recall@1"].mean()),
            "top1_recall_weighted": _weighted(g, "top1_recall"),
            "top5_recall_weighted": _weighted(g, "top5_recall"),
        })
    return pd.DataFrame(rows).sort_values(["pass", "min_year"]).reset_index(drop=True)


def _latest_run() -> Path | None:
    runs = [p for p in config.RUNS_DIR.iterdir() if p.is_dir()]
    runs = [p for p in runs if (p / "per_cohort.csv").exists()]
    if not runs:
        return None
    return sorted(runs)[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=None,
                    help="run directory containing per_cohort.csv (default: latest)")
    ap.add_argument("--pass", dest="passes", action="append", default=None,
                    help="which pass(es) to include: train, test, test_ablated, "
                         "test_unablated. Can be repeated. Default: all in file.")
    args = ap.parse_args()

    run_dir = args.run or _latest_run()
    if run_dir is None:
        sys.exit("no run directory with per_cohort.csv found")
    per_cohort_path = run_dir / "per_cohort.csv"
    print(f"analyzing: {per_cohort_path}")

    per_cohort = pd.read_csv(per_cohort_path)
    if "pass" not in per_cohort.columns:
        sys.exit("per_cohort.csv missing 'pass' column")

    passes = args.passes or sorted(per_cohort["pass"].unique())
    summary = analyze(per_cohort, passes)

    out_path = run_dir / "cohort_analysis.csv"
    summary.to_csv(out_path, index=False)
    print(f"wrote {out_path}")

    # Pretty print
    print()
    with pd.option_context("display.max_rows", None, "display.width", 160,
                           "display.float_format", lambda x: f"{x:.4f}"):
        print(summary.to_string(index=False))

    # Quick callout of what the macro average hides
    test_passes = [p for p in passes if "test" in p]
    if test_passes:
        print()
        print("-" * 70)
        print("Per-era test breakdown (Hungarian recall@1 weighted by n_marriages):")
        for p in test_passes:
            df_p = summary[summary["pass"] == p]
            print(f"\n  pass = {p}")
            for _, r in df_p.iterrows():
                print(f"    {r['era']:<12} n={int(r['n_marriages']):>6}  "
                      f"recall@1 = {r['hungarian_recall@1_weighted']:.4f}")
        print("-" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
