# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Heterogeneous Graph Transformer (HGT) pipeline that predicts marriage edges in
the **CMGPD-LN** historical Chinese genealogy panel (ICPSR DS0001). The
research question driving the design: how much do **maternal** kinship edges
(`r_ms`, `r_md`) contribute to predictability above a patrilineally-fractured
graph? The pipeline trains on a graph with maternal edges ablated, then
evaluates against an unablated copy to quantify the recall@1 delta.

## Commands

All commands run from the project root.

```bash
# Full pipeline (skips cached stages):
python -m src.main --stage all
# Individual stages:
python -m src.main --stage data       # .rda → cleaned parquet → HeteroData graph cache
python -m src.main --stage features   # attach person/household/community/banner features
python -m src.main --stage train      # train HGT + MarriageScorer; write checkpoints/best.pt
python -m src.main --stage eval       # write runs/<ts>/metrics.json + per_cohort.csv

# Useful flags:
python -m src.main --stage all --smoke    # restrict to 1849-1854 cohorts (cheap dev loop)
python -m src.main --stage data --force   # rebuild caches even if they exist

# Tests:
pytest tests/test_smoke.py -v
pytest tests/test_smoke.py::test_subgraph_strictly_before_t -v   # single test
```

The `data` stage requires **R** (`Rscript`) to convert the DS0001 `.rda` file
to gzipped CSV (the binary format pyreadr cannot read at this scale). Set
`R_EXECUTABLE` if `Rscript` is not on `PATH`. Auxiliary tables DS0009
(grain prices) and DS0011 (disasters) load directly via `pyreadr`.

## Architecture

### Graph schema
Defined in `src/config.py`. Four node types — `person`, `household`,
`community`, `banner` — and nine edge types in `EDGE_TYPES`. **Every edge
type listed in `config.EDGE_TYPES` must remain present in `graph.metadata()`
even after ablation**, because `HGTConv` registers per-edge-type linear
projections from the metadata snapshot. `ablate_maternal_edges()` therefore
replaces the `r_ms` / `r_md` `edge_index` with empty `(2, 0)` tensors rather
than deleting the keys.

### Pipeline stages (numbered files in `src/`)
- **`stage0_data.py`** — load DS0001, clean IDs/codes, build the
  `HeteroData` graph with kinship edges (split paternal/maternal by child
  sex) and timed `r_hw` marriage edges. Writes `data/processed/hgt_pipeline/graph.pt`.
- **`stage1_features.py`** — attach `x_sex`, `x_relationship`,
  `x_continuous`, `x_occupational` to person nodes plus `.x` to other node
  types. Continuous features include macro covariates (grain prices, era,
  disasters) from `temporal_indicators.py`.
- **`stage2_split.py`** — `compute_cohort_split` bins `r_hw` edges by
  marriage year into train (≤1855) / val (≤1879) / test (≤1909).
  `ablate_maternal_edges` zeros maternal edge tensors in place (keys
  preserved). `mask_target_edges` returns a shallow copy with specified
  `r_hw` pairs removed.
- **`stage3_temporal.py`** — `subgraph_at_year(g, t)` returns a copy with
  `edge_time < t` enforced on every edge type. Static edges (timed `0`,
  e.g. `r_hc`, `r_cb`) are kept unconditionally. Subgraphs are cached on
  disk under `SUBGRAPH_CACHE_DIR` keyed by `(t, sha1(drop_pairs))`.
- **`src/model/hgt.py`** — `HGT` encoder (per-type embedders → stacked
  `HGTConv` with residual+LayerNorm+dropout) and `MarriageScorer`
  (MLP over `[h_m, h_w, |h_m-h_w|, h_m*h_w]`).
- **`train.py`** — per-epoch loop: shuffle training years, batch
  `BATCH_YEARS` years per optimizer step, build `subgraph_at_year(t,
  drop=train[t] ∪ all_val ∪ all_test)`, encode persons, score
  positive + within-cohort negative pairs with BCE. Validates with
  Hungarian recall@1; checkpoints best to `checkpoints/best.pt`.
- **`evaluate.py`** — runs three passes: train cohort (overfit sanity),
  ablated test (main number), unablated test (upper bound). The
  `ablation_delta_recall@1` is the headline result.

### Key invariants (verified by tests; preserve when refactoring)
1. **No future leakage.** All edges in `subgraph_at_year(g, t)` satisfy
   `edge_time < t`. The training loop additionally drops the year's own
   target pairs and globally drops all val + test pairs from the message-
   passing graph during encoding.
2. **Ablate, don't delete.** `ablate_maternal_edges` empties tensors but
   leaves keys; `HGTConv` requires every edge type in metadata.
3. **Share tensors, copy containers.** `subgraph_at_year` and
   `mask_target_edges` use `copy.copy(graph)` — shallow — because node
   features are huge. Only the edge tensors that change are replaced.
4. **Within-cohort negatives.** `sample_negatives` draws from the same-year
   marriage cohort. Cross-year negatives are too easy and inflate metrics.
5. **CMGPD `SEX` coding is preserved as 1=Female, 2=Male** (raw convention).

### Configuration
`src/config.py` is the single source of truth for paths, year boundaries,
feature lists, model hyperparameters, and the ablated edge set. Do not
hardcode these elsewhere.

### Caches
Successive runs reuse:
- `data/processed/hgt_pipeline/ds0001_raw_from_r.csv.gz` (R export)
- `data/processed/hgt_pipeline/ds0001_clean.parquet`
- `data/processed/hgt_pipeline/graph.pt` (graph + id_maps)
- `data/processed/hgt_pipeline/subgraphs/sg_<t>_<hash>.pt`
- `checkpoints/best.pt`
- `runs/<timestamp>/metrics.json`

Use `--force` on `data`/`features` stages to invalidate. Run
`stage3_temporal.clear_subgraph_cache()` after any schema change that
affects edge contents.
