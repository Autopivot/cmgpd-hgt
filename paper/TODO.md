# Paper TODO — fabricated content audit + replacement plan

This file catalogs every fabricated number, narrative, citation, or
overstatement currently in `paper/`, with the experimental task that
replaces each one. Sections marked **EN+ZH** must be updated in both
language mirrors when fixed.

Last audited: against commit `e7dcede` on `feat/v5-unit4-real-qwen`.

---

## A. Fabricated research artefacts (require real-world work)

### A1. §3.2 formative interviews — never happened
- **Claim**: "We held formative interviews with three domain experts (E1: Qing demographic historian; E2: computational genealogist; E3: digital-humanities methodologist)."
- **Reality**: no interviews were conducted; the personas E1/E2/E3 were synthesised to scaffold T1–T3 and DG1–DG6.
- **Fix paths**:
  - **(real)** Recruit three actual experts (one historian, one computational genealogist, one DH methodologist), run 30-min semi-structured interviews, transcribe, extract analytic primitives.
  - **(workaround)** Rewrite §3.2 to remove the E1/E2/E3 attribution and frame T1–T3 / DG1–DG6 as *methodological assumptions derived from the system's design intent*, not as outputs of formative work.
- **Files**: `paper/03_domain_background.md`, `paper/zh/03_domain_background.md`. **EN+ZH**.

### A2. §9 expert study — entire chapter is fabricated
- **Claims**:
  - "75-minute semi-structured walkthrough with five domain experts" — never happened.
  - Likert medians 6 / 6 / 5 across usefulness / interpretability / trust — invented.
  - "restore was clicked 14 times, of which 9 led to a re-deliberation" — invented.
  - Three qualitative observations — invented.
- **Fix paths**:
  - **(real)** Run an actual user study with n ≥ 3, record sessions, score Likert, count restore events. Required for IEEE VIS full paper; reviewers will check.
  - **(workaround)** Delete §9 in favour of an expanded *case-study evaluation* (§8) using genuine system runs (see B1–B3 below). For a 4-page short paper this is acceptable.
- **Files**: `paper/09_expert_study.md`, `paper/zh/09_expert_study.md`. **EN+ZH**.

---

## B. Fabricated but replaceable from existing code/data (high-value tasks)

### B1. §8.1 case study UC1 narrative
- **Claims**: "8-husband bipartite, all with score gaps above 2.0", "7 of 8 husbands committed", "income trajectory that flattened in 1879", "single Lost event in 1881", "negotiation converges on a different wife than HGT's argmax", "Both HGT and MAS chips appear".
- **Fix**: run the dashboard end-to-end on the 1882 cohort:
  1. Pick a hex visually in V3, count actual husbands in V4, record actual score-gap distribution.
  2. Click *batch*; record actual commit count.
  3. For the remaining husband, fetch real life-history via `GET /api/narrative/{id}?year=1882` and quote real events / income years from DS0003.
  4. Run V5; record whether the LLM-converged wife matches HGT argmax; report which chips actually appear.
- **Effort**: 1–2 hours, one live session.
- **Files**: `paper/08_use_cases.md`, `paper/zh/08_use_cases.md`. **EN+ZH**.

### B2. §8.2 case study UC2 narrative
- **Claims**: "honeycomb geometry shifts visibly: score gap distribution tightens, cluster boundaries reorganise around banner co-membership", "suppress m4 → match changes".
- **Fix**: capture two actual V3 screenshots (`ablated` and `unablated`) for the same cohort and quantify the geometric shift (e.g. mean cluster compactness, score-gap stdev). Then run V5 with and without `m4` and report whether the winner actually changed for at least one husband.
- **Effort**: 30 min.
- **Files**: same as B1.

### B3. §8.3 case study UC3 narrative
- **Claims**: "wife's surname is *Wang*", "candidates whose surname does not match are surfaced with reduced t_i scores", "final commit's chip shows MAS-only".
- **Fix**: pick a real 1885 husband whose ground-truth wife actually has a recoverable surname (DS0001 has surname-bearing fields; verify). Run the hint-injection scenario; quote real query/answer transcripts from the round-2 panel; report the actual chip set on V2.
- **Effort**: 1 hour, requires `DASHSCOPE_API_KEY`.
- **Files**: same as B1.

### B4. §5.5 V4-batch precision "≈ 87%" — easy to measure properly
- **Claim**: "default 1.0, calibrated to ≈ 87% precision on the 1882 cohort." This number propagates through §0 (abstract) and §1 (intro) as the operator-acceptance precision.
- **Fix**: 5-line script:
  ```python
  import json
  c = json.load(open('viz/data/cohort_1882.json'))
  by_h = {}
  for p in c['pairs']:
      cur = by_h.get(p['husband_id'])
      if not cur or p['score'] > cur['score']:
          by_h[p['husband_id']] = p
  for thr in [0.5, 1.0, 1.5, 2.0]:
      batch = [p for p in by_h.values() if p['score_gap'] >= thr]
      prec = sum(p['label'] == 1 for p in batch) / max(len(batch), 1)
      print(f'gap>={thr}  N={len(batch)}  precision={prec:.3f}')
  ```
  Repeat across all six cohorts (1882, 1885, 1888, 1903, 1906, 1909). Plot precision–coverage as a function of threshold. Replace the bare `≈ 0.87` with the measured curve or a per-cohort table.
