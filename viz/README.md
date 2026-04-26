# viz/

Vanilla HTML/CSS/JS frontend for inspecting per-cohort HGT marriage-prediction
results. ASight-style honeycomb + contour overlays, no framework, no build step.

## Run locally

```bash
python -m http.server 8766 --directory viz
# open http://localhost:8766/index.html
```

The page loads `data/cohort_<year>.json` (and `..._unablated.json`) over HTTP.
File-protocol (`file://`) won't work because of CORS on `fetch`.

## Regenerate JSON from a trained checkpoint

```bash
# Real model output (requires checkpoints/best_{ablated,unablated}.pt + graph.pt)
python viz/data/precompute.py --year 1882 --ablated
python viz/data/precompute.py --year 1882 --unablated
python viz/data/precompute.py --all                      # all 6 years × 2 conditions

# Synthetic stub (works without a trained model — what's currently committed)
python viz/data/precompute.py --year 1882 --stub
```

See `viz/data/README.md` for the full data contract and stub vs. real status.

## Add a new test year

1. Add the year to `YEARS` in `viz/js/main.js`.
2. Generate `viz/data/cohort_<YEAR>.json` and `cohort_<YEAR>__unablated.json` via `precompute.py`.
3. Reload the page; the year-selector multiples auto-reflect `YEARS`.

## Module map

| File | Owner | Role |
|---|---|---|
| `index.html`, `css/main.css`, `js/main.js`, `js/interactions.js` | wire-up | page shell, state machine, event routing |
| `js/cluster_layout.js`, `js/honeycomb_render.js` | honeycomb | inward-attraction hex packing + SVG render |
| `js/contour_render.js` | contour | weighted height field → IDW grid → Gaussian smooth → d3-contour rings |
| `js/drill_panel.js` | drill | sortable per-cell pair table (with side-by-side compare) |
| `js/linked_views.js` | strips | score-gap and confusion strips that highlight on cell hover |
| `data/precompute.py`, `data/*.json` | data | model → JSON; contract documented in `data/README.md` |

## Color palette (fixed)

Cells: `#993c1d` low / `#f5f1e8` mid / `#0f6e56` high.
Contours: `#1d9e75` confidence / `#ba7517` patrilineal / `#7f77dd` endogamy.
Border `#888780`. Background white.
