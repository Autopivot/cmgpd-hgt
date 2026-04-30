# Case Study — Cell #136: 1882 calibration → 1885 transfer

## 1. Setup

**Cohort**: CMGPD-LN, ablated (maternal edges removed during message-passing).
**Years**: 1882 (full GT, training mode) → 1885 (no GT, transfer mode).
**Hex cell**: #136 in the 1882-anchored MDS frame, centroid `(cx=0.480, cy=0.554)` in the canonical [0,1]² space. The same cell-id resolves to the same centroid in 1885 within Δ ≤ 0.0003 because all later years are KNN-projected onto the 1882 PCA-MDS basis (`viz/data/anchor_1882_ablated.npz`).

Cell #136 is one of 288 populated hex cells in the V3 honeycomb. We picked it because (a) it carries five distinct husbands in 1882, (b) two of them have ground-truth wives that fall inside the cell, and (c) the cell sits in a moderate-density region of `train_ref_coords` so transfer should be neither trivial nor extrapolative.

## 2. 1882 — what's in the cell

| Husband | K candidates | GT wife | GT rank | Hungarian correct? | Notes |
|---|---|---|---|---|---|
| P23497  | 4 | P24248  | 1 | ✓ | `same_lineage=true`, `patri_path_count=9` (deep paternal chain), best-neg score gap +0.08 |
| P215824 | 2 | — (no GT in this cell) | — | n/a | two near-identical scores (8.09, 8.09) — likely sibling pair as candidates |
| P164103 | 3 | — | — | n/a | top two scores tied at 9.27 (twins/cousins?) |
| P91527  | 1 | — | — | n/a | only one candidate, score 7.73, gap +0.15 |
| P77574  | 2 | P79028  | 1 | ✓ | `same_lineage=true`, `patri=2`, gap +0.02 (HGT barely got it right) |

The two GT-bearing husbands both committed via Hungarian — recall@1 in this cell is 2/2 = 1.00 in the eval frame. The remaining three husbands have only hard-negatives sampled into this cell (the cohort is sampled, not exhaustive).

## 3. 1882 — analyst-tuned per-husband rule sheets

For each husband the analyst observes the V5 MAS rounds (persona → impressions → deep-dive → rebuttals → alignment → final) and re-weights the four similarity metrics + the motif catalog from V6's RuleWeightsEditor. The weights below are what we recorded after one full pass (sliders are 0.00–2.00, step 0.05; motif checkboxes are binary).

| Husband | paternal | siblings | household | banner | M01 | M02 | M03 | M10 | banner-CTX | community-CTX | co-res | region |
|---|---:|---:|---:|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| P23497  | **1.65** | 0.85 | 0.95 | **1.55** | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P77574  | 1.30 | 0.95 | 1.10 | 1.20 | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P215824 | 0.85 | **1.70** | 1.30 | 1.05 | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ |
| P164103 | 0.95 | 1.20 | 1.25 | **1.45** | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ |
| P91527  | 1.00 | 1.00 | 1.00 | 1.00 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Reasoning behind the manual tunings:

- **P23497**: GT wife P24248 has `patri_path_count=9` and same lineage. The MAS rounds repeatedly cite "shared paternal banner" as the deciding evidence, so the analyst lifts `paternal_lineage_proximity` to 1.65 and `same_banner` to 1.55. M01/M02 stay on (direct sibling + shared-father motifs are exactly the kin patterns the persona surfaces).
- **P77574**: `patri=2` (cousin-tier), GT scraped through with gap +0.02 — close call. The analyst keeps weights moderate (1.10–1.30) without aggressive priors so the prior doesn't over-anchor when transferred.
- **P215824**: two near-identical scores 8.09/8.09 — V6 motif detection flags M03 (two-degree sibling chain) consistently. Sibling weight pushed to 1.70; M02 disabled because the candidates do *not* share a father with the husband.
- **P164103**: three candidates with twin top scores 9.27/9.27 — analyst weighs banner endogamy 1.45 (the only field that breaks the tie in the persona text).
- **P91527**: K=1 (no comparison), defaults preserved.

## 4. Aggregate → save to cell

