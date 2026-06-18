# System Overview — GeneaLink (post-redesign)

This document is a fresh end-to-end picture of the system as it stands after the
1882-anchored MDS + per-cell rule-transfer redesign. It supersedes the older
slider-based V6 description and the per-year-MDS V3 description in §05.

## 1. Project framing

**Goal**. Reconstruct the marriage edges and maternal edges that imperial-era
Chinese family genealogies (`jiapu`) systematically suppress. The deployment
target is real `jiapu`; CMGPD-LN serves as a testbed where those edges *do*
exist and can be ablated to simulate the `jiapu` record gap.

**Two regimes the system explicitly distinguishes** (the title-bar mode banner
makes this regime visible at all times):

| Regime | Cohort year | GT visible? | Mode banner | Analyst's role |
|---|---|---|---|---|
| **Eval / training** | 1882 (validation cohort) | yes | green "training mode" | Tune per-husband rule weights against MAS feedback; commit accepted edges; bind aggregate rule profiles to hex cells. |
| **Transfer / deploy** | 1885, 1888, 1903, 1906, 1909 | no | blue "transfer mode" | Reuse the 1882-bound cell rules as soft priors on round-1 MAS prompts; commit edges blind; track edge-completion progress against cohort size. |

The cohort split is enforced everywhere: V1 swaps its y-axis, V3 disables the
GT-aware "score-gap" colormap option, V6 makes its weight sliders read-only
in transfer mode, and the backend `/negotiate` reads `cell_rules` only when
the analyst's V6 saved a profile.

## 2. Computational backbone (unchanged)

- **Heterogeneous Graph Transformer** (`src/model/hgt.py`) over four node
  types (`person`, `household`, `community`, `banner`) and nine edge types
  (`r_fs`, `r_fd`, `r_ms`, `r_md`, `r_sib`, `r_hh`, `r_hc`, `r_cb`, `r_hw`).
- **Marriage scorer** — MLP over `[h_m, h_w, |h_m − h_w|, h_m * h_w]`.
- **Ablation pipeline** — `r_ms` and `r_md` (maternal child→mother edges) and
  the target `r_hw` are stripped before training; `evaluate.py` reports
  `ablation_delta_recall@1` against an unablated upper-bound pass.
- **Cohort split** — train ≤ 1855 / val ≤ 1879 / test ≤ 1909.

The vis layer **freezes the trained checkpoint** (`checkpoints/best_ablated.pt`,
`best_unablated.pt`). All vis-time computation is forward-pass + similarity
features + LLM negotiation.

## 3. Six-panel workspace (current shape)

