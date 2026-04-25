"""CLI entry point for the HGT marriage-prediction pipeline.

Usage:
  python -m src.main --stage all|data|features|train|eval [--smoke] [--force]

Stages:
  data     — load .rda → clean → build_graph → save graph cache
  features — attach features (person/household/community/banner)
  train    — train HGT + scorer; save best checkpoint by val recall@1
  eval     — load checkpoint; produce runs/<ts>/metrics.json
  all      — run the four in order (skipping cached stages unless --force)
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def stage_data(force: bool = False) -> None:
    """Build graph.pt. --force rebuilds the graph but reuses the upstream
    clean parquet if it exists (the clean parquet has its own provenance
    and is expensive to recompute from the .rda)."""
    from .stage0_data import build_graph, clean_dataframe, load_rda, save_graph
    if config.GRAPH_CACHE_PATH.exists() and not force:
        log.info("graph cache exists; skipping (use --force to rebuild)")
        return
    if config.CLEAN_PARQUET_PATH.exists():
        log.info("loading cleaned parquet")
        import pandas as pd
        df = pd.read_parquet(config.CLEAN_PARQUET_PATH)
    else:
        df = clean_dataframe(load_rda())
        config.CLEAN_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(config.CLEAN_PARQUET_PATH, index=False)
        log.info("wrote cleaned parquet → %s", config.CLEAN_PARQUET_PATH)
    graph, id_maps, df = build_graph(df)
    save_graph(graph, id_maps)


def stage_features(force: bool = False) -> None:
    from .stage0_data import load_graph, save_graph
    from .stage1_features import attach_features
    import pandas as pd

    graph, id_maps = load_graph()
    has_features = (
        hasattr(graph["person"], "x_continuous")
        and graph["person"].x_continuous.numel()
        and hasattr(graph, "macro_table")  # per-cohort macro table required after schema v2
    )
    if has_features and not force:
        log.info("features already attached; skipping (use --force to recompute)")
        return
    df = pd.read_parquet(config.CLEAN_PARQUET_PATH)
    attach_features(graph, df, id_maps)
    save_graph(graph, id_maps)


def stage_train(smoke: bool = False, ablate: bool = True) -> None:
    from .train import train
    train(smoke=smoke, ablate=ablate)


def stage_eval(smoke: bool = False, ablate: bool = True) -> None:
    from .evaluate import evaluate
    evaluate(smoke=smoke, ablate=ablate)


def main() -> int:
    parser = argparse.ArgumentParser(description="HGT marriage-prediction pipeline")
    parser.add_argument("--stage", choices=["all", "data", "features", "train", "eval"],
                        default="all")
    parser.add_argument("--smoke", action="store_true",
                        help="restrict to 1849–1854 marriage cohorts for a quick run")
    parser.add_argument("--force", action="store_true",
                        help="rebuild caches in data/features stages")
    parser.add_argument("--no-ablate", action="store_true",
                        help="train/eval on the FULL graph (keep r_ms, r_md). "
                        "Required for the proper ablation comparison: train both modes, "
                        "then compare via scripts/compare_ablation.py")
    args = parser.parse_args()
    ablate = not args.no_ablate

    if args.stage in ("all", "data"):
        stage_data(force=args.force)
    if args.stage in ("all", "features"):
        stage_features(force=args.force)
    if args.stage in ("all", "train"):
        stage_train(smoke=args.smoke, ablate=ablate)
    if args.stage in ("all", "eval"):
        stage_eval(smoke=args.smoke, ablate=ablate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
