# cmgpd-hgt + visual analytics workspace

Heterogeneous Graph Transformer (HGT) for marriage-edge prediction in the
**CMGPD-LN** historical genealogy panel (ICPSR 27063), bundled with a
six-panel visual analytics workspace that lets a historian or demographer
review, override, and audit the predicted marriages through a multi-agent
LLM negotiation interface.

This repository ships **code only**. The Qing-dynasty Liaoning panel is
ICPSR-licensed and cannot be redistributed; you must acquire it yourself
(see [Step 2](#step-2-acquire-the-cmgpd-ln-dataset-from-icpsr) below).

> For per-folder responsibilities and the full file tree, see [`docs/STRUCTURE.md`](docs/STRUCTURE.md). For Claude-Code-oriented architecture notes (graph schema, ablation invariants, training loop), see [`CLAUDE.md`](CLAUDE.md).

---

## What gets built

| Component | Path | Purpose |
|---|---|---|
| **HGT pipeline** | `src/` | Trains the marriage-prediction model on ablated graph; emits cohort JSONs that the dashboard reads. |
| **Backend (FastAPI)** | `viz-mas/server/` | Serves cohort data, hosts the 6-round bilateral LLM-agent negotiation, accepts/restores match commits. |
| **Frontend (Vue 3 + Vite)** | `viz-mas/src/` | Six linked views (V1–V6) for cohort overview, processed pairs, embedding space, bipartite detail, agent arena, and rule injector. |

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Python** | 3.10 – 3.12 | Pipeline + backend |
| **R** | ≥ 4.3 | One-time `.rda → .csv.gz` conversion (the Liaoning panel ships as R binaries pyreadr can't stream at 1.5 M rows) |
| **Node.js** | ≥ 18 | Vite dev server |
| **Git** | any modern | Clone the repo |
| **ICPSR account** | free | Required to download the licensed dataset |
| **DashScope API key** | optional | Real Qwen calls in V5; without it the orchestrator falls back to deterministic stubs |

**Disk:** ≈ 700 MB once the cohort caches and trained model are built (the raw `.rda` files are ≈ 70 MB; the rest is generated).

---

## Files NOT in git (you must acquire / generate)

The repo's `.gitignore` excludes the entire `data/`, `runs/`, and
`checkpoints/` trees because they're either ICPSR-licensed or fully
reproducible from `data/raw/`. Populate these locally:

| Path | Origin | Acquired via |
|---|---|---|
| `data/raw/DS0001/27063-0001-Data.rda` | ICPSR study #27063 | manual download (Step 2) |
| `data/raw/DS0003/27063-0003-Data.rda` | ICPSR study #27063 | manual download (Step 2) |
| `data/raw/DS0003/event_value_labels.json` | already in git (small JSON) | bundled |
| `data/raw/DS0009/*.rda`, `DS0011/*.rda` | ICPSR study #27063 | manual download (optional — macro signal) |
| `data/processed/hgt_pipeline/*.parquet` | generated | `python -m src.main --stage data` |
| `data/processed/ds0003/*.parquet` | generated | first call to `events_loader` |
| `checkpoints/best.pt` | generated | `python -m src.main --stage train` |
| `runs/<timestamp>/metrics.json` | generated | `python -m src.main --stage eval` |
| `viz/data/cohort_<year>__<ablation>.json` | generated | `python -m src.main --stage eval` |
| `.env` (Qwen key) | manual | see [Step 4](#step-4--environment-variables) |

---

## Setup

### Step 1 — Clone

```bash
git clone https://github.com/Autopivot/cmgpd-hgt.git
cd cmgpd-hgt
```

All paths below are relative to the repo root. The HGT pipeline lives in `src/`, the visual analytics workspace in `viz-mas/`, the paper drafts in `paper/` (markdown sections, EN + ZH) and `paper-vis-short/` (LaTeX submission).

### Step 2 — Acquire the CMGPD-LN dataset from ICPSR

1. Create a free account at <https://www.icpsr.umich.edu/web/pages/index.html>.
2. Open study **#27063 — China Multi-Generational Panel Dataset, Liaoning, 1749–1909**:
   <https://www.icpsr.umich.edu/web/ICPSR/studies/27063>
3. Accept the terms of use and download the **R format** bundle. The archive contains 11 datasets (DS0001 – DS0011); you need at minimum:

   | File | Size | Used by |
   |---|---|---|
   | `27063-0001-Data.rda` (DS0001 — Basic File) | ≈ 39 MB | Person profiles, kinship graph |
   | `27063-0003-Data.rda` (DS0003 — Analytic File) | ≈ 25 MB | Life-event narratives, banner affiliation |
   | `27063-0009-Data.rda` (DS0009 — Grain prices) | ≈ 1 MB | Macro covariates *(optional)* |
   | `27063-0011-Data.rda` (DS0011 — Disasters) | ≈ 1 MB | Macro covariates *(optional)* |

4. Place them under `data/raw/`:

   ```
   data/raw/
   ├── DS0001/27063-0001-Data.rda
   ├── DS0003/27063-0003-Data.rda
   ├── DS0009/27063-0009-Data.rda          # optional
   └── DS0011/27063-0011-Data.rda          # optional
   ```

   The exact `DSxxxx/` folder layout matters — `src/config.py` and
   `server/data/events_loader.py` look for these paths verbatim.

### Step 3 — Install dependencies

#### Python

```bash
cd 
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

# Pipeline + ML deps
pip install -r requirements.txt

# Backend deps (FastAPI + OpenAI SDK for DashScope)
pip install -r viz-mas/server/requirements.txt
```

#### R

Install [R](https://cran.r-project.org/) ≥ 4.3 and ensure `Rscript` is on
your `PATH`. No R packages beyond base are needed — the export scripts use
only `load`, `write.csv`, `gzfile`. Verify:

```bash
Rscript --version          # should print "Rscript (R) version 4.x.y"
```

If `Rscript` isn't on `PATH`, set the explicit path:

```bash
# Windows example
export R_EXECUTABLE="C:/Program Files/R/R-4.5.0/bin/x64/Rscript.exe"
```

#### Frontend

```bash
cd viz-mas/
npm install
```

### Step 4 — Environment variables

Create `.env` (or set in your shell) for the optional Qwen key:

```ini
# Required for real LLM agents in V5; without this the orchestrator falls
# back to deterministic heuristic personas/queries/answers.
DASHSCOPE_API_KEY=sk-...

# Optional override (default is qwen-plus-2025-04-28)
QWEN_MODEL=qwen-plus-2025-04-28

# Optional override if Rscript isn't on PATH
R_EXECUTABLE=/usr/bin/Rscript
```

You can also set the API key at runtime via the dashboard's V6 panel, or
`POST /api/llm_config` with `{api_key, model}`.

### Step 5 — Build the data caches and train the model

From ``:

```bash
# All four pipeline stages in order. First run takes 10–20 min depending
# on hardware; subsequent runs reuse caches.
python -m src.main --stage all

# Smoke run (1849–1854 cohorts only) for a fast check:
python -m src.main --stage all --smoke
```

What each stage does:

| Stage | Output |
|---|---|
| `data` | `data/processed/hgt_pipeline/ds0001_clean.parquet` + `graph.pt` |
| `features` | Person/household/community/banner features attached to graph |
| `train` | `checkpoints/best.pt` (the encoder + scorer) |
| `eval` | `runs/<ts>/metrics.json` + `viz/data/cohort_<year>__<ablation>.json` |

Re-run a single stage with `--stage <name>`; force a rebuild with `--force`.

> **DS0003 narrative cache** is built lazily on first backend call (not by
> the pipeline). The first negotiation request runs the R export (~4 s) and
> joins it against DS0001 by `RECORD_NUMBER` (~10 s), persisting
> `data/processed/ds0003/ds0003_joined.parquet` for fast subsequent loads.

### Step 6 — Start the backend

```bash
cd viz-mas/
python -m uvicorn server.main:app --port 8001 --reload
```

The first request that hits a profile or narrative endpoint will take
20 – 40 s while the parquets warm into the in-process cache. After that,
all calls are sub-millisecond.

Verify:

```bash
curl http://127.0.0.1:8001/api/health
# → {"ok":true, "macro":{...}, "motifs":{...}}

curl http://127.0.0.1:8001/api/profile/P259640
# → {"id":"P259640","sex":"M","birth_year":1860,
#    "banner_label":"Solid White","region_label":"South Liaoning",...}
```

### Step 7 — Start the frontend

In a second terminal:

```bash
cd viz-mas/
npm run dev
```

Vite serves the dashboard on `http://localhost:5190` (port pinned in
`vite.config.js`). The Vite proxy forwards `/api/*` to the backend on
`8001`, so both servers must be running.

Open the URL — you should see six panels (V1 – V6) populated with the 1882
cohort by default. If everything is wired correctly:

- **V1** plots the MAS acceptance curve vs the static HGT recall@1 baseline.
- **V2** lists accepted matches (empty until you accept any).
- **V3** renders the honeycomb embedding; clicking a hex selects pairs.
- **V4** shows the bipartite husband ↔ candidates view for the V3 selection.
- **V5** boots the agent arena; click a husband node in V4 to load it, then `▶ arena` to start a 6-round negotiation.
- **V6** exposes macro-feature weights and motif toggles.

---

## Verifying the visual workflow

A 60-second smoke test:

1. In V3, click any populated hex.
2. In V4, click a husband node (left column). Profile popup should show real `sex / birth / banner / region`.
3. Click `▶ arena` in V5. Round 1 emits 7 personas (husband + 6 candidates) within ~5 s (real Qwen) or instantly (stub).
4. Click `Approve & Advance →`. Round 2 emits queries + answers + scores.
5. Type `@everyone be skeptical` in the hint console. Hit send.
6. Advance through round 6. Click `Accept this match`.
7. Watch V1's curve update, V2 prepend a new row tagged `HGT,MAS` (or just `MAS` / `HGT` depending on convergence), V3 mask the dot, V4 drop the edge.
8. Click `↶ restore` on the V2 row. Everything rolls back cleanly.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| All popup fields show `?` | Backend not running | `netstat -ano \| findstr :8001` — start uvicorn if missing |
| `Rscript export failed: returned non-zero exit status` | R not installed or not on PATH | Install R ≥ 4.3 or set `R_EXECUTABLE` |
| `Port 5190 is already in use` | Stale Vite process | Kill the process holding port 5190 |
| `Port 8001 is already in use` | Stale uvicorn | `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8001 -State Listen).OwningProcess -Force` |
| First negotiation hangs > 30 s | Parquet cache cold-load on first request | Wait — subsequent calls are instant |
| V5 personas all look identical | `DASHSCOPE_API_KEY` unset → stub mode | Add the key, restart backend |
| `cohort_<year>__<ablation>.json not found` | Eval stage hasn't run yet | `python -m src.main --stage eval` |
| `events_loader returns empty` | DS0003 missing or join cache stale | Delete `data/processed/ds0003/` and let it rebuild |

---

## Project layout (high level)

```
VIS_2026/
├── README.md                               ← this file
├── 
│   ├── README.md                           HGT pipeline deep dive
│   ├── requirements.txt                    Pipeline Python deps
│   ├── data/
│   │   ├── raw/                            (gitignored) ICPSR .rda files
│   │   └── processed/                      (gitignored) generated parquets
│   ├── src/                                HGT pipeline (data → features → train → eval)
│   │   ├── config.py                       paths + hyperparameters
│   │   ├── stage0_data.py … stage3_temporal.py
│   │   ├── train.py / evaluate.py
│   │   └── model/hgt.py
│   ├── scripts/                            R exporters + diagnostics
│   ├── viz/data/                           generated cohort_<year>__<ablation>.json
│   ├── viz-mas/
│   │   ├── package.json                    Frontend deps
│   │   ├── vite.config.js                  Pinned port 5190 + /api proxy
│   │   ├── src/
│   │   │   ├── App.vue                     6-panel layout
│   │   │   ├── api/client.js               HTTP + WebSocket helpers
│   │   │   ├── canonical/                  honeycomb layout + render
│   │   │   ├── components/                 V1–V6 Vue components
│   │   │   └── utils/eventbus.js           cross-view bus
│   │   └── server/
│   │       ├── requirements.txt
│   │       ├── main.py                     FastAPI app + WS broker
│   │       ├── data/events_loader.py       DS0003 events + income lookup
│   │       └── mas/
│   │           ├── agent.py                DashScope OpenAI-compatible client
│   │           ├── llm_helpers.py          chat_json + render_prompt
│   │           ├── motif_matcher.py        SEAL m1–m4 matchers
│   │           ├── negotiator_rounds.py    6-round bilateral orchestrator
│   │           ├── profiles.py             person profile cache
│   │           └── prompts/                persona / query / answer / score
│   ├── checkpoints/                        (gitignored) trained model
│   └── runs/                               (gitignored) eval artefacts
├── tests/                                  Pipeline smoke + leakage-invariant tests
├── scripts/                                R exporters + diagnostic CLIs
├── viz/                                    Static cohort viewer (legacy; viz-mas reads cohort_*.json from viz/data/)
├── paper/                                  Markdown paper sections (EN + zh/)
├── paper-vis-short/                        IEEE VIS short-paper LaTeX submission
├── docs/STRUCTURE.md                       Per-folder layout reference
└── README.md                               This file
```

For the full annotated tree see [`docs/STRUCTURE.md`](docs/STRUCTURE.md).

---

## Further reading

- **Per-folder responsibilities + naming conventions** —
  [`docs/STRUCTURE.md`](docs/STRUCTURE.md)
- **HGT pipeline mechanics** — graph schema, ablation invariants, training loop:
  [`CLAUDE.md`](CLAUDE.md)
- **Frontend layout & view contracts** — V1–V6 design notes:
  [`viz-mas/README.md`](viz-mas/README.md)
- **CMGPD-LN itself** — ICPSR codebooks under `data/raw/DS000X/27063-000X-Codebook.md`

## License

Code: see `LICENSE` (if present in your fork) — typically MIT for the
research code. Data: ICPSR Terms of Use govern the CMGPD-LN panel; no
redistribution.