**Title bar**: `GeneaLink` · YEAR segment (1882 / 1885 / 1888 / 1903 / 1906 /
1909) · backend health chip · 🔑 DashScope key popover · Reset.
A 18-pixel **mode banner** sits below the title bar showing the active regime.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ GeneaLink   YEAR  [1882] 1885 1888 1903 1906 1909      backend ok 🔑 Reset│
│ 🟢 training mode · 1882 (full GT) — V6 sliders adjustable, save to cell  │
├──────────────────┬─────────────────────────┬──────────────────────────────┤
│ V1: Overview     │ V3: Embedding View      │ V5: MAS View                 │
│   (recall@1 in   │   (honeycomb / scatter  │   (▶ arena, 6-round bilateral│
│    1882; edge-   │    / mixed; eval/deploy │    negotiation, hint console,│
│    completion in │    color modes; gold-   │    👁 GT toggle, candidate   │
│    1885+)        │    dot bound cells)     │    cards with persona)       │
├──────────────────┼─────────────────────────┼──────────────────────────────┤
│ V2: Process View │ V4: Bipartite View      │ V6: Rules View               │
│   (accepted-edge │   (husband-↔-wife arcs, │   (MACRO: grain+disaster     │
│    table with    │    HGT score labels,    │    dual-axis chart +         │
│    optional GT   │    selectable husband   │    similarity bars; RULES:   │
│    column)       │    drives V6+V5)        │    sliders + motifs; MICRO:  │
│                  │                         │    live motif detection)     │
└──────────────────┴─────────────────────────┴──────────────────────────────┘
```

Column widths and row heights are drag-resizable; both ratios persist to
`localStorage["cmgpd-col-pct-v1"]` and `cmgpd-row-pct-v1`.

### V1 — Overview (mode-aware)

- **Eval mode (1882)**: cumulative MAS recall@1 vs accepted relations curve
  in red, plus a dashed green HGT static baseline (~0.605). Anchors the
  analyst on the gap between the calibrated-but-rank-poor HGT and the
  agent-loop's running recall.
- **Transfer mode (1885+)**: cumulative model edge-completion progress.
  x-axis = number of accepted edges; y-axis = `n_accepted /
  cohort_husbands`; horizontal y=1 ceiling labelled `cohort = N`. recall@1
  is undefined here so the panel honestly drops it.

### V2 — Process View (accepted-edge table)

Logs every committed `(husband, wife)` pair in the current cohort. Columns:
husband, wife, score, gap, **H.** (Hungarian-correct dot — green/red/grey),
optional **GT** (toggleable via the `show GT` checkbox in the header — green
"GT" chip / red "neg" / grey "—" only visible when the analyst chooses to
look), source chips (`HGT`, `MAS`, or both), restore button. The H. and GT
columns are blank in transfer mode (or the GT checkbox is simply hidden by
the analyst).

### V3 — Embedding View (1882-anchored honeycomb)

- **Coordinate system**. All cohort years live in the SAME 2-D MDS frame.
  1882 is the anchor: `precompute.py` fits StandardScaler + PCA + MDS jointly
  on (test pairs ∪ training-positives) for 1882, persists the anchor at
  `viz/data/anchor_1882_{ablated|unablated}.npz` (scaler bytes, PCA bytes,
  z_norm, MDS coords). 1885+ skip the local MDS fit; their `z_proj` flows
  through the saved scaler+PCA → KNN-regressor (k=8, distance-weighted)
  trained on the anchor's PCA → MDS pairs. `train_ref_coords` (the gold
  contour heatmap) is the anchor's `mds_train` verbatim, so the contour is
  byte-identical across years (within float32 serialization precision).
- **Layout**. `cluster_layout.js` packs the unit square into ~290 hexagonal
  cells; cell-IDs are assigned by deterministic grid traversal so the same
  cell-id lands at the same (cx, cy) in every year. `meanScoreGap`,
  `meanScore`, `posRatio` are aggregated per cell.
- **Three render modes**: `honeycomb` (cells only, click → V4), `scatter`
  (one dot per pair at raw `mds_coords[i]`, lasso-selectable), `mixed`
  (translucent hexes + dots).
- **Two color modes** (eval vs deploy):
  - `gap` (eval): diverging red→beige→green by cell-mean `score_gap`,
    anchored at ±2 logits. Stripe overlay flags `posRatio` outliers (>2σ).
    Requires GT.
  - `score` (deploy): sequential beige→blue by cell-mean raw HGT score,
    anchored at cohort min/max. Stripe overlay disabled. GT-free.
- **Bound-cell indicator**. Cells with a saved `/api/cell-rules/{id}`
  profile show a small gold dot at their centroid. Querying the endpoint
  on cohort load returns the list of bound IDs — the dot map is identical
  across years because cell-IDs are stable.
- **Train-density contour** (gold heatmap behind hexes/dots). Built with
  `d3.contourDensity` from `train_ref_coords`. Same in every year because
  it's the anchor's saved coords.

### V4 — Bipartite View (husband ↔ wife arcs)

Per-cohort selection from V3 (hex click or lasso). Husbands on the left,
wives on the right, bezier arcs labelled with HGT score (green/red/grey by
`hungarian_correct`). Clicking either side: gold-rings the husband, fetches
his profile popup, emits both `person-selected` (V5 picks up) and
`husband-context` (V6 picks up). Wife clicks resolve to the owning husband
so V6 still activates. Empty-canvas click clears the selection across
V4/V5/V6. A batch-accept tool in the header argmax-picks the best wife per
husband at gap ≥ τ for fast triage.

### V5 — MAS View (LLM negotiation arena)

- **Husband target row** with chip + birth/banner/community/household + life
  history + persona resume. Click a husband in V4 (or V2/V3) to load.
- **▶ arena** kicks off `/api/negotiate/{husband_id}` with body
  `{year, ablation, auto_commit, cell_rules?}`. The orchestrator opens
  `WebSocket /api/negotiate/{husband_id}/stream` and runs six rounds:
  persona → impressions → deep-dive → rebuttals → alignment → final.
- **Per-candidate cards** (CandidateCard.vue) — pre-score, gap, persona
  traits, per-round score history, conversation transcript. The
  `· GT pair / hard neg` badge is hidden by default and revealed by the
  **👁 GT** toggle in the panel head. Final round writes
  `{score = (s + t)/2 − λ·|s − t|, λ=0.3}` and the ranking footer surfaces
  the top-3 with an Accept button.
- **Hint console**. Formal `@target: verb` syntax (`boost`, `penalise`,
  `eliminate`, `accept`) parses regex-fast; free text goes to
  `/api/hint/parse`, which routes through Qwen with a strict
  `{actions, rationale}` JSON schema and dispatches `modify_persona_field` /
  `modify_score` / `eliminate` / `inject_directive` to the in-memory MAS
  state. Applied actions stack in a directives panel under the chat log.
- **GT toggle and reveal** are session-only — clicking another husband or
  changing the cohort resets the V5 view.

### V6 — Rules View (mode-aware sliders + cell binding + motif detection)

Three sections:

1. **MACRO FEATURES**. Two side-by-side panels:
   - `MacroCombinedChart`: dual-axis chart over the prior 10 years.
     Left axis (gold, line + LOW/HIGH band) = grain price (raw DS0009
     `.rda`, exposing `grain_price` mean + `grain_low` min(LOW_*) +
     `grain_high` max(HIGH_*)).  Right axis (red, bars at 0.45 opacity) =
     disaster count from DS0011. Y-axis labels are rotated outside the plot
     ("grain price" left, "Disasters" right) — no top title.
   - `PairSimilarityBarChart`: vertical bars, x = candidate wife_id, y =
     metric value. Metric picker on the right (vertical button stack):
     paternal lineage proximity (numeric), shared siblings (numeric),
     same household history (yes/no), same banner (yes/no). Binary metrics
     render bars at height 0/1 with `no`/`yes` axis ticks; missing-value
     candidates show "?" labels.
2. **RULE WEIGHTS** (the F1 RuleWeightsEditor). Four sliders (range 0–2,
   step 0.05) for the four pair-feature weights, plus an 8-checkbox grid
   for catalog motifs (M01, M02, M03, M10) + context motifs
   (CTX_same_banner, CTX_same_community, CTX_co_resident, CTX_same_region).
   - Per-husband sheets persist to `localStorage` keyed
     `cmgpd-cell-rules-husband-{husband_id}`.
   - Each slider drag emits `cell-rules-updated` so V5 re-uses the latest
     weights on the next /negotiate.
   - Editable in 1882 only; greyed-out + read-only in 1885+.
3. **MICRO MOTIFS** (live detection). For each candidate `(h, w)` the panel
   queries `/api/motifs/{h}/{w}?year=N`, which `seal/scripts/motif_detect.py`
   resolves against `seal/motifs/catalog.json`. Returned motifs are augmented
   with profile-driven **context motifs** (CTX_same_banner / CTX_same_community
   / CTX_co_resident / CTX_same_region) so non-kin candidates surface a
   meaningful row instead of always being empty. The list aggregates by
   `motif_id` and shows per row: a `MotifMiniGlyph` (custom SVG renderer
   that walks the catalog's `relations` chain), a row of matched-candidate
   chips, and the motif's English `explanation_en`.

**Cell binding (the load-bearing mechanism for transfer)**. The panel head
shows `cell #N · {n_husbands} bound · last saved <ISO>` or `unbound` when
V3 emits a `hex-select` event. In 1882 a **💾 save to cell** button
aggregates per-husband sheets (mean weights; OR-reduced motif booleans; if
a husband has no localStorage sheet because the analyst didn't drag any
slider, default 1.0 weights + all-on motifs are used so the cell still
binds) and POSTs to `/api/cell-rules/{cell_id}`. In 1885+ the same cell
reload pre-fills the read-only sliders; the save button is hidden. V5's
arena reads the same cell rules and forwards them to the round-1 prompt.

