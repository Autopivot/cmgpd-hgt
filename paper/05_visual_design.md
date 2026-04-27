# 5 [SYSTEM]: Visual Analytics Design

## 5.1 System overview

**[SYSTEM]** is laid out as a 3-column, 2-row grid of six linked views, backed by a FastAPI server with WebSocket fan-out for the agent stream (Fig. 1). The frontend is a Vue 3 + Vite single-page application that holds an in-memory cohort context and routes selection events through a shared bus (`hex-select`, `person-selected`, `match-accepted`, `match-restored`). The backend caches the cleaned CMGPD-LN parquet, the HGT-trained model checkpoint, and DS0003-derived per-person life histories.

> **Figure 1 (caption).** [SYSTEM] at a glance. Six linked views (V1–V6) cooperate through a shared event bus. V3's honeycomb cohort canvas drives selection; V4 unfolds the bipartite detail; V5 hosts the six-round agent negotiation; V2 records every commit with a multi-label provenance tag; V1 tracks the running MAS recall@1 against the static HGT baseline; V6 lets the analyst tune macro-feature weights and motif toggles. Every commit is one-click reversible.

## 5.2 V1 — Acceptance curve and ablation diagnostic

The leftmost top panel anchors the session in evaluation context. The *x*-axis advances in cumulative *accepted-edge* ticks; the *y*-axis plots the running recall@1 of the operator's commits against the cohort's known ground truth. A horizontal reference line marks the static HGT-only baseline, computed via per-cohort Hungarian assignment. The curve is updated reactively on `match-accepted` and `match-restored`, so the analyst sees in real time whether the LLM-augmented pipeline is closing or widening the gap to the bare HGT ceiling.

*Encoding choice:* we use a step function rather than a smoothed line to make the contribution of each individual commit visible; the rationale is that this view is also a self-audit instrument (DG2).

## 5.3 V2 — Processed pairs with multi-label provenance

V2 is the persistent record of *what has been committed so far*. Every accepted match appears as a row carrying husband ID, wife ID, HGT score, score gap, the pair's Hungarian-decoder verdict, and the core artefact of [SYSTEM]: a *source* chip set. The chip rules are:

- A commit produced by V4's batch operation receives the chip **HGT** (sage green). Batch always selects the husband's $\arg\max$ by HGT score, so the tag is unambiguous.
- A commit produced by V5's MAS arena receives the chip **MAS** (amber). If the MAS-chosen wife coincides with the husband's HGT $\arg\max$, the row carries *both* chips, signalling convergent agreement of the two pipelines.

A trailing ↶ *restore* button on every row issues an HTTP `POST` to `/api/negotiate/{id}/restore`, removes the entry from the in-memory accept log, and broadcasts `match-restored` on the bus, which causes V1's curve to recompute, V3's masked dot to reappear, and V4's bipartite edge to re-enter selection if its hex is currently active. This is DG5 materialised: a single click rolls a bad commit back across all four dependent views.

## 5.4 V3 — Honeycomb embedding canvas

V3 carries the cohort-as-canvas requirement (DG1). Pairs are projected into 2-D via per-cohort metric multidimensional scaling on the HGT joint embedding and binned into a flat-top hex grid via an ASight-style iterative inward-attraction packer (cluster-coloured hexes contiguously, capacity-limited to 12 pairs per cell). Three foreground modes are exposed:

- **`honeycomb`**: cell colour encodes mean signed score gap on a divergent ramp anchored at $\pm 2\,\text{logits}$; cluster borders are drawn between cells with different cluster IDs.
- **`scatter`**: one dot per pair, percentile-clipped (2nd–98th percentile) MDS coordinates; the score-gap ramp is the same as honeycomb mode for cross-mode legibility.
- **`mixed`**: hexes dimmed to 0.55 opacity, dots overlaid at cell-jittered positions, allowing simultaneous reading of cluster geometry and individual-pair noise.

A click on a hex (or a dot, or a lasso brush) selects the pairs and emits `hex-select`; V4 and V5 respond. A *score gap* diverging legend in the header ($-2 \dots +2$) makes the colour ramp self-explaining. Importantly, V3 *masks* dots whose $(h, w)$ pair is in the running accepted set, with the visual encoding reverting to the full ramp on `match-restored`: the canvas thus reflects "what is left to commit" at any point, not the static HGT prediction.

## 5.5 V4 — Bipartite husband–wives detail with batch and per-person profile

V4 unfolds whichever pairs V3 has selected into a bipartite layout: husbands on the left axis, candidate wives on the right, Bézier edges weighted by HGT score (line stroke and a centred score chip). Two operator affordances live here.

First, a *profile popup* opens on any node click, fetching the cleaned-parquet attributes for that person from `/api/profile/{id}`; banner is displayed with the real Eight Banners label (e.g., *Solid White*) and geographic region with the four-district CMGPD-LN code (e.g., *South Liaoning*).

Second, a *batch* button lets the analyst commit, in one stroke, every husband's HGT $\arg\max$ above a configurable score-gap threshold (default 1.0, calibrated to ≈87% precision on the 1882 cohort). Batch commits arrive in V2 with the **HGT**-only chip. A husband-node click also emits `person-selected`, which V5 picks up to load that husband as the negotiation target.

## 5.6 V5 — The agent arena

V5 is the deliberative core of [SYSTEM] and the surface that materialises DG3 and DG4. After a husband is loaded, V5 displays a collapsible *life history* panel summarising:

- a persona headline (LLM-produced from real DS0003 events and income, see §6);
- a chip-row of matched SEAL motifs;
- an event pill strip with year + English label (e.g., 1864 *Birth*, 1880 *In-Marriage*);
- an income trajectory rendered as terraced pips (low / mid / high).

The candidate grid below renders one `CandidateCard` per top-K wife, each with persona summary, round-by-round score pips (`R<N>:t<X>/c<Y>`) for the husband-side score $t_i$ and wife-side score $s_i$, and a chevron that expands the full per-round transcript of queries and answers.

A *hint console* above the grid accepts free-form messages addressed to `@everyone`, `@target`, or specific candidates by ID; submitted hints land in a per-husband `asyncio.Queue` on the server, are drained between rounds, and are interpolated into the next round's prompt as system context.

## 5.7 V6 — Macro and motif rule injector

V6 closes the steering loop. The macro half exposes a small set of sliders (paternal-lineage importance, sibling overlap, household share, banner match, macro era) that re-weight the SEAL motif pre-prior. The motif half exposes four boolean toggles for $\mathsf{m}_1$–$\mathsf{m}_4$, letting the analyst suppress specific motifs from the persona prompt (e.g., to test whether a match still holds without the same-household evidence). A scalar input for $\lambda$ in Eq. 1 is also exposed, enabling sensitivity exploration on the gap penalty.

## 5.8 Linked interaction model

The four bus events — `hex-select`, `person-selected`, `match-accepted`, `match-restored` — form the backbone of inter-view coordination (DG6). The acceptance pipeline threads as follows:

1. V4 batch or V5 final-rank acceptance issues `match-accepted`;
2. V2 prepends the row, V1 reloads its curve, V3 masks the dot, V4 drops the edge from the active selection.

The restoration pipeline is the symmetric reverse on `match-restored`. This single source of truth is what allows [SYSTEM] to behave as a single instrument rather than as a collection of widgets.
