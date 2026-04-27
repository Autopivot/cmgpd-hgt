# Repository Structure

This is the canonical workspace for the CMGPD-HGT project — HGT marriage-edge prediction backed by a six-panel visual analytics interface.

```
cmgpd-hgt/
├── README.md                 Entry point: setup, dependencies, run commands
├── CLAUDE.md                 Architecture notes for Claude Code
├── requirements.txt          Top-level pipeline + ML deps (PyTorch, PyG, etc.)
├── .gitignore                Excludes data/, runs/, checkpoints/, .venv/, etc.
│
├── src/                      ── HGT TRAINING PIPELINE
│   ├── config.py               Single source of truth: paths, year cuts,
│   │                           feature lists, hyperparameters, ablation set
│   ├── stage0_data.py          .rda → cleaned parquet → HeteroData graph cache
│   ├── stage1_features.py      Attach per-node features + macro_table
│   ├── stage2_split.py         compute_cohort_split + ablate_maternal_edges
│   ├── stage3_temporal.py      subgraph_at_year (no-future-leakage invariant)
│   ├── train.py                Per-cohort training loop, BCE on within-cohort negs
│   ├── evaluate.py             ROC-AUC, PR-AUC, Hungarian recall@1, Hit@K, MRR
│   ├── temporal_indicators.py  Macro covariates from DS0009 + DS0011
│   ├── sampling.py             Within-cohort negative sampling
│   └── model/hgt.py            HGT encoder + MarriageScorer MLP
│
├── viz-mas/                  ── VISUAL ANALYTICS WORKSPACE
│   ├── README.md               Frontend layout, view contracts
│   ├── package.json            Vue 3 + Vite + d3 deps
│   ├── vite.config.js          Pinned port 5190 + /api proxy → backend 8001
│   ├── index.html
│   ├── src/                    Frontend (Vue 3)
│   │   ├── App.vue               Six-panel grid layout
│   │   ├── api/client.js         HTTP + WebSocket helpers
│   │   ├── canonical/            Honeycomb layout + render
│   │   ├── components/           V1–V6 view components
│   │   └── utils/eventbus.js     Cross-view event bus (mitt)
│   └── server/                 Backend (FastAPI)
│       ├── main.py               REST + WebSocket app
│       ├── data/events_loader.py DS0003 events + income lookup
│       ├── mas/                  6-round LLM negotiation
│       │   ├── agent.py            DashScope (Qwen) OpenAI-compat client
│       │   ├── llm_helpers.py      chat_json + render_prompt
│       │   ├── motif_matcher.py    SEAL m1–m4 matchers
│       │   ├── negotiator_rounds.py 6-round bilateral orchestrator
│       │   ├── profiles.py         Person profile cache
│       │   ├── prompts/            persona / query / answer / score templates
│       │   ├── state.py            In-memory acceptance log
│       │   └── ws_broker.py        Per-husband WebSocket fan-out
│       ├── tests/                Pytest unit tests
│       └── requirements.txt      Backend deps (FastAPI, OpenAI SDK, pandas)
│
├── tests/                    Pipeline unit tests (smoke, leakage invariants)
├── scripts/                  R exporters + diagnostic scripts
│   ├── export_ds0001_rda.R     ICPSR DS0001 → gzipped CSV
│   ├── export_ds0003_rda.R     DS0003 → CSV (events + income + banner)
│   ├── analyze_cohorts.py      Cohort-level diagnostics
│   ├── audit_early_cohorts.py  Pre-1855 sanity checks
│   └── compare_ablation.py     Ablated-vs-unablated metrics deltas
│
├── viz/                      Static cohort viewer (legacy; viz-mas reads
│                             cohort_<year>__<ablation>.json from viz/data/)
│
├── paper/                    ── PAPER DRAFT (markdown, EN + ZH)
│   ├── README.md               Section index + pre-submission TODOs
│   ├── 00_abstract.md … 11_conclusion.md
│   └── zh/                     Chinese mirror
│
├── paper-vis-short/          ── IEEE VIS SHORT-PAPER LaTeX SUBMISSION
│   ├── paper.tex               Compiled IEEE VIS short-paper draft
│   ├── template.tex            Pristine vgtc template (reference)
│   ├── template.bib            Placeholder bibliography
│   ├── vgtc.cls, *.bst         IEEE VGTC class + bibliography styles
│   ├── makefile                latexmk-driven build
│   └── figures/                Vector + raster figure assets
│
├── docs/
│   └── STRUCTURE.md            This file
│
├── data/                     [GITIGNORED] ICPSR raw + processed parquets
├── checkpoints/              [GITIGNORED] best_ablated.pt, best_unablated.pt
└── runs/                     [GITIGNORED] metrics.json + per_cohort.csv per eval
```

## Quick navigation

| Task | Where |
|---|---|
| Train HGT on the ablated graph | `src/train.py` (entry: `python -m src.main --stage train`) |
| Evaluate against held-out edges | `src/evaluate.py` (entry: `python -m src.main --stage eval`) |
| Run the visual analytics dashboard | `viz-mas/` — `npm run dev` (frontend) + `uvicorn server.main:app --port 8001` (backend) |
| Edit the paper sections | `paper/*.md` (English) or `paper/zh/*.md` (Chinese) |
| Compile the IEEE VIS short paper | `paper-vis-short/` — `latexmk -pdf paper.tex` |
| Inspect or change a hyperparameter | `src/config.py` (only authoritative source) |
| Add a new SEAL motif | `viz-mas/server/mas/motif_matcher.py` + `src/config.py` |
| Override a backend prompt | `viz-mas/server/mas/prompts/{persona,query,answer,score}.txt` |

## Naming conventions

| Style | Used for | Example |
|---|---|---|
| `snake_case.py` | Python modules | `events_loader.py`, `motif_matcher.py` |
| `PascalCase.vue` | Vue components | `AgentBattleView.vue`, `CandidateCard.vue` |
| `kebab-case` | Top-level directories | `viz-mas/`, `paper-vis-short/` |
| `lowercase` | Single-word directories | `src/`, `viz/`, `paper/`, `tests/`, `scripts/` |
| `NN_section.md` | Paper sections | `01_introduction.md`, `04_computational_backbone.md` |
| `YYYYMMDD_HHMMSS_<tag>` | Run artefact directories | `runs/20260427_191523_ablated/` |

## Two-server bus contract (frontend ↔ backend)

The visual workspace runs as two processes:

- **Backend**: FastAPI on `127.0.0.1:8001` (`viz-mas/server/main.py`).
- **Frontend**: Vite dev server on `127.0.0.1:5190` (`viz-mas/`) with `/api/*` proxied to the backend.

Six WebSocket frame types drive the V5 negotiation loop:

```
start → stage:profile → stage:filter → narrative → round_start → persona
      → query → answer → round_scores → round_paused (await advance)
      → final_ranking → committed → done
```

Bus events for cross-view coordination:

```
hex-select        V3 → V4, V5
person-selected   V4 → V5
match-accepted    V4/V5 → V1/V2/V3
match-restored    V2 → V1/V3
```

## Things that live OUTSIDE this repo

- ICPSR CMGPD-LN dataset (license-restricted; place under `data/raw/DS0001/…` and `data/raw/DS0003/…`). See `README.md` Step 2.
- DashScope API key for real Qwen calls in V5 (set `DASHSCOPE_API_KEY`; falls back to deterministic heuristics if unset).