Clicking **💾 save to cell** at year=1882 aggregates the five sheets:

- Mean weights: `paternal=1.15, siblings=1.14, household=1.12, banner=1.25`.
- OR-reduce motifs: every motif has at least one husband endorsing it → all eight catalog + CTX flags stay enabled.

The POST `/api/cell-rules/136` records:

```json
{
  "cell_id": 136,
  "year": 1882,
  "n_husbands": 5,
  "weights": {
    "paternal_lineage_proximity": 1.15,
    "shared_siblings": 1.14,
    "same_household_history": 1.12,
    "same_banner": 1.25
  },
  "motifs_enabled": {
    "M01_direct_sibling": true, "M02_shared_father_via_fs_fd": true,
    "M03_two_degree_sibling_chain": true, "M10_household_mediated_daughter": true,
    "CTX_same_banner": true, "CTX_same_community": true,
    "CTX_co_resident": true, "CTX_same_region": true
  },
  "updated_at": "2026-04-30T19:41:45+00:00"
}
```

The V3 hex now carries a gold dot indicator on cell #136. The V6 chip switches from `cell #136 · unbound` to `cell #136 · 5 bound · last saved 2026-04-30T19:41:45+00:00`.

## 5. 1885 — same cell, different cohort

Switching the year segment to **1885** flips the mode banner from green training to blue transfer and re-fetches `/api/embedding/1885`. Cell #136 in the 1885 layout stays at `(cx=0.480, cy=0.554)` because both years share the 1882-anchored PCA-MDS frame.

What changes is the cell's **occupancy** — 1885 sampling gives cell #136 a different population:

| Metric | 1882 | 1885 |
|---|---|---|
| n_pairs in cell | 12 | 12 |
| n_husbands | 5 | 11 |
| First five husbands | P23497, P77574, P215824, P164103, P91527 | P91883, P202442, P77492, P78686, P151318, … |
| GT wives in cell | 2 (P24248, P79028) | n/a — GT not used |

The 1885 husbands are *new individuals* — the cohort sampler picked different people in this region of the embedding space. None of the five 1882 husbands appear; the calibration we saved is therefore being applied **across persons**, anchored only by their shared MDS neighbourhood.

## 6. Transfer effect on V6

Clicking cell #136 in 1885:

- V6 header: `cell #136 · 5 bound · last saved 2026-04-30T19:41:45+00:00` (the *1882* timestamp).
- Mode banner: blue, "transfer mode · 1885 (no GT) — V6 cell rules loaded from 1882; sliders read-only".
- 💾 save-to-cell button: hidden (not editable in transfer mode).
- Clicking any 1885 husband (e.g. P91883) populates V6 with that husband's similarity bars + motifs. The RuleWeightsEditor sliders auto-fill from the 1882 cell profile and grey out:

| Slider | Value (read-only) |
|---|---:|
| paternal | 1.15 |
| siblings | 1.15 (slider step rounds 1.14 → 1.15) |
| household | 1.10 (rounds 1.12 → 1.10) |
| banner | 1.25 |

All eight motif checkboxes are pre-checked.

## 7. MAS prompt injection — backend confirmation

Pressing **▶ arena** for P91883 in 1885 sends a `POST /api/negotiate/P91883` body that now includes the cell_rules payload. The backend orchestrator's start frame on the WebSocket carries:

```json
{
  "type": "start",
  "husband_id": "P91883",
  "year": 1885,
  "ablation": "ablated",
  "cell_rules_attached": true
}
```

The round-1 `query.txt` template renders with the new `{cell_rules_block}` populated:

```
PRIOR CALIBRATION FROM 1882 COHORT (same MDS region):
  - paternal lineage proximity: weight 1.15
  - shared siblings:            weight 1.14
  - same household history:     weight 1.12
  - same banner:                weight 1.25
  Active motifs: CTX_co_resident, CTX_same_banner, CTX_same_community,
                 CTX_same_region, M01_direct_sibling,
                 M02_shared_father_via_fs_fd,
                 M03_two_degree_sibling_chain,
                 M10_household_mediated_daughter.
  Treat these weights as a SOFT prior — they reflect how much each
  similarity feature mattered for accepted matches at this point in the
  kinship-embedding space last cohort. Adjust your scoring accordingly
  when candidates differ along these dimensions.
```

