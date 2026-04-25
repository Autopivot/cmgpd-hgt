# cmgpd-hgt

Heterogeneous Graph Transformer (HGT) for marriage edge prediction in
the **CMGPD-LN** (China Multi-Generational Panel Dataset – Liaoning,
ICPSR 27063 / 21766) historical genealogy panel. Predicts husband–wife
edges (`r_hw`) within per-year marriage cohorts, with per-cohort
Hungarian decoding to enforce the closed-world bipartite constraint.

The driving research question: *how much do maternal kinship edges
(`r_ms`, `r_md`) contribute to predictability above a patrilineally-fractured
graph?* Empirically, with `r_hw` edges present and a depth-2 HGT, the answer
turns out to be ≈ 0 — see [Findings](#findings) below.

## Pipeline

```
DS0001.rda ─┐
DS0009.rda ─┼─► clean.parquet ─► HeteroData graph ─┐
DS0011.rda ─┘                                       │
                                                    ▼
                              attach person/household/community/banner features
                                                    │
                                                    ▼
                       cohort-year split + maternal-edge ablation (optional)
                                                    │
                                                    ▼
                        per-year causal subgraphs (edge_time < t)
                                                    │
                                                    ▼
                                  HGT encoder (2 layers, hidden=128)
                                                    │
                                                    ▼
                       MarriageScorer MLP over [h_m, h_w, |Δ|, h_m·h_w]
                                                    │
                                                    ▼
                  per-cohort Hungarian decode → recall@1 / top-k / AUC
```

## Layout

```
src/
  config.py             single source of truth (paths, splits, feature lists, hparams)
  stage0_data.py        load CMGPD .rda → clean → build HeteroData
  stage1_features.py    attach features to all node types
  stage2_split.py       cohort split, maternal-edge ablation, target-edge masking
  stage3_temporal.py    per-year causal subgraph + on-disk cache
  temporal_indicators.py  grain-price + disaster + dynasty macro covariates (DS0009/DS0011)
  sampling.py           within-cohort negative sampler
  model/
    hgt.py              HGT encoder + MarriageScorer
  train.py              training loop with Hungarian validation
  evaluate.py           pair-level + per-cohort metrics
  main.py               python -m src.main --stage [data|features|train|eval|all]

scripts/
  export_rda.R              R helper for .rda → .csv.gz export
  compare_ablation.py       proper ablated-vs-unablated model comparison
  analyze_cohorts.py        disaggregate metrics by era (pre-1780 / regular / catch-up / late)
  audit_early_cohorts.py    per-cohort context-density audit (parent / sibling / household degrees)

tests/
  test_smoke.py         unit checks + end-to-end smoke (GPU-gated)
```

## Setup

Requires Python 3.11 with CUDA-enabled PyTorch.

```bash
conda create -n cmgpd-hgt python=3.11
conda activate cmgpd-hgt
pip install -r requirements.txt
```

R is required only if loading from `.rda` (DS0001 export); the project
caches the parsed CSV / parquet so this is a one-time prerequisite. Set
`R_EXECUTABLE` env var if `Rscript` is not on `PATH`.

ICPSR data is **not redistributed** — fetch DS0001 (21766), DS0009, DS0011
yourself and place the `.rda` files at the paths in `src/config.py`:
- `data/raw/DS0001/21766-0001-Data.rda`
- `data/raw/DS0009/27063-0009-Data.rda`
- `data/raw/DS0011/27063-0011-Data.rda`

## Run end-to-end

```bash
# 1. Build graph + features (~5 min on CPU)
python -m src.main --stage data
python -m src.main --stage features

# 2. Train both ablation conditions (~30 min each on a 4090)
python -m src.main --stage train               # ablated (r_ms/r_md zeroed)
python -m src.main --stage train --no-ablate   # unablated (full graph)

# 3. Evaluate
python -m src.main --stage eval                # uses CKPT_ABLATED
python -m src.main --stage eval --no-ablate    # uses CKPT_UNABLATED

# 4. Compare and disaggregate
python scripts/compare_ablation.py             # writes runs/<ts>_compare/comparison.{json,md}
python scripts/analyze_cohorts.py              # cohort_analysis.csv per run
```

## Findings (single seed, this checkpoint)

| Cohort era | n_marriages | recall@1 (ablated) |
|---|---:|---:|
| Regular test (1882–1888) | 6,129 | **0.899** |
| Catch-up (1903) | 12,026 | 0.730 |
| Late (1906–1909) | 8,073 | 0.739 |
| **Test macro average** | 26,228 | **0.772** |

Pre-1780 train cohorts (recall ≈ 0.38) are structurally unpredictable —
the panel started in 1749 and these cohorts have ~70% of women without a
recorded father visible in the time-restricted subgraph. Detail in
`scripts/audit_early_cohorts.py`.

**Ablation comparison (proper experiment, both models trained from scratch
with `r_ms`/`r_md` present vs. zeroed throughout):**

| Metric | Ablated | Unablated | Δ |
|---|---:|---:|---:|
| Hungarian recall@1 | 0.7717 | 0.7695 | −0.0022 |
| ROC-AUC | 0.9936 | 0.9935 | −0.0001 |
| Log-loss | 0.3942 | 0.4014 | +0.0071 |

Within single-seed noise. **Maternal edges (`r_ms`, `r_md`) add ~zero
predictive value for marriage prediction in this graph.** Mechanistically
this is because a 2-layer HGT can reach a person's mother via the
2-hop path `child ──r_fs→ father ──r_hw→ mother`, which uses only edges
that survive ablation. Each marriage edge implicitly identifies a mother.

This contradicts the original design hypothesis (that maternal edges are
the only cross-family bridge in a patrilineal genealogy) and is the
substantive contribution of the project.

## Key invariants (verified by `tests/test_smoke.py`)

1. **No future leakage.** Edges in `subgraph_at_year(g, t)` satisfy `edge_time < t` for every edge type.
2. **Ablate, don't delete.** `ablate_maternal_edges()` empties tensors but leaves keys; `HGTConv` requires every edge type in `metadata`.
3. **Share tensors, copy containers.** `subgraph_at_year` and `mask_target_edges` use `copy.copy(graph)` — node features are huge and must not be cloned.
4. **Within-cohort negatives.** Negative women are drawn from the same-year marriage cohort.
5. **CMGPD `SEX` coding is preserved as 1=Female, 2=Male** (raw convention).

## Data attribution

CMGPD-LN: Lee, James Z., Cameron Campbell, and Wang Feng. *China Multi-Generational
Panel Dataset, Liaoning (CMGPD-LN), 1749–1909*. ICPSR 27063 / 21766.
Data are not redistributed in this repository.