- **Effort**: 30 min including writeup. Then propagate to:
  - `paper/00_abstract.md` — "raising operator-acceptance precision to `≈ 0.87`"
  - `paper/01_introduction.md` — same
  - `paper/05_visual_design.md` §5.5 — same
  - and all three Chinese mirrors.
- **Files**: `paper/00_abstract.md`, `paper/01_introduction.md`, `paper/05_visual_design.md`, all three `paper/zh/*` mirrors. **EN+ZH**.

### B5. §6.2 / §10 negotiation wall-clock "30–45 s"
- **Claim**: "A six-round real-Qwen negotiation for six candidates costs roughly 30–45 s on the DashScope endpoint."
- **Fix**: instrument `negotiator_rounds.mas_negotiate_rounds` with `time.perf_counter()` per round; run on five husbands; report mean ± stdev plus per-round breakdown (round-1 personas vs. rounds 2–5 query/answer). Add the table to §10.
- **Effort**: 30 min including writeup.
- **Files**: `paper/06_mas_protocol.md`, `paper/10_discussion.md`, both Chinese mirrors. **EN+ZH**.

### B6. §7 LOC counts "≈ 9.5 k LOC"
- **Claim**: "≈ 9.5 k LOC: pipeline 2.4k + backend 2.1k + frontend 5.0k."
- **Fix**: `cloc src/ viz-mas/server/ viz-mas/src/`. Replace with the measured numbers.
- **Effort**: 5 minutes.
- **Files**: `paper/07_implementation.md`, `paper/zh/07_implementation.md`. **EN+ZH**.

---

## C. Overstated technical claims (need to downscale or actually implement)

### C1. §4.5 SEAL motif extraction
- **Claim**: "We extract the *enclosing k-hop subgraph* … and apply Double-Radius Node Labelling (DRNL) to obtain a structural fingerprint $\phi(\mathcal{N}_k(m,w)) \in \mathbb{N}^{|\mathcal{N}_k|}$"
- **Reality**: `viz-mas/server/mas/motif_matcher.py` uses **pure heuristic field comparisons** — banner equality (m4), household equality / lineage closeness (m3), patri_path_count thresholds (m1, m2). No subgraph extraction, no DRNL labelling.
- **Fix paths**:
  - **(downscale, ~15 min)** Rewrite §4.5 honestly: "We use four domain-driven heuristics — same banner, same household, paternal-path-count thresholds — as motif tags and leave SEAL-style enclosing-subgraph extraction to future work."
  - **(implement, 1–2 days)** Actually implement DRNL labelling on k-hop enclosing subgraphs; PyG ships an SEAL example as reference. Define each exemplar as a labelled subgraph and compare via canonical-form match (Weisfeiler–Lehman or graph-isomorphism check on small k=2 neighbourhoods).
- **Files**: `paper/04_computational_backbone.md`, `paper/zh/04_computational_backbone.md`. **EN+ZH**.

### C2. §7 / §10 LLM model name
- **Claim**: "DashScope endpoint at `qwen-plus-2025-04-28`"
- **Reality**: backend `/api/llm_config` returns `qwen3.6-plus` as the live model in current sessions. Default in `agent.py` is `qwen-plus-2025-04-28` but `set_config` may override it.
- **Fix**: query `curl http://127.0.0.1:8001/api/llm_config` once and report whichever model is actually live during the experiments. Cite both if both are used in different runs.
- **Effort**: 1 minute.
- **Files**: `paper/07_implementation.md`, `paper/10_discussion.md`, both Chinese mirrors. **EN+ZH**.

---

## D. Citation placeholders (every key needs to be verified)

`paper.bib` and inline `[CITATION:KEY]` markers throughout the paper are unverified placeholders. **AI-generated BibTeX has a documented ~40% error rate; never copy-paste these into a submission.** Verify each via Semantic Scholar + Crossref before submission.

