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

Frontend (always required):

```bash
cd viz-mas
npm install
npm run dev    # → http://localhost:5190/
```

Backend (optional — enables live agent streaming + slider sync):

```bash
cd viz-mas
pip install -r server/requirements.txt
uvicorn server.main:app --host 127.0.0.1 --port 8001 --reload
```

Without the backend, the frontend falls back to:
- static cohort JSONs in `public/data/`
- a client-side simulation of the agent stream (same event shapes, same component decomposition as the server)

The 12 cohort JSONs were copied into `public/data/` at scaffold time. To
refresh from the upstream `viz/data/` directory after a precompute rerun:

```bash
cp ../viz/data/cohort_*.json public/data/
```

## What's wired now (formerly the stub list)

1. **FastAPI backend** at `server/main.py` — endpoints: `/api/health`, `/api/metrics`, `/api/pair`, `/api/shap/{pair_id}`, `/api/rules` (GET/POST), and `WS /api/negotiate/{pair_id}/stream`. Vite proxies `/api/*` (HTTP + WebSocket) to `127.0.0.1:8001`.
2. **WebSocket negotiation stream** — V5 opens a WS to `/api/negotiate/{id}/stream`; events arrive incrementally (`round-start` → 6× `agent` → `final`). Falls back to client-side simulation if the backend isn't running.
3. **Motif glyphs** — `MotifGlyph.vue` ports the reference's DRNL-coloured node + relation-coloured edge SVG glyph. V6 uses it inline next to each motif row.
4. **SHAP waterfall** — V5 renders a per-pair component-attribution waterfall under the agent rows. Heuristic decomposition: bias + paternal lineage + sibling overlap + household share + banner match + macro era + endogamy penalty, each gated by the live macro slider weights from V6. The "FINAL (logit)" bar at the bottom shows where the components add up to the model's actual prediction.

## How the views connect

```
V6 sliders/checkboxes ── postRules() ──→ FastAPI in-memory state
        │                                    │
        └─ bus.emit('rules-updated') ────────┴─→ V5 re-streams + recomputes SHAP
V3 click / lasso ── bus.emit('hex-select') ──→ V4 (bipartite) + V5 (negotiate)
```

So moving a V6 slider while a V5 round is open re-streams the rounds with the new weights and re-renders the waterfall — closes the loop between rule input and per-pair explanation.

## Connection to existing repo

- Cohort JSONs come from `viz/data/precompute.py` — the same artefacts the
  vanilla viewer at `viz/index.html` uses. The same checkpoint
  (`checkpoints/best_ablated.pt` / `best_unablated.pt`) drives both.
- The vanilla `viz/` viewer remains untouched and continues to work standalone.
