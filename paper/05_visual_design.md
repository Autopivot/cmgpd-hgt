# 5 [SYSTEM]: Visual Analytics Design

## 5.1 System overview

**[SYSTEM]** is laid out as a 3-column, 2-row grid of six linked views, backed by a FastAPI server with WebSocket fan-out for the agent stream (Fig. 1). The frontend is a Vue 3 + Vite single-page application that holds an in-memory cohort context and routes selection events through a shared bus (`hex-select`, `person-selected`, `match-accepted`, `match-restored`). The backend caches the cleaned CMGPD-LN parquet, the HGT-trained model checkpoint, and DS0003-derived per-person life histories.

> **Figure 1 (caption).** [SYSTEM] at a glance. Six linked views (V1–V6) cooperate through a shared event bus. V3's honeycomb cohort canvas drives selection; V4 unfolds the bipartite detail; V5 hosts the six-round agent negotiation; V2 records every commit with a multi-label provenance tag; V1 tracks the running MAS recall@1 against the static HGT baseline; V6 surfaces the kinship neighbourhood of the husband alongside that of every top-$K$ candidate so the analyst can see, at a glance, what immediate-family social context each agent is reasoning over. Every commit is one-click reversible.

## 5.2 V1 — Acceptance curve and ablation diagnostic

The leftmost top panel anchors the session in evaluation context. The *x*-axis advances in cumulative *accepted-edge* ticks; the *y*-axis plots the running recall@1 of the operator's commits against the cohort's known ground truth. A horizontal reference line marks the static HGT-only baseline, computed via per-cohort Hungarian assignment. The curve is updated reactively on `match-accepted` and `match-restored`, so the analyst sees in real time whether the LLM-augmented pipeline is closing or widening the gap to the bare HGT ceiling.

*Encoding choice:* we use a step function rather than a smoothed line to make the contribution of each individual commit visible; the rationale is that this view is also a self-audit instrument (DG2).

## 5.3 V2 — Processed pairs with multi-label provenance

V2 is the persistent record of *what has been committed so far*. Every accepted match appears as a row carrying husband ID, wife ID, HGT score, score gap, the pair's Hungarian-decoder verdict, and the core artefact of [SYSTEM]: a *source* chip set. The chip rules are:

- A commit produced by V4's batch operation receives the chip **HGT** (sage green). Batch always selects the husband's $\arg\max$ by HGT score, so the tag is unambiguous.
- A commit produced by V5's MAS arena receives the chip **MAS** (amber). If the MAS-chosen wife coincides with the husband's HGT $\arg\max$, the row carries *both* chips, signalling convergent agreement of the two pipelines.

A trailing ↶ *restore* button on every row issues an HTTP `POST` to `/api/negotiate/{id}/restore`, removes the entry from the in-memory accept log, and broadcasts `match-restored` on the bus, which causes V1's curve to recompute, V3's masked dot to reappear, and V4's bipartite edge to re-enter selection if its hex is currently active. This is DG5 materialised: a single click rolls a bad commit back across all four dependent views.

## 5.4 V3 — Honeycomb embedding canvas

V3 carries the cohort-as-canvas requirement (DG1). The view consists of four computational stages and four overlaid render layers.

### 5.4.1 Pair embedding pipeline (upstream, Python)

For every test pair $(m, w)$ we first form a 128-dim *pair-interaction vector*

$$
z_{m,w} \;=\; W_1\,[\,h_m\,\Vert\,h_w\,\Vert\,|h_m - h_w|\,\Vert\,h_m \odot h_w\,] \;\in\; \mathbb{R}^{128}
$$

— precisely the first hidden activation of the marriage scorer (§4.3), so the V3 geometry is anchored to the same representation that drives the ranking. We additionally sample up to $S=1000$ positive pairs from the train bucket and project them through the same scorer head; let $Z_{\text{test}} \in \mathbb{R}^{n \times 128}$ and $Z_{\text{train}} \in \mathbb{R}^{S \times 128}$.

A **single joint MDS frame** is fit on the concatenation:
1. Standardize $Z = [Z_{\text{test}};\,Z_{\text{train}}]$ column-wise (zero mean, unit variance).
2. Reduce to $r = \min(50, n + S, 128)$ components via PCA on $Z$.
3. Form the $(n+S) \times (n+S)$ Euclidean dissimilarity matrix $D_{ij} = \|z^{\text{PCA}}_i - z^{\text{PCA}}_j\|_2$, symmetrise as $(D + D^\top)/2$, zero the diagonal.
4. Fit metric MDS with $D$ as a precomputed dissimilarity to two components (`n_init=1, max_iter=200, normalized_stress="auto", random_state=0`); the first $n$ rows of the resulting matrix are the cohort coordinates $\hat{u}_i \in \mathbb{R}^2$, the remaining $S$ rows form a *training-reference background* the dashboard renders as a density heatmap.