## 4. Data flow — bus + REST surface

### Bus events (frontend)

| Event | Producer | Consumers | Payload |
|---|---|---|---|
| `cohort-changed` | App.vue (year/ablation toggle) | all panels | `{year, ablation}` |
| `hex-select` | V3 (cell click), V2 (row click) | V4, V6 | `{binKey, cell_id, pairIds, pairs[]}` |
| `hex-clear` | App.vue Reset, V3 background click, V4 background click | V3 (highlight off), V4 (drop selection), V6 (clear cell) | — |
| `person-selected` | V4, V2 (husband click) | V5 (load husband), V4 (highlight ring) | `{id, role}` (id=null clears V5) |
| `husband-context` | V4 (any person click) | V6 (set husband + candidates) | `{husband_id, candidates: [{wife_id, score, score_gap}]}` |
| `cohort-context` | V5 (after `stage:filter` + final ranking + arena teardown) | V6 (override candidates with arena spawn) | `{husband_id, candidate_ids}` |
| `cell-rules-updated` | V6 (slider drag, save, transfer-mode reload) | V5 (cache for next /negotiate), V3 (refresh bound dots), RuleWeightsEditor (sync slider state) | `{cell_id, year, weights, motifs_enabled, n_husbands?, updated_at?}` |
| `match-accepted` | V5 (acceptOne, batch), V4 (batch tool), V2 (commit) | V3 (acceptedSet → dim dot), V4 (filter pair), V1 (reload progress) | `{husband_id, wife_id, score, source}` |
| `match-restored` | V2 (restore button) | V3, V4, V1 (re-add) | `{husband_id, wife_id}` |
| `panel-resized` | App.vue (drag gutters) | views in the affected column | `{ids: ['v1','v2'…]}` |
| `full-screen` | any panel-head ⛶ | App.vue (state.fullscreen) | `id` |

