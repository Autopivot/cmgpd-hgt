# `viz/data/` — precomputed cohort viewer payloads

This directory holds the **JSON payloads** consumed by the HGT
research-demo viewer, plus the **`precompute.py`** script that produces
them. The payloads are designed to be self-contained: the frontend reads
them with a single `fetch()` call and renders without any extra API.

## Status of the current files (as committed)

| file                            | year | condition | mode          | n_pairs |
|---------------------------------|------|-----------|---------------|--------:|
| `cohort_1882.json`              | 1882 | ablated   | **real**      |  6,000  |
| `cohort_1882__unablated.json`   | 1882 | unablated | stub          |    250  |
| `cohort_1885.json`              | 1885 | ablated   | stub          |    250  |
| `cohort_1885__unablated.json`   | 1885 | unablated | stub          |    250  |
| `cohort_1888.json`              | 1888 | ablated   | stub          |    250  |
| `cohort_1888__unablated.json`   | 1888 | unablated | stub          |    250  |
| `cohort_1903.json`              | 1903 | ablated   | stub          |    250  |
| `cohort_1903__unablated.json`   | 1903 | unablated | stub          |    250  |
| `cohort_1906.json`              | 1906 | ablated   | stub          |    250  |
| `cohort_1906__unablated.json`   | 1906 | unablated | stub          |    250  |
| `cohort_1909.json`              | 1909 | ablated   | stub          |    250  |
| `cohort_1909__unablated.json`   | 1909 | unablated | stub          |    250  |

### Stub vs real

`cohort_1882.json` was produced by running the real HGT pipeline against
the trained ablated checkpoint (1,000 husbands × 6 cohort women →
6,000 scored pairs, then PCA + MDS + KMeans/X-Means clustering).
It carries real CMGPD-LN PERSON_IDs, real model scores, real lineage
roots, and real patrilineal-path counts.

The other 11 JSONs are **stub mode** — synthesised by `precompute.py`
with contract-valid distributional shape (clustered embeddings,
plausible score distributions, sparse same-lineage flags) but no
relationship to the actual model output. They exist so the frontend
exercises every code path on every year tab without blocking on
~hour-long retraining.