Joint fitting matters: it places test and train pairs in the *same* 2-D frame, so the heatmap is comparable across modes. Cluster assignments are then computed on the post-PCA latents $z^{\text{PCA}}$ (not MDS, where small distortions can corrupt boundaries) by X-means with the BIC split criterion bounded above by $k_{\max} = 10$; falling back to $K$-means with silhouette selection over $K \in [2, \min(k_{\max}, \lfloor n/5 \rfloor)]$ if `pyclustering` is unavailable. Both the $\hat{u}_i$ and the cluster labels $\kappa_i \in \{0, \dots, K-1\}$ ship in the cohort JSON consumed by the frontend.

### 5.4.2 Coordinate normalisation

Raw MDS coordinates routinely have a few extreme outliers that stretch the $\min/\max$ envelope by 3–5×, compressing 90% of the cohort into 6% of the canvas. We instead clip to the 2nd–98th percentile bounds before mapping to the unit square:

$$
u_{i,j} \;=\; \mathrm{clip}\!\left(\frac{\hat{u}_{i,j} - q_{2}(\hat{u}_{:,j})}{q_{98}(\hat{u}_{:,j}) - q_{2}(\hat{u}_{:,j})},\; 0,\; 1\right), \quad j \in \{x, y\}.
$$

The same percentile bounds are reused by the scatter mode and the heatmap, so the three foreground modes share one frame.

### 5.4.3 Flat-top hex grid

We tile $[0,1]^2$ with flat-top hexagons of circumradius $R = 0.04$ in normalised units (≈ 30 px on a 750-px canvas). Cells are addressed by axial offset coordinates $(q, r)$:

$$
\textsf{cx}(q, r) \;=\; 1.5R\,q, \qquad
\textsf{cy}(q, r) \;=\; \sqrt{3}\,R\,r \;+\; \begin{cases} \tfrac{\sqrt{3}}{2}R & q \text{ odd} \\ 0 & q \text{ even} \end{cases},
$$

i.e. odd-$q$ offset, with column step $1.5R$ and row step $\sqrt{3}\,R$. The six vertices of cell $(q, r)$ are $(\textsf{cx} + R\cos\theta_k,\; \textsf{cy} + R\sin\theta_k)$ for $\theta_k = k\pi/3$, $k = 0, \dots, 5$. We retain a one-radius margin so cells whose centres lie just outside $[0,1]^2$ but whose interiors clip the canvas survive. Yields $\approx 350$–$500$ cells for $R = 0.04$, small enough that linear-scan nearest-cell queries beat KD-tree construction on every packing step.

The neighbour map for `cluster-borders` is precomputed once: for cell $(q, r)$, the six axial neighbours are

$$
\mathcal{N}(q, r) \;=\; (q, r) \;\oplus\;
\begin{cases}
\{(+1,0),(+1,-1),(0,-1),(-1,-1),(-1,0),(0,+1)\} & q \text{ even} \\
\{(+1,+1),(+1,0),(0,-1),(-1,0),(-1,+1),(0,+1)\} & q \text{ odd}.
\end{cases}
$$

### 5.4.4 Iterative inward-attraction packer

Each pair $i$ has a normalised position $u_i$, a cluster label $\kappa_i$, and a target *cluster centroid* $c_{\kappa_i} = \mathbb{E}_{j:\,\kappa_j = \kappa_i}[u_j]$ in the same frame. We pack pairs into hex cells under three constraints:

- **(C1) Same-cluster cells**: every cell holds points from at most one cluster;
- **(C2) Capacity**: each cell holds at most $C = 12$ points;
- **(C3) Cluster compactness**: each cluster's cells should form a contiguous island around $c_{\kappa}$.

Algorithm (Algorithm 2): sort pairs by $\|u_i - c_{\kappa_i}\|_2$ ascending, so the densest core of each cluster is placed first and claims the central hexes; outliers spiral outward.