### REST endpoints (backend, FastAPI on :8001)

| Route | Purpose |
|---|---|
| `GET  /api/health` | liveness |
| `GET  /api/profile/{person_id}` | DS0001+DS0003 person attributes |
| `GET  /api/macro/{year}?window=N` | grain prices (mean + LOW + HIGH) + disaster count for the prior N years; reads raw `D:/projects/cmgpd-hgt/data/raw/DS0009/27063-0009-Data.rda` |
| `GET  /api/pair-features/{h}/{w}` | `{paternal_lineage_proximity, shared_siblings, same_household_history, same_banner}`; BFS on undirected paternal+maternal kin graph up to 8 hops, common-ancestors-within-2-generations for siblings, full panel-history join for household, banner→community fallback |
| `GET  /api/motifs/{h}/{w}?year=N` | seal `detect_for_query` output + four `CTX_*` profile-driven context motifs; LRU-cached by `(h, w, year)` |
| `GET  /api/cell-rules/{cell_id}?year=1882` | bound rule profile for the cell |
| `POST /api/cell-rules/{cell_id}` | save aggregated profile (atomic write to `viz-mas/server/data/cell_rules.json`) |
| `GET  /api/cell-rules` | list of all bound cells (drives V3 gold-dot indicators) |
| `DELETE /api/cell-rules/{cell_id}?year=N` | unbind |
| `POST /api/negotiate/{husband_id}` | start the 6-round MAS orchestrator; body `{year, ablation, auto_commit, cell_rules?}` |
| `GET  /ws /api/negotiate/{husband_id}/stream` | WebSocket replay of `start, stage, narrative, persona, query, answer, round_scores, round_paused, final_ranking, committed, hint_ack, error, done` frames |
| `POST /api/negotiate/{husband_id}/advance` | leave a round_paused frame |
| `POST /api/negotiate/{husband_id}/hint` | append a directive to the per-husband hint queue |
| `POST /api/hint/parse` | LLM-routed natural-language hint dispatch |
| `POST /api/negotiate/{husband_id}/override` | manual commit |
| `POST /api/negotiate/{husband_id}/restore` | rollback |
| `GET  /api/eval-progress?year=N&ablation=A` | V1 trajectory (returns recall@1 series in 1882 and progress fraction in 1885+) |
| `GET, POST /api/llm_config` | pinned model `qwen3.6-plus` + DashScope key (set via the 🔑 popover) |