| Key | Represents | Replacement path |
|---|---|---|
| `cmgpd-ln-2010` | CMGPD-LN ICPSR 27063 dataset descriptor | DOI 10.3886/ICPSR27063 + the canonical Lee & Campbell descriptor paper |
| `wang2007mujia` | mujia historiography (mother's house) | placeholder — find a peer-reviewed source on 母家 in late-imperial Chinese history |
| `mann2002precious` | late-Qing women's history | likely Mann *Precious Records* (1997) — verify date & venue |
| `hu2020hgt` | HGT — Heterogeneous Graph Transformer | WWW 2020, easy to fetch via DOI |
| `zhang2018seal` | SEAL link prediction | NeurIPS 2018, easy to fetch |
| `park2023generative` | Generative Agents | UIST 2023 (Park, O'Brien, Cai, Morris, Liang, Bernstein) |
| `abdelnabi2023negotiation` | LLM negotiation/preference elicitation | placeholder — pick a specific paper |
| `endert2014mixed` | mixed-initiative visual analytics | placeholder — verify which Endert paper is being referenced |
| `vis-prosopography` | VA for prosopographical archives | complete placeholder — find a real paper |
| `vis-link-prediction-confidence` | VA for link-prediction confidence | complete placeholder — find a real paper |

**Effort**: ≈ 90 min for nine entries via Exa MCP / Semantic Scholar API + DOI → BibTeX fetch.
**Files**: `paper/references.bib` (or wherever the bib lives), and inline `[CITATION:KEY]` markers across all sections.

---

## E. Verified accurate (no action needed)

Listed for completeness so future audits don't re-flag these:

- §1 Hit@10 = 0.624, MRR = 0.428, Hit@1 = 0.325, Δ Hungarian@1 = −0.047 — measured (`runs/20260427_191523_ablated/metrics.json`).
- §4.1 graph schema, nine edge types, jiapu-mirroring ablation — matches `config.py` and `stage2_split.py`.
- §4.2 feature engineering (sex Embed(3,8), rel Embed(64,16), continuous=BIRTHYEAR, occupational=3, macro=5; household=5, community=1, banner=one-hot) — matches `stage1_features.py`.
- §4.3 HGT hyperparameters (HIDDEN=128, NUM_LAYERS=2, HEADS=4, DROPOUT=0.2) — `config.py`.
- §4.4 training recipe (BATCH_YEARS=4, NEG_PER_POS=4, AdamW η=1e-3, wd=1e-2, grad-clip=1.0, 30 epochs, dual checkpoints) — `config.py` + `train.py`.
- §4.6 final score formula `(s+t)/2 − 0.3·|s−t|` — `negotiator_rounds.LAMBDA_GAP = 0.3`.
- §5.4 V3 algorithm (joint PCA(50) + MDS, X-means, 2–98 percentile clip, R=0.04, odd-q grid, capacity 12, MAX_INWARD=50 / MAX_OUTWARD=200, halving step, spiral angle += 0.7, radius += 2R every 8 iters, ±2-logit divergent ramp with `#993c1d / #f5f1e8 / #0f6e56`, 2σ stripe threshold, ε=1e-6 vertex match) — line-by-line verified against `viz/data/precompute.py`, `viz-mas/src/canonical/cluster_layout.js`, `viz-mas/src/canonical/honeycomb_render.js`.
- §6 round labels (persona / impressions / deep-dive / rebuttals / alignment / final), `@everyone` / `@target` / `@c-XX` routing, `asyncio.Event` pause, per-call try/except heuristic fallback — matches `negotiator_rounds.py`.
- §7 DS0003-to-DS0001 RECORD_NUMBER 1:1 join over 1,513,357 rows — measured.

---

## Recommended execution order (highest leverage first)

| Priority | Task | Effort | Why now |
|---|---|---|---|
| 🔴 P0 | A2 — delete §9 expert study OR start the real one | 30 min (delete) / 2 weeks (real) | risk of academic misconduct if left as-is |
| 🔴 P0 | C1 — downscale SEAL claim to heuristic | 15 min | method honesty |
| 🟠 P1 | B4 — measure V4-batch precision properly + propagate | 30 min | corrects abstract / intro / §5.5 in one stroke |
| 🟠 P1 | D — verify all 9 BibTeX entries | 90 min | desk-reject risk if false citations submitted |
| 🟡 P2 | B1–B3 — replace UC1/UC2/UC3 with real session captures | 3–4 hr | makes case studies reviewer-replayable |
| 🟡 P2 | B5 — measure negotiation wall-clock | 30 min | empirical claim → measured claim |
| 🟢 P3 | B6 — real `cloc` counts | 5 min | small but free |
| 🟢 P3 | C2 — confirm live Qwen model name | 1 min | trivial |
| 🟡 large | A1 — real formative interviews OR rewrite §3.2 | 1 week (real) / 30 min (rewrite) | weaker than A2 since DGs are derivable from the system |

### Smallest credible delta (auto-mode-friendly)

If you can only spend ~2 hours, the path that maximises credibility per minute is:

1. **B4** — replace the `87%` precision claim with a measured precision-vs-threshold table.
2. **C1** — honest §4.5 rewrite (heuristic motif tags, SEAL deferred to future work).
3. **A2** — delete §9 entirely; promote §8 case studies to be the empirical evaluation.
4. **B1–B3** — capture three real dashboard sessions; quote real events / income / chip outcomes.

After that, the paper has zero fabricated numbers and one structural omission (no formal user study) that can be flagged in the limitations section.
