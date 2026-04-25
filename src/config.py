"""Configuration constants for the HGT marriage-prediction pipeline.

Single source of truth for paths, splits, feature lists, model hyperparameters.
All other modules import from here; do not hardcode paths or thresholds elsewhere.

CMGPD SEX coding (raw): 1 = Female, 2 = Male. We preserve that convention.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

RAW_DATA_PATH = DATA_DIR / "raw" / "DS0001" / "21766-0001-Data.rda"
RAW_GRAIN_PATH = DATA_DIR / "raw" / "DS0009" / "27063-0009-Data.rda"
RAW_DISASTER_PATH = DATA_DIR / "raw" / "DS0011" / "27063-0011-Data.rda"

RAW_CSV_CACHE_PATH = DATA_DIR / "processed" / "hgt_pipeline" / "ds0001_raw_from_r.csv.gz"
CLEAN_PARQUET_PATH = DATA_DIR / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"
GRAIN_PARQUET_PATH = DATA_DIR / "processed" / "hgt_pipeline" / "grain_prices.parquet"
DISASTER_PARQUET_PATH = DATA_DIR / "processed" / "hgt_pipeline" / "disasters.parquet"
GRAPH_CACHE_PATH = DATA_DIR / "processed" / "hgt_pipeline" / "graph.pt"
SUBGRAPH_CACHE_DIR = DATA_DIR / "processed" / "hgt_pipeline" / "subgraphs"

CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"
RUNS_DIR = PROJECT_ROOT / "runs"

# Separate checkpoint files per training condition.
# An ablated-trained model has untrained projections for r_ms/r_md, so
# evaluating it on the unablated graph produces meaningless deltas.
# Always pair `best_ablated.pt` with the ablated graph and
# `best_unablated.pt` with the full graph.
CKPT_ABLATED   = CHECKPOINT_DIR / "best_ablated.pt"
CKPT_UNABLATED = CHECKPOINT_DIR / "best_unablated.pt"

R_EXPORT_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "export_rda.R"
R_EXECUTABLE = os.environ.get("R_EXECUTABLE") or shutil.which("Rscript")

# ── Year horizon and cohort split ──────────────────────────────────────
MIN_YEAR = 1749
MAX_YEAR = 1909
TRAIN_END_YEAR = 1855  # inclusive — marriages in years <= this are train
VAL_END_YEAR = 1879    # inclusive — train_end < year <= val_end is val
TEST_END_YEAR = 1909   # inclusive — val_end < year <= test_end is test

# ── Graph schema ───────────────────────────────────────────────────────
NODE_TYPES = ["person", "household", "community", "banner"]

# Order matters only for logging readability.
EDGE_TYPES = [
    ("person", "r_hw", "person"),
    ("person", "r_fs", "person"),  # father→son      (paternal, kept)
    ("person", "r_fd", "person"),  # father→daughter (paternal, kept)
    ("person", "r_ms", "person"),  # mother→son      (maternal, ABLATED)
    ("person", "r_md", "person"),  # mother→daughter (maternal, ABLATED)
    ("person", "r_sib", "person"),
    ("person", "r_hh", "household"),
    ("household", "r_hc", "community"),
    ("person", "r_cb", "banner"),
]

# Edge types zeroed out at the start of training (and inference) to simulate
# a patrilineally-fractured genealogy. The keys remain in graph.metadata() so
# HGTConv keeps the per-edge-type projections — they just receive empty input.
ABLATE_EDGES = [
    ("person", "r_ms", "person"),
    ("person", "r_md", "person"),
]

# ── Cleaning ───────────────────────────────────────────────────────────
MISSING_CODES = [-1, -2, -3, -4, -9, -99, "NA", "", None]

# ── Feature definitions ────────────────────────────────────────────────
# Person-level continuous features (constant or causal up to cutoff_year).
# AGE_IN_SUI was removed because it depends on the YEAR of the person's
# latest observation, which under the current pipeline is the snapshot year
# (≤ TEST_END_YEAR), not the cohort year — so the model received the
# person's POST-marriage age. The model can recover age info from
# BIRTHYEAR + cohort_year_z (in the per-cohort macro vector) if needed.
CONTINUOUS_FEATURES = [
    "BIRTHYEAR",
]
# Per-year macro covariates. NOT stored as static person features; instead
# build_temporal_indicator_table → macro_table is attached to the graph as
# a (n_years, K) lookup, and subgraph_at_year(t) stashes the row for year
# (t-1) on the subgraph as person.x_macro for the encoder to broadcast.
# This keeps macro features causally aligned with the cohort year being
# scored, instead of leaking the snapshot year's macro state.
MACRO_FEATURES = [
    "cohort_year_z",
    "grain_price_z",
    "grain_price_yoy",
    "era_id",
    "disaster_flag",
]
OCCUPATIONAL_COLUMNS = ["POSITION", "TITLE", "SALARY"]
CATEGORICAL_FEATURES = {"RELATIONSHIP": {"vocab_size": 64}}

# Dynasty boundaries: (era_id, start_year_inclusive, name).
# era_id assigned by bisect; year < first start gets era_id 0 (Qianlong block).
DYNASTY_BOUNDARIES = [
    (0, 1736, "Qianlong"),
    (1, 1796, "Jiaqing"),
    (2, 1821, "Daoguang"),
    (3, 1851, "Xianfeng"),
    (4, 1862, "Tongzhi"),
    (5, 1875, "Guangxu"),
    (6, 1909, "Xuantong"),
]

# ── Model ──────────────────────────────────────────────────────────────
HIDDEN = 128
NUM_LAYERS = 2
HEADS = 4
DROPOUT = 0.2

# ── Training ───────────────────────────────────────────────────────────
LR = 1e-3
WEIGHT_DECAY = 1e-2
EPOCHS = 30
BATCH_YEARS = 4   # number of cohort-years processed per optimizer step
NEG_PER_POS = 4
GRAD_CLIP = 1.0
SEED = 0

# ── Evaluation ─────────────────────────────────────────────────────────
RECALL_AT_K = [1, 5, 10]