The husband-side (target) LLM thus enters round 1 with explicit guidance that *banner endogamy* and *paternal lineage* mattered most for the analyst's previous accepts in this MDS region — exactly the pattern the 1882 cell was tuned to.

## 8. Findings & takeaways

1. **The cell-id stays stable across years** when MDS is anchored on 1882: cell #136 in 1885 is at the same (cx, cy) as in 1882 (Δ < 0.0003). Without the anchor (per-year MDS fits) cell ids would drift unpredictably and per-cell rule profiles couldn't transfer.
2. **The transfer is across persons, not across the same individuals**. The five 1882 husbands in cell #136 do not appear in 1885; the eleven 1885 husbands are new. The prior is saying "people in this region of the kinship embedding tend to be decided by banner + paternal lineage" — a population-level claim, not a per-person memo.
3. **The historian's edit budget shrinks dramatically in transfer mode**. In 1885 cell #136, the V6 sliders are read-only — there's no per-husband re-tuning loop. The 1882 calibration is the only intervention; the LLM does the rest with the prior baked into round-1 prompts.
4. **A failure mode worth flagging**: the 1885 husband P91883 may be in a banner that *didn't* dominate accepts in 1882 cell #136 — the prior would then push the LLM toward a wrong answer with no GT to correct it. Defending the deployed reconstruction therefore requires either (a) a held-out 1885 sample with hand-validated wives to spot-check, or (b) a confidence threshold from the backbone HGT score that gates which 1885 cells inherit a 1882 prior at all.
5. **The bound-cell indicator** (gold dot on V3) lets the analyst see at a glance which regions of 1885's embedding are "covered" by 1882 calibration. Empty regions need either fresh 1882-sampled tuning (harder — would require resampling 1882 cohort to populate cell) or a fallback to the no-prior path.

## 9. Reproduction recipe

```python
# 1. start backend + Vite preview
cd viz-mas/server && python -m uvicorn server.main:app --port 8001 &
cd viz-mas && npm run dev

# 2. open http://127.0.0.1:5190, year = 1882, click hex cell #136 in V3.
# 3. for each husband appearing in V4 bipartite view, click the husband node.
#    Adjust V6 RuleWeightsEditor sliders + motif checkboxes (see §3 table).
# 4. click "💾 save to cell" in V6 header → cell #136 binds.
# 5. switch year segment to 1885 → V6 header chip stays "cell #136 · 5 bound".
# 6. click any 1885 husband node in V4 → V6 sliders auto-fill from 1882 profile.
# 7. press ▶ arena → /negotiate carries cell_rules; round-1 prompt renders
#    "PRIOR CALIBRATION FROM 1882 COHORT" block as shown in §7.

# verify backend persistence:
curl http://127.0.0.1:8001/api/cell-rules/136?year=1882
curl http://127.0.0.1:8001/api/cell-rules           # listing all bound cells
```

## 10. Artifacts

- `viz/data/cohort_1882.json`, `cohort_1885.json` — regenerated with 1882-anchored MDS
- `viz/data/anchor_1882_ablated.npz`, `anchor_1882_unablated.npz` — saved scaler + PCA + reference coords
- `viz-mas/server/data/cell_rules.json` — persisted cell #136 profile (after the walkthrough)
- `viz-mas/server/api/cell_rules_endpoint.py` — REST surface
- `viz-mas/server/mas/negotiator_rounds.py:_format_cell_rules_block` — prompt formatter
- `viz-mas/server/mas/prompts/query.txt` — `{cell_rules_block}` placeholder
- `viz-mas/src/components/v6/RuleWeightsEditor.vue` — sliders + motif checkboxes
- `viz-mas/src/components/RulerInjectorView.vue` — hex-select binding + save button
- `viz-mas/src/components/HexEmbeddingView.vue` — 1882 contour reuse + bound-dot rendering
- `viz-mas/src/components/AgentBattleView.vue` — V5 → /negotiate cell_rules forwarding
