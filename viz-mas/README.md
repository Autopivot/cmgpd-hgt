# viz-mas/

Vue 3 + Vite frontend for the CMGPD MAS+HGT analytics workspace. Layout +
algorithms ported from the reference at
`D:/projects/jiapu-hgt-final/.claude/worktrees/nostalgic-booth-48a44f/frontend-asight/`.

## Layout

3-column grid + 6 panels (matches the reference):

| Cell | Component | Role |
|------|-----------|------|
| V1   | `OverviewView`              | Per-cohort completion metrics (recall@1, top-10, MRR) — line chart + table |
| V2   | `ProcessedRelationsTable`   | Sorted list of matched (husband ↔ wife) pairs in the active cohort |
| V3   | **`HexEmbeddingView`**      | **Embedding space — ASight pipeline**: density contour + X-means convex hulls + (hex / scatter) foreground + lasso |
| V4   | `BipartiteDetailView`       | Bipartite husband ↔ wife graph for the V3-selected pairs |
| V5   | `AgentBattleView`           | MAS negotiation arena (currently a stub running 3 hand-rolled rule-agents per pair) |
| V6   | `RulerInjectorView`         | Macro feature weights + micro motif toggles (local-only sliders) |

## View 3 details (preserved)

- ASight pipeline order: density contour → X-means + cluster hulls → foreground.
- Two foreground modes: `⬢ hex` (binned glyphs, mean HGT score) and `• scatter` (one dot per pair).
- Lasso (d3.brush rectangle) — toggled with the lasso button. Selection emits a `hex-select` event with the picked pairs; V4/V5 pick it up.
- HGT score color ramp: cream → gold → orange → magenta → indigo. Cluster palette `d3.schemeSet2`.
- Top-K filter: keep only the K best-scoring pairs per husband (1, 3, 5, 8). K=1 collapses to argmax.

## Data source

- Static fallback (current default): fetches `./data/cohort_<year>__<ablation>.json`. The 12 JSONs are precomputed by `viz/data/precompute.py` against the trained checkpoints. Real `score`, `score_gap`, `hungarian_correct`, `mds_coords`, `clusters`, `lineage_*`, and `patri_path_count` per pair.
- Live backend (planned, not yet implemented): FastAPI at `127.0.0.1:8001` exposing `/api/match`, `/api/embedding`, `/api/negotiate/{id}/stream`, etc.

## Run

```bash
cd viz-mas
npm install
npm run dev   # serves on http://localhost:5190/
```

The 12 cohort JSONs were copied into `public/data/` at scaffold time. To
refresh from the upstream `viz/data/` directory after a precompute rerun:

```bash
cp ../viz/data/cohort_*.json public/data/
```

## What's stubbed (not done yet)

1. **Live MAS+HGT backend** — agent-battle and rule-injector are local placeholders. The user-facing wiring (event bus, API surface) is in place; the FastAPI side is the next deliverable.
2. **WebSocket negotiation stream** — V5 currently calls `getAgentRound()` which returns a static 3-agent fixture per pair. The real stream from `/api/negotiate/{id}/stream` will replace it.
3. **Motif glyph component** — V6 lists motifs as text only; the reference's circular SVG glyph (DRNL-coloured, src/dst as stars) will land with the motif backend.
4. **SHAP waterfall** — V5 in the reference has a per-pair SHAP explanation; this requires running explainer code against the trained HGT and is deferred.

## Connection to existing repo

- Cohort JSONs come from `viz/data/precompute.py` — the same artefacts the
  vanilla viewer at `viz/index.html` uses. The same checkpoint
  (`checkpoints/best_ablated.pt` / `best_unablated.pt`) drives both.
- The vanilla `viz/` viewer remains untouched and continues to work standalone.