## 5. The 1882 → 1885+ transfer mechanism (the redesign's core claim)

Three things together make per-cell rule transfer work:

1. **Anchored MDS frame**.  `precompute.py` fits the joint PCA + MDS for 1882
   and saves the scaler + PCA model + MDS coords. Every later year applies
   the saved scaler+PCA and KNN-regresses (k=8, distance-weighted) PCA → MDS
   from the anchor. `train_ref_coords` is copied through verbatim. Wall time
   for 1885+: ~10s/year (vs ~3 min for the original joint-MDS fit).

2. **Stable hex-cell IDs**. Because every year occupies the SAME 2-D space,
   the deterministic grid packer in `cluster_layout.js` assigns the same
   cell-ID at the same (cx, cy) in every year. Empirically the centroid drift
   between 1882 and 1885 is < 0.0003 in [0,1]² — far below the cell radius.

3. **Cell-keyed rule profile**. The analyst's per-husband V6 weight sheets
   in 1882 aggregate into a single cell profile (mean weights + OR-reduced
   motifs), keyed `(cell_id, year=1882)`. In any later year, V6 fetches the
   same `(cell_id, year=1882)` profile when the analyst clicks the
   matching hex; the read-only sliders display it; and V5's arena POSTs it
   along with `/negotiate` so the round-1 prompt renders a `PRIOR
   CALIBRATION FROM 1882 COHORT` block:

   ```
   PRIOR CALIBRATION FROM 1882 COHORT (same MDS region):
     - paternal lineage proximity: weight 1.15
     - shared siblings:            weight 1.14
     - same household history:     weight 1.12
     - same banner:                weight 1.25
     Active motifs: M01, M02, M03, M10, CTX_*.
     Treat these weights as a SOFT prior — they reflect how much each
     similarity feature mattered for accepted matches at this point in the
     kinship-embedding space last cohort. Adjust your scoring accordingly
     when candidates differ along these dimensions.
   ```

   The block is empty (no extra lines emitted) when no `cell_rules` are
   attached, so 1882's own negotiations and any unbound 1885+ cell behave
   identically to the pre-redesign baseline.

The transfer is **across persons, not across the same individuals**: cell
#136's five 1882 husbands do not appear in 1885; the 11 1885 husbands in
the same cell are different people. The prior is a population-level claim
about *kinship-embedding-space neighbourhoods*, not a per-person memo.

## 6. Eval-mode vs deploy-mode summary

