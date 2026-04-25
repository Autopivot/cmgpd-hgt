"""Audit context-density per training cohort to explain the recall elbow.

Hypothesis: pre-1780 train cohorts have low Hungarian recall@1 because at the
candidate marriage year t, the encoder sees a graph where the men and women
have very few visible kinship + sibling + household edges. Reasons:

  - the panel starts in 1749, so people marrying in 1753 have parents born
    before any record exists; FATHER_ID strings may exist but the parent's
    PERSON_ID isn't in id_maps if they were never observed in the registers;
  - r_sib and r_hh edges accumulate over time, so the early subgraph is
    structurally thin;
  - communities and lineages stabilize over generations, so the average
    "context degree" of a man/woman in the cohort grows with calendar time.

This script walks each train (and test) cohort year, builds the causal
subgraph used at training time, and reports the average degree of cohort
men and women across all relevant edge types. Output: a CSV that should
show degrees climbing with year and matching the recall climb.

Usage:
    python scripts/audit_early_cohorts.py [--device cuda|cpu] [--limit N]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.stage0_data import load_graph  # noqa: E402
from src.stage2_split import ablate_maternal_edges, compute_cohort_split  # noqa: E402
from src.stage3_temporal import subgraph_at_year  # noqa: E402


# Per-relation: which axis points at the cohort person.
#   "in"  → cohort person is the destination (e.g. r_fs: father → son, son is dst)
#   "out" → cohort person is the source      (e.g. r_hh: person → household)
#   "any" → bidirectional, count either side  (r_sib is added both ways already)
EDGE_AUDIT = [
    # (relation, side_for_men,  side_for_women, total_node_type_for_minlength)
    ("r_fs", "in",  None, "person"),  # only meaningful for sons
    ("r_fd", None, "in", "person"),   # only meaningful for daughters
    ("r_ms", "in",  None, "person"),  # only meaningful for sons
    ("r_md", None, "in", "person"),   # only meaningful for daughters
    ("r_sib", "any", "any", "person"),
    ("r_hh", "out", "out", "person"),
    ("r_cb", "out", "out", "person"),
]


def _degree(graph, persons: torch.Tensor, edge_type, side: str, n_nodes: int) -> np.ndarray:
    """Count edges of `edge_type` incident on each cohort person on the given side."""
    ei = graph[edge_type].edge_index
    if ei.numel() == 0:
        return np.zeros(persons.size(0), dtype=np.int64)
    if side == "in":
        idx = ei[1]
    elif side == "out":
        idx = ei[0]
    elif side == "any":
        idx = torch.cat([ei[0], ei[1]])
    else:
        raise ValueError(side)
    counts = torch.bincount(idx, minlength=n_nodes)
    return counts[persons].cpu().numpy()


def audit_cohort(graph, year: int, men: list[int], women: list[int],
                 drop_pairs: set) -> dict:
    sg = subgraph_at_year(graph, year, drop_pairs=drop_pairs, use_cache=False)
    n_persons = int(sg["person"].num_nodes)
    persons_m = torch.tensor(men, dtype=torch.long)
    persons_w = torch.tensor(women, dtype=torch.long)

    row: dict = {"year": int(year), "n_men": len(men), "n_women": len(women)}
    for rel, side_m, side_w, _ntype in EDGE_AUDIT:
        et = ("person", rel, "person") if rel != "r_hh" and rel != "r_cb" else (
            ("person", rel, "household") if rel == "r_hh" else ("person", rel, "banner")
        )
        if side_m is not None:
            deg_m = _degree(sg, persons_m, et, side_m, n_persons)
            row[f"men_{rel}_mean"]   = float(deg_m.mean())   if deg_m.size else 0.0
            row[f"men_{rel}_zero%"]  = float((deg_m == 0).mean() * 100) if deg_m.size else 0.0
        if side_w is not None:
            deg_w = _degree(sg, persons_w, et, side_w, n_persons)
            row[f"women_{rel}_mean"]  = float(deg_w.mean())  if deg_w.size else 0.0
            row[f"women_{rel}_zero%"] = float((deg_w == 0).mean() * 100) if deg_w.size else 0.0
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="only audit the first N train years (debugging)")
    ap.add_argument("--no-ablate", action="store_true",
                    help="audit the unablated graph (keep r_ms, r_md)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    print("loading graph …")
    graph, _ = load_graph()
    if not args.no_ablate:
        ablate_maternal_edges(graph)
    split = compute_cohort_split(graph)

    drop_global = split["all_val_pairs"] | split["all_test_pairs"]

    rows = []
    train_years = sorted(split["train"].keys())
    test_years = sorted(split["test"].keys())
    if args.limit:
        train_years = train_years[: args.limit]

    for label, years_list, pairs_dict in [
        ("train", train_years, split["train"]),
        ("test",  test_years,  split["test"]),
    ]:
        for y in years_list:
            t0 = time.perf_counter()
            pairs = pairs_dict[y]
            men = sorted({h for h, _, _ in pairs})
            women = sorted({w for _, w, _ in pairs})
            drop = set(((h, w) for h, w, _ in pairs)) | drop_global
            row = audit_cohort(graph, y, men, women, drop)
            row["pass"] = label
            rows.append(row)
            print(f"  {label} {y}: M={len(men):>5} W={len(women):>5}  "
                  f"({time.perf_counter() - t0:.1f}s)")

    df = pd.DataFrame(rows)
    out = args.out or (config.RUNS_DIR / f"audit_early_cohorts_{'unablated' if args.no_ablate else 'ablated'}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nwrote {out}")

    # Summary: focus on the columns most relevant to the recall elbow
    key_cols = [
        "pass", "year", "n_men",
        "men_r_fs_mean", "men_r_sib_mean", "men_r_hh_mean",
        "women_r_fd_mean", "women_r_sib_mean", "women_r_hh_mean",
        "women_r_fd_zero%",
    ]
    key_cols = [c for c in key_cols if c in df.columns]
    print("\nKey context-density columns (mean degree per cohort person):")
    with pd.option_context("display.max_rows", None, "display.width", 160,
                           "display.float_format", lambda x: f"{x:.2f}"):
        print(df[key_cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