To regenerate any of them with the real model, see
[Running real precompute](#running-real-precompute) below. A retrain
is required first because the model schema migrated to per-cohort
macro covariates after the 1882 real run was produced.

## Running stub precompute

Stub mode does not touch the model or the graph cache. It just writes a
contract-valid payload using `numpy`. Use it when:

- the conda environment is missing (`pyclustering`, GPU drivers, …);
- you want to iterate on the frontend without paying for HGT inference;
- a real run failed and you need a placeholder.

```bash
# Single year + condition
python viz/data/precompute.py --year 1882 --ablated --stub
python viz/data/precompute.py --year 1882 --unablated --stub

# All 6 acceptance-required JSONs at once
python viz/data/precompute.py --all --stub
```

## Running real precompute

Real mode loads `data/processed/hgt_pipeline/graph.pt`, restores one of
the trained checkpoints (`checkpoints/best_ablated.pt` or
`checkpoints/best_unablated.pt`), runs HGT on the per-cohort causal
subgraph, and writes both encoder embeddings and pair-level scores. The
model has been observed to consume ~6–8 GB GPU memory and several minutes
per cohort.

```bash
# Single (year, condition)
python viz/data/precompute.py --year 1882 --ablated
python viz/data/precompute.py --year 1882 --unablated

# All 6 cohorts (3 years × 2 conditions)
python viz/data/precompute.py --all
```

Use the project's conda environment:

```
C:/Users/Bryan/anaconda3/envs/cmgpd-hgt/python.exe viz/data/precompute.py --all
```

If real mode raises (e.g. the graph cache is missing macro features, the
checkpoint shape has shifted, or a GPU dependency is missing),
`precompute.py` falls back to stub mode automatically and logs the
reason. The fallback ensures the acceptance criteria
(6 contract-valid files) are met regardless.

## Years available

The acceptance-required cohort years are `1882`, `1885`, `1888`. Three
additional test cohorts are supported by the script if you want to
extend coverage: `1903`, `1906`, `1909`. To produce them:

```bash
python viz/data/precompute.py --years 1903,1906,1909
```

The era tag in each payload is:

| year | era       | comment |
|------|-----------|---------|
| 1882 | regular   | densely sampled mid-Guangxu cohort |
| 1885 | regular   | mid-Guangxu cohort |
| 1888 | regular   | thin late-Guangxu cohort (~1188 pairs) |
| 1903 | catchup   | very large catch-up cohort (~12k pairs) |
| 1906 | late      | late panel; sparse paternal kin |
| 1909 | late      | terminal year; sparse paternal kin |

## Data contract

Every payload conforms to the following shape. **Frontend code should
treat this section as the source of truth**; the precompute script
validates it on every write.

```jsonc
{
  "year": 1882,                // int, the cohort marriage year
  "n_pairs": 1495,             // int, length of pairs / mds_coords / clusters arrays
  "ablation": "ablated",       // "ablated" | "unablated"
  "k_clusters": 8,             // int, number of clusters (X-Means or KMeans+silhouette)
  "pairs": [
    {
      "id": 0,                                // int, equals array index
      "husband_id": "P00123",                 // string, "P" + the CMGPD PERSON_ID
      "wife_id":    "P04812",                 // string
      "label": 1,                             // 1 = positive (true couple), 0 = hard-negative pair
      "score": 4.71,                          // float, scorer logit
      "score_gap": 0.83,                      // float (signed)
                                              //   positives: score - best_within-cohort_negative
                                              //   negatives: score - score(true_wife)
      "rank_of_true_wife": 1,                 // int|null, rank of husband's true wife in his
                                              //   row over the cohort women (1-indexed). null
                                              //   for negative-row pairs.
      "hungarian_correct": true,              // bool|null, true iff (husband, true_wife) is in
                                              //   the cohort-square Hungarian matching.
                                              //   null for negative-row pairs.
      "lineage_husband": "L042",              // string "L%03d" or "L_unknown"
      "lineage_wife":    "L017",              // string
      "same_lineage": false,                  // bool, lineage_husband == lineage_wife (and not unknown)
      "era": "regular",                       // "regular" | "catchup" | "late"
      "patri_path_count": 2,                  // int >= 0, # of paths of length ≤ 2 from husband
                                              //   to wife in the patrilineal subgraph
                                              //   (r_fs, r_fd, r_sib, r_hh, r_hc, r_cb).
      "z": [/* HIDDEN floats */]              // length-128 list (matches model HIDDEN). The
                                              //   penultimate-layer scorer activation:
                                              //   GELU(scorer.mlp[0]([h_m; h_w; |h_m-h_w|; h_m*h_w])).
    }
    // …
  ],
  "mds_coords": [[x, y], …],   // length n_pairs; PCA(50) → MDS(2) on z (z-scored across cohort)
  "clusters":   [c, c, …]      // length n_pairs; integer cluster id per pair (X-Means BIC, kmax=10)
}
```

Notes on the `z` and projection space:

- `z` is the **first-layer activation of the marriage scorer**, i.e.
  `GELU(Linear(4·HIDDEN → HIDDEN)(concat[h_m; h_w; |h_m−h_w|; h_m·h_w]))`.
  This is the representation the scorer's final logit head sees, which
  makes it the most diagnostic embedding for "how does the model think
  about this couple?".
- `mds_coords` is a 2-D embedding of `z` for plotting. Pipeline:
  z-score across all pairs in the cohort → PCA(50) → MDS(2) (sklearn
  defaults, `random_state=0`).
- `clusters` is X-Means (`pyclustering`) with BIC, `kmax=10`. If
  `pyclustering` is not installed the script falls back to KMeans with
  `k` chosen by silhouette score over `[2, kmax]`.

Pair-level invariants the frontend can rely on:

- `pairs[i].id == i` for all `i`.
- `len(pairs) == len(mds_coords) == len(clusters) == n_pairs`.
- `n_pairs >= 100` (enforced by the acceptance harness; in practice
  several hundred to ~6 000).
- No `NaN` or `Infinity` in any numeric field.
- `hungarian_correct` and `rank_of_true_wife` are **only** populated for
  positive-label pairs; for negatives they are `null`.

## How to validate manually

```bash
python -c "
import json, sys
p = json.load(open('viz/data/cohort_1882.json'))
print('n_pairs =', p['n_pairs'])
print('positives =', sum(1 for q in p['pairs'] if q['label'] == 1))
print('k_clusters =', p['k_clusters'])
print('ablation =', p['ablation'])
print('first pair keys =', sorted(p['pairs'][0].keys()))
"
```