```
for each i in order:
    p ← u_i;  cl ← κ_i;  c ← c_cl;  placed ← False

    # ── inward attraction (geometric series collapse to centroid) ──
    for it = 1 .. 50:
        p ← (p + c) / 2                          # halve gap each iter
        cell ← argmin_{cells} ||p - centre(cell)||²
        if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
            cell.add(i);  placed ← True;  break

    # ── outward radial spiral fallback ──
    if not placed:
        radius ← 2R;   angle ← Uniform(0, 2π)
        for it = 1 .. 200:
            p ← c + (radius·cos angle, radius·sin angle)
            cell ← argmin_{cells} ||p - centre(cell)||²
            if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
                cell.add(i);  placed ← True;  break
            angle ← angle + 0.7         # rotate ≈ 40°
            if it mod 8 == 7: radius ← radius + 2R   # archimedean step

    # ── last-resort sweep (rare in practice) ──
    if not placed:
        for cell in cells:
            if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
                cell.add(i);  break
```

The inward loop's halving step has a closed-form bound: after $t$ iterations, $\|p^{(t)} - c\| = 2^{-t}\,\|u_i - c\|$, so within 6–7 iterations the candidate position is well inside the centroid's hex. The outward fallback runs an Archimedean spiral $r(\theta) = 2R\,(1 + \lfloor\theta/(8 \cdot 0.7)\rfloor)$ around the centroid; the angular step of $0.7\,\text{rad}$ is approximately the angle subtended by one hex at radius $2R$, ensuring near-uniform coverage of each ring before stepping outward.

### 5.4.5 Per-cell aggregates

For each non-empty cell with occupants $P_c$ we compute four diagnostic aggregates:

$$
\textsf{meanScoreGap}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathrm{gap}(p),
\qquad
\textsf{posRatio}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathbb{1}[\mathrm{label}(p) = 1],
$$
$$
\textsf{patriPathMean}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathrm{patriPathCount}(p),
\qquad
\textsf{sameLinFrac}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathbb{1}[\mathrm{sameLineage}(p)].
$$

`meanScoreGap` drives the divergent fill; `posRatio` drives the outlier-stripe overlay; `patriPathMean` and `sameLinFrac` surface in tooltips for cell-level inspection.

### 5.4.6 Render layers and visual encoding

Layer 1 — **hex cells**. Cell fill follows a three-stop divergent ramp on `meanScoreGap`, anchored at $\pm 2$ logits and interpolated linearly in sRGB:

$$
\mathrm{color}(v) = \begin{cases}
\mathrm{lerp}(\mathsf{COLOR\_LOW},\,\mathsf{COLOR\_MID},\,(v + 2)/2) & -2 \le v < 0 \\
\mathrm{lerp}(\mathsf{COLOR\_MID},\,\mathsf{COLOR\_HIGH},\,v/2) & 0 \le v \le +2 \\
\mathsf{COLOR\_LOW} & v < -2 \\
\mathsf{COLOR\_HIGH} & v > +2
\end{cases}
$$