| Surface | Eval (1882) | Deploy (1885+) |
|---|---|---|
| Mode banner | 🟢 training | 🔵 transfer |
| V1 y-axis | recall@1 | accepted / cohort_husbands |
| V1 baseline | HGT 0.605 dashed | y=1 cohort ceiling |
| V2 H. column | green/red dots | dots blank (no GT) |
| V2 GT column | toggleable; green/red chips | toggle hidden in deploy mode (no `label` to read) |
| V3 default colormap | `gap` (red/green diverging) | `score` (beige/blue sequential) |
| V3 stripe overlay | on (`posRatio` outlier) | off (depends on label) |
| V3 contour | 1882 anchor's `train_ref_coords` | same — identical contour shape |
| V3 bound-cell dots | yes | yes |
| V4 batch-accept | yes | yes (gap-threshold; doesn't depend on GT) |
| V5 GT-reveal toggle | shows "GT pair / hard neg" on cards | hides them by default |
| V6 RuleWeightsEditor | editable | read-only, pre-filled from 1882 cell profile |
| V6 save-to-cell button | shown | hidden |
| `/negotiate` cell_rules | optional (1882's own pass) | required if cell is bound, else fallthrough |

## 7. Implementation files

```
viz-mas/server/
  main.py                              # FastAPI app + WS broker + router includes
  api/
    macro_endpoint.py                  # /api/macro from raw .rda
    pair_features_endpoint.py          # /api/pair-features (kin BFS + community fallback)
    motif_endpoint.py                  # /api/motifs (seal + CTX_* augmentation)
    cell_rules_endpoint.py             # /api/cell-rules persistence
  mas/
    negotiator_rounds.py               # 6-round orchestrator + _format_cell_rules_block
    state.py                           # in-memory accept log + hint queue + persona overrides
    profiles.py                        # DS0001/DS0003 cache
    llm_helpers.py                     # render_prompt(template, **kwargs), chat_json
    hint_router.py                     # NLP hint dispatch via Qwen
    prompts/persona.txt, query.txt, answer.txt, score.txt, hint_router.txt
  data/
    cell_rules.json                    # persisted bound profiles (atomic-write JSON)
viz-mas/src/
  App.vue                              # title bar, mode banner, drag-resize gutters, key popover
  utils/eventbus.js                    # default-export {on, off, emit}
  api/client.js                        # axios wrappers + cohort JSON cache
  components/
    OverviewView.vue                   # V1 — mode-aware curve
    ProcessedRelationsTable.vue        # V2 — accepted-edge log + GT toggle
    HexEmbeddingView.vue               # V3 — honeycomb / scatter / mixed + bound-dots
    BipartiteDetailView.vue            # V4 — husband-↔-wife arcs
    AgentBattleView.vue                # V5 — MAS arena + cell_rules forwarding + GT toggle
    CandidateCard.vue                  # V5 per-candidate card (revealGT prop)
    RulerInjectorView.vue              # V6 shell — MACRO + RULES + MICRO sections
    v6/MacroCombinedChart.vue          # dual-axis grain + disaster
    v6/PairSimilarityBarChart.vue      # vertical bars + side metric picker
    v6/RuleWeightsEditor.vue           # F1 sliders + motif checks
    v6/MotifMatchList.vue              # F4 live motif results
    v6/MotifMiniGlyph.vue              # catalog-relation-chain SVG
  canonical/
    cluster_layout.js                  # buildHoneycomb (deterministic grid)
    honeycomb_render.js                # renders cells + stripes + borders + bound-dots
viz/data/
  precompute.py                        # 1882-anchor MDS + KNN projection
  anchor_1882_ablated.npz              # saved scaler+PCA+coords (binary)
  anchor_1882_unablated.npz
  cohort_{1882,1885,1888,1903,1906,1909}{,_unablated}.json
src/
  config.py, stage*.py, model/hgt.py, train.py, evaluate.py
  temporal_indicators.py               # macro covariates derivation
checkpoints/
  best_ablated.pt, best_unablated.pt
data/processed/hgt_pipeline/
  ds0001_clean.parquet, graph.pt, grain_prices.parquet, disasters.parquet,
  subgraphs/sg_<t>_<hash>.pt
```

## 8. What an analyst session looks like end-to-end

1. **Boot**. `uvicorn viz-mas.server.main:app --port 8001` + `npm run dev`
   in `viz-mas/`. Open the browser, press 🔑, paste the DashScope key, save.
2. **1882 calibration pass**. Year segment defaults to 1882, banner is green.
   For each interesting hex cell in V3:
   - Click the cell → V4 fills with that cell's pairs.
   - For each husband in V4: click → V5 ▶ arena → six rounds → accept the
     persuasive candidate. Adjust V6's RuleWeightsEditor sliders/motifs as
     the rounds suggest.
   - Click **💾 save to cell** in V6 → cell binds, gold dot appears in V3,
     chip updates with the saved timestamp.
3. **Switch year segment to 1885 (or 1888 / 1903 / 1906 / 1909)**. Banner flips
   to blue. The V3 contour and cell layout are identical (anchor); the
   gold-dot map shows which cells inherit a 1882 prior.
4. **Transfer pass**. Click a bound cell in V3 → V4 fills with 1885's pairs
   → click a husband. V6 sliders fill from the 1882 profile read-only. Press
   ▶ arena → /negotiate carries `cell_rules` → round-1 prompt sees the
   `PRIOR CALIBRATION` block. Accept or override based on the round-6
   ranking. V1 progress curve advances toward y=1.
5. **Audit**. V2 logs every committed edge with source chips
   (HGT-batch / MAS / both). The **show GT** toggle is hidden in 1885+ —
   recall@1 is undefined, so the analyst grades by domain plausibility, not
   by ground truth.

## 9. What changed from the previous (pre-redesign) overview

For readers familiar with the older shape:

- V6 used to be a five-slider rule-injector with four motif checkboxes that
  drove a `RuleWeights`/`MotifFlags` server-side state via `/api/rules`.
  That whole surface is gone; the four V6 sliders now live inside
  `RuleWeightsEditor` and are scoped per-husband, not global. `/api/rules`
  is no longer wired from the frontend.
- V3 used per-year MDS fits with no cross-year alignment. The redesign
  anchors on 1882 and KNN-projects later years; cell-IDs are now stable.
- V3 had a single fixed colormap (gap diverging). Eval and deploy now have
  separate colormaps with an explicit toggle.
- V1 was always recall@1 + HGT baseline regardless of year. Now it
  swaps to a model-completion progress curve in 1885+.
- V2 always showed the H. dot and a "label" column. The H. dot is now blank
  when the cohort has no GT; a separate **show GT** toggle lets the analyst
  reveal/hide GT chips on demand.
- V5 always showed the `GT pair / hard neg` badge inline on each candidate
  card. The redesign hides it behind a **👁 GT** toggle so the analyst can
  do blind triage.
- V6's MACRO row used to be three side-by-side panels (grain line + disaster
  bars + similarity). It's now two: a single dual-axis chart for grain +
  disasters, and a vertical-bar similarity chart with the metric picker
  on the right.
- V6 micro motifs used to be static catalog dumps with toggle checkboxes.
  Now they are **live** — `/api/motifs` runs the seal detector per
  candidate and augments with profile-driven context motifs so non-kin
  candidates also surface useful matches.
- The title bar text shortened from "CMGPD MAS · Hex Analytics" to
  "GeneaLink"; ablation toggle removed (locked to ablated); free-form LLM
  config replaced by a 🔑 popover that pins `qwen3.6-plus`.
- Selection clearing cascades cleanly: V4 hex-clear or empty-canvas click
  drops V5 + V6 in lock-step (previously V5 stayed on the last husband).