with $\mathsf{COLOR\_LOW} = \texttt{\#993c1d}$ (terracotta), $\mathsf{COLOR\_MID} = \texttt{\#f5f1e8}$ (cream), $\mathsf{COLOR\_HIGH} = \texttt{\#0f6e56}$ (sage). Anchors at $\pm 2$ are deliberate: per-pair $\mathrm{gap} \in [-13, +13]$ but cell-mean values concentrate by averaging up to 12 pairs, so most cells sit in $[-2, +2]$; wider anchors washed out the diverging signal in pilot studies.

Layer 2 — **outlier stripes**. Let $\mu = \mathbb{E}[\textsf{posRatio}_c]$ and $\sigma = \mathrm{Std}[\textsf{posRatio}_c]$ over non-empty cells. Cells with $|\textsf{posRatio}_c - \mu| > 2\sigma$ receive a 45°-rotated stripe overlay (4 px period, 1.5 px stroke, 60% opacity), flagging a structurally over- or under-positive cluster pocket without disturbing the underlying fill.

Layer 3 — **cluster borders**. For every neighbour pair $(c_a, c_b) \in \mathcal{N}$ with $\mathrm{cluster}(c_a) \ne \mathrm{cluster}(c_b)$ and both non-empty, draw the shared edge — i.e. the two vertices both polygons hold in common, located by an $\varepsilon = 10^{-6}$ coordinate match on the projected vertex set.

Layer 4 — **dot scatter** *(modes `scatter` and `mixed` only)*. One dot per pair at $u_i$ (or at $\textsf{centre}(\textsf{cell}(i)) + \delta_i$ where $\delta_i$ is a deterministic hash-jitter inside the cell, in `mixed` mode); the same divergent ramp is applied to per-pair $\mathrm{gap}$ for cross-mode legibility. The mode toggle exposes three readings:
- **`honeycomb`** — clusters and their density readable at a glance.
- **`scatter`** — individual-pair noise visible.
- **`mixed`** — hexes dimmed to opacity 0.55, dots overlaid; supports drilling into a specific pair without losing cluster context.

### 5.4.7 Selection and acceptance masking

A click on a hex (or a dot, or a lasso brush in scatter mode) selects the underlying pairs and emits `hex-select`; V4 and V5 respond. A *score gap* divergent legend in the header ($-2 \dots +2$) makes the ramp self-explanatory. Crucially, V3 *masks* dots whose $(h, w)$ pair is in the running accepted set, with the encoding reverting to the full ramp on `match-restored`: the canvas thus reflects *what is left to commit* at any point, not the static HGT prediction.

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

## 5.7 V6 — Kinship neighbourhood graph

V6's purpose is to make the *immediate-family social context* of every actor in the current negotiation directly visible. As the analyst drives V4 → V5, V6 displays the husband currently loaded in V4 together with the top-$K$ candidates surfaced in V5, each surrounded by their one-hop kin, so it is obvious at a glance whether two candidates share a father, a mother, or a sibling, and whether the husband's family overlaps any candidate's family.

*Subgraph definition.* For every focal person $p \in \{x\} \cup \{y_1, \ldots, y_K\}$ (the husband and the $K$ candidates) we extract the $k = 1$ ego-graph restricted to `person` nodes and to the kinship edge subset

$$\mathcal{E}_{\mathrm{kin}} \;=\; \{r_{fs},\, r_{fd},\, r_{ms},\, r_{md},\, r_{sib}\},$$

i.e. paternal son / daughter, maternal son / daughter, and sibling. Higher $k$ is deferred to future work — at $k = 1$ the per-focal neighbourhood is small (parents, children, siblings: typically a single-digit count of nodes) so a $1 + K$ ego union can be laid out and animated interactively without aggregation. The subgraphs are rendered as the *union* of their ego-graphs in a single force-directed canvas; shared kin (e.g., two candidates who share a father) appear once, as the connecting node, which is precisely the relational fact V6 is designed to make legible.

*Visual encoding.* The husband node is filled green at radius $r = 9$; candidate nodes are filled amber at $r = 8$ and carry a stroke ring to distinguish them from ordinary kin; all other person nodes (parents, siblings, children) are light grey at $r = 5$. Edges are colour-neutral grey but stroke-styled by kinship channel: paternal edges ($r_{fs}, r_{fd}$) are *solid*, maternal edges ($r_{ms}, r_{md}$) are *dashed*, and sibling edges ($r_{sib}$) are *dotted*. On `match-accepted`, an additional $r_{hw}$ edge is drawn between the husband and the accepted candidate, in the canonical [SYSTEM] terracotta `#993c1d` at stroke width 2, so the committed marriage stands out from the kinship scaffolding.

*Layout and interaction.* The canvas runs a d3-force simulation (link distance ≈ 30 px, charge ≈ −80, plus a centring force and a collision force) restarted with $\alpha = 0.3$ on every cohort-context update for warm restart. The analyst can drag a node to pin it (d3-drag freezes the node on release; double-click releases it back to the simulation) and zoom the canvas with the mousewheel and pan by dragging empty space, both routed through `d3.zoom` with scale extent $[0.3, 4]$. Hovering a node reveals a tooltip with `{id, sex, role, relation-to-focal}`.

*Accept cascade.* When the analyst accepts a candidate $y_i$ in V5, the bus emits `match-accepted`; V6 inserts the new $r_{hw}$ edge as described above and runs a 200 ms d3 transition fading every node and edge that belongs *only* to a non-winning candidate's ego-graph to opacity 0.25, leaving the husband's ego and the winner's ego at full opacity. On `match-restored` the symmetric reverse runs: the $r_{hw}$ edge is removed and all opacities transition back to 1.0. The result is that V6 acts as a real-time *witness* to the negotiation outcome: which family was joined, and which families were not.

*Future work.* The current implementation is fixed at $k = 1$; arbitrary $k$ (multi-hop kinship) is left to a follow-up release because the layout and the colour-by-relation legend both require redesign once second-degree kin (grandparents, cousins) and household / community nodes are admitted.

## 5.8 Linked interaction model

The four bus events — `hex-select`, `person-selected`, `match-accepted`, `match-restored` — form the backbone of inter-view coordination (DG6). The acceptance pipeline threads as follows:

1. V4 batch or V5 final-rank acceptance issues `match-accepted`;
2. V2 prepends the row, V1 reloads its curve, V3 masks the dot, V4 drops the edge from the active selection.

The restoration pipeline is the symmetric reverse on `match-restored`. This single source of truth is what allows [SYSTEM] to behave as a single instrument rather than as a collection of widgets.
