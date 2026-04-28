"""FastAPI backend for the viz-mas MAS+HGT demo.

Reads the same cohort_<year>__<ablation>.json artefacts the frontend
consumes statically. Adds three things the static path can't do:

  1. WebSocket /api/negotiate/{pair_id}/stream
     Streams agent-round events with realistic per-round latency so V5's
     arena UI fills in incrementally. The agents are deterministic
     functions of the pair's per-pair fields (score, score_gap,
     same_lineage, patri_path_count, era).

  2. GET /api/shap/{pair_id}
     A SHAP-style waterfall: decomposes the pair's logit into named
     contributions. The decomposition is approximate — a true HGT-aware
     attribution would run feature-ablation through the trained model;
     this version uses a heuristic that mirrors what the model is
     learning from those features. Documented inline so the next pass
     can swap in real ablation.

  3. POST /api/rules
     Lets V6 sliders mutate the macro feature weights. The new weights
     are mixed into the SHAP/agent computation immediately, so the
     waterfall re-renders when sliders move.

Run:
    cd viz-mas
    pip install -r server/requirements.txt
    uvicorn server.main:app --host 127.0.0.1 --port 8001 --reload

The frontend already proxies /api/* to 127.0.0.1:8001 via vite.config.js.
If the backend isn't running, viz-mas/src/api/client.js falls back to
loading static cohort JSONs from /data/.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

from fastapi import (
    BackgroundTasks, FastAPI, HTTPException, Query,
    WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Multi-Agent System (MAS) modules — per-person LLM negotiation,
# WebSocket fan-out, hint storage, accepted-match log.
from .mas import agent as mas_agent
from .mas.profiles import get_profile as mas_get_profile
# The single-shot negotiator is REMOVED with the V5 6-round refactor. The
# import is kept commented for one merge cycle so reviewers can see the
# replacement; delete after unit 5 lands.
# from .mas.negotiator import negotiate as mas_negotiate  # noqa: ERA001
from .mas.negotiator_rounds import mas_negotiate_rounds
from .mas.state import state as mas_state
from .mas.ws_broker import broker as mas_broker

# DS0003 life-event + income loader (V5 narrative grounding for persona agents).
# Imported at module top so tests can monkey-patch
# `server.main.load_events` / `load_income` / `get_birth_year` directly.
from .data.events_loader import (
    get_birth_year, load_events, load_income,
)

ROOT = Path(__file__).resolve().parents[1]
# Single canonical data source: D:/projects/VIS_2026/NEW/viz/data/. Both
# the frontend (via vite middleware) and the backend read from this
# directory; no duplicates under viz-mas/public/data anymore.
CANONICAL_DATA_DIR = ROOT.parent / "viz" / "data"

app = FastAPI(title="cmgpd-mas-backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5190", "http://127.0.0.1:5190"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cohort cache ──────────────────────────────────────────────────────
_cohort_cache: dict[tuple[int, str], dict] = {}


def _cohort_path(year: int, ablation: str) -> Path:
    suffix = "__unablated" if ablation == "unablated" else ""
    name = f"cohort_{year}{suffix}.json"
    p = CANONICAL_DATA_DIR / name
    if p.exists():
        return p
    raise HTTPException(404, f"cohort {year} ({ablation}) not found at {CANONICAL_DATA_DIR}")


def load_cohort(year: int, ablation: str = "ablated") -> dict:
    key = (int(year), ablation)
    if key in _cohort_cache:
        return _cohort_cache[key]
    with _cohort_path(year, ablation).open("r", encoding="utf-8") as fh:
        c = json.load(fh)
    _cohort_cache[key] = c
    return c


# ── Live state ────────────────────────────────────────────────────────
class RuleWeights(BaseModel):
    paternal_lineage: float = 1.0
    sibling_overlap: float = 1.0
    household_share: float = 1.0
    banner_match: float = 0.5
    macro_era: float = 0.8


class MotifFlags(BaseModel):
    m1_father_brother: bool = True
    m2_uncle_in_law: bool = True
    m3_same_household: bool = False
    m4_banner_endog: bool = True


_macro = RuleWeights()
_motifs = MotifFlags()

ALL_YEARS = [1882, 1885, 1888, 1903, 1906, 1909]


# ── Heuristic decomposition (stand-in for true HGT-ablation SHAP) ─────
def _shap_components(pair: dict) -> list[dict[str, Any]]:
    """Decompose the pair's logit into named contributions whose sum
    equals the (sigmoid-inverse) score, with the macro slider weights
    folded in. Returns ordered components for waterfall rendering."""
    s = float(pair.get("score", 0.0))
    gap = float(pair.get("score_gap", 0.0))
    patri = float(pair.get("patri_path_count", 0.0))
    same_lin = bool(pair.get("same_lineage", False))
    era = pair.get("era") or "regular"

    # Heuristic component proportions. These mirror what the model is
    # learning from each feature and are mixed by the live RuleWeights.
    base = -1.0  # bias, kept fixed
    paternal_raw = 0.6 * patri  # +0.6 logit per visible paternal-2-hop path
    sibling_raw = 0.35 * (1 if patri >= 2 else 0)
    household_raw = 0.45 * (1 if patri >= 3 else 0)
    banner_raw = 0.3
    macro_raw = {"regular": 0.4, "catchup": 0.0, "late": 0.2}.get(era, 0.0)
    endog_penalty = -2.0 if same_lin else 0.0

    parts = [
        {"label": "bias",                "value": base},
        {"label": "paternal lineage",    "value": _macro.paternal_lineage * paternal_raw},
        {"label": "sibling overlap",     "value": _macro.sibling_overlap  * sibling_raw},
        {"label": "household share",     "value": _macro.household_share  * household_raw},
        {"label": "banner match",        "value": _macro.banner_match     * banner_raw},
        {"label": "macro era",           "value": _macro.macro_era        * macro_raw},
        {"label": "endogamy penalty",    "value": endog_penalty},
    ]

    # Re-scale so the components sum to the actual logit. Preserves the
    # SIGN of each contribution but rescales magnitude so the waterfall
    # bottoms out at the model's actual prediction.
    s_predicted = sum(p["value"] for p in parts)
    if s_predicted != 0:
        ratio = s / s_predicted
        for p in parts:
            p["scaled"] = p["value"] * ratio
    else:
        for p in parts:
            p["scaled"] = p["value"]

    parts.append({"label": "FINAL (logit)", "value": s, "scaled": s, "is_total": True})
    parts.append({"label": "score gap",     "value": gap, "scaled": gap, "is_total": True})
    return parts


# ── HTTP endpoints ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"ok": True, "macro": _macro.model_dump(), "motifs": _motifs.model_dump()}


@app.get("/api/health")
async def api_health():
    return await health()


@app.get("/api/metrics")
async def api_metrics(ablation: str = "ablated"):
    out = []
    for y in ALL_YEARS:
        try:
            c = load_cohort(y, ablation)
        except HTTPException:
            continue
        positives = [p for p in c["pairs"] if p.get("label") == 1]
        n_pos = len(positives)
        correct = sum(1 for p in positives if p.get("hungarian_correct") is True)
        top1 = sum(1 for p in positives if p.get("rank_of_true_wife") == 1)
        top10 = sum(1 for p in positives
                    if isinstance(p.get("rank_of_true_wife"), int) and p["rank_of_true_wife"] <= 10)
        mrr = (sum(1.0 / p["rank_of_true_wife"]
                   for p in positives
                   if isinstance(p.get("rank_of_true_wife"), int) and p["rank_of_true_wife"] > 0)
               / n_pos) if n_pos else 0.0
        out.append({
            "year": y,
            "n_pairs": c.get("n_pairs"),
            "n_positives": n_pos,
            "hungarian_recall_at_1": (correct / n_pos) if n_pos else 0.0,
            "top1_recall": (top1 / n_pos) if n_pos else 0.0,
            "top10_recall": (top10 / n_pos) if n_pos else 0.0,
            "mrr": mrr,
            "completion": (correct / n_pos) if n_pos else 0.0,
        })
    return out


@app.get("/api/pair")
async def api_pair(year: int, id: int, ablation: str = "ablated"):
    c = load_cohort(year, ablation)
    if not (0 <= id < len(c["pairs"])):
        raise HTTPException(404, f"pair id {id} out of range")
    return c["pairs"][id]


@app.get("/api/narrative/{person_id}")
def api_narrative(person_id: str, year: int = Query(..., ge=1700, le=2000)):
    """Return a person's life-history timeline up to ``year``.

    Powers the V5 (Agent Arena) per-persona narrative panel: each Qwen
    agent (husband + each candidate wife) is grounded in the real DS0003
    event stream and yearly income trace bounded above by the cohort
    year. The window starts at the person's known birth year if DS0003
    knows it, else `year - 80` (an upper bound on plausible lifespan)
    so we still surface anything the loader can find.

    The actual year filtering is performed by the loader; this endpoint
    only normalises the person id and forwards `start`/`end` to it.
    Returns 404 when DS0003 has neither events nor income for this id.
    """
    birth = get_birth_year(person_id)
    start = birth if birth is not None else year - 80
    events = load_events(person_id, start, year)
    income = load_income(person_id, start, year)
    if not events and not income:
        raise HTTPException(status_code=404, detail="person not found")
    normalized_id = person_id if person_id.startswith("P") else f"P{person_id}"
    return {
        "person_id": normalized_id,
        "birth_year": birth,
        "events": events,
        "income": income,
    }


@app.get("/api/profile/{person_id}")
def api_profile(person_id: str):
    """Return the cleaned-parquet attributes for one person.

    Backs V4's click-popup (sex / birth / banner / community / household)
    and seeds V5's husband header before the negotiation streams. Falls
    back to a {sex:'?', birth_year:None, ...} stub when the parquet is
    missing or the id is unknown — matching the frontend's offline stub
    so the UI behaves identically with or without the backend.
    """
    return mas_get_profile(person_id)


@app.get("/api/seal/{husband_id}/{wife_id}")
def api_seal_subgraph(husband_id: str, wife_id: str):
    """Return the SEAL motif subgraph for a (husband, wife) pair.

    Currently a STUB — returns one of four canonical motif exemplars
    deterministically per pair. Schema v1; see `server/data/seal_loader.py`
    for the strict output contract and the migration notes for the real
    DRNL+motif-classification pipeline.

    Backs V6's per-edge sub-window: the user clicks any r_hw edge
    (potential dashed or confirmed solid) and gets a focused mini-graph
    showing the structural pattern that justifies (or would justify) the
    match.
    """
    from .data.seal_loader import get_seal_subgraph
    return get_seal_subgraph(husband_id, wife_id)


@app.get("/api/shap/{pair_id}")
async def api_shap(pair_id: int, year: int, ablation: str = "ablated"):
    c = load_cohort(year, ablation)
    if not (0 <= pair_id < len(c["pairs"])):
        raise HTTPException(404, f"pair id {pair_id} out of range")
    pair = c["pairs"][pair_id]
    return {
        "pair_id": pair_id,
        "husband_id": pair["husband_id"],
        "wife_id": pair["wife_id"],
        "components": _shap_components(pair),
    }


@app.get("/api/rules")
async def api_rules_get():
    return {"macro": _macro.model_dump(), "motifs": _motifs.model_dump()}


@app.post("/api/rules")
async def api_rules_post(body: dict):
    if "macro" in body:
        for k, v in body["macro"].items():
            if hasattr(_macro, k):
                setattr(_macro, k, float(v))
    if "motifs" in body:
        for k, v in body["motifs"].items():
            if hasattr(_motifs, k):
                setattr(_motifs, k, bool(v))
    return {"macro": _macro.model_dump(), "motifs": _motifs.model_dump()}


# ──────────────────────────────────────────────────────────────────────
# MAS — per-husband 6-round bilateral negotiation
# ──────────────────────────────────────────────────────────────────────
#
# Each husband gets ONE negotiation session at topic
# `negotiate:{husband_id}`. The orchestrator (mas_negotiate_rounds) runs
# six rounds — persona load, opening pitches, bilateral scoring, ranking,
# arbitration, commit — and pauses between them on a per-husband
# asyncio.Event. The user "advances" rounds via POST /advance and can
# inject prompts via POST /hint, which land in a per-husband asyncio.Queue
# the orchestrator drains between rounds.

class _NegotiateStartBody(BaseModel):
    year: int
    ablation: str = "ablated"
    auto_commit: bool = False


async def _run_orchestrator(
    husband_id: str, year: int, ablation: str, auto_commit: bool,
) -> None:
    """Background entrypoint: marks the session active for the duration of
    the orchestrator run so /advance can answer 404 vs 200 correctly, and
    forwards any orchestrator exception as an error frame on the WS topic.
    """
    topic = f"negotiate:{husband_id}"

    async def _publish(event: dict) -> None:
        await mas_broker.publish(topic, event)

    try:
        await mas_negotiate_rounds(
            husband_id, year, ablation,
            publish=_publish,
            advance_event=mas_state.get_advance_event(husband_id),
            hint_queue=mas_state.get_hint_queue(husband_id),
            auto_commit=auto_commit,
        )
    except Exception as e:   # noqa: BLE001
        log.exception("orchestrator failed for %s: %s", husband_id, e)
        await mas_broker.publish(topic, {"type": "error", "message": str(e)})
    finally:
        mas_state.mark_session_inactive(husband_id)


@app.post("/api/negotiate/{husband_id}")
async def api_negotiate_start(husband_id: str, body: _NegotiateStartBody):
    """Kick off a 6-round negotiation as a fire-and-forget asyncio task;
    the live event stream is at WS /api/negotiate/{husband_id}/stream.
    Pause/resume between rounds via POST /api/negotiate/{husband_id}/advance,
    and inject directives via POST /api/negotiate/{husband_id}/hint.

    NOTE: we deliberately use ``asyncio.create_task`` rather than
    FastAPI's ``BackgroundTasks`` because the orchestrator parks on
    per-round advance Events for an unbounded duration; ``BackgroundTasks``
    runs after the response but BLOCKS the request lifecycle, which would
    stall the sync ``TestClient`` (and any client expecting prompt 200).
    """
    topic = f"negotiate:{husband_id}"
    mas_broker.reset(topic)               # fresh replay buffer per run
    mas_state.reset_session(husband_id)   # clear advance event + hint queue
    # Mark active synchronously so a /advance hitting microseconds after
    # this 200 doesn't see "no active session".
    mas_state.mark_session_active(husband_id)
    asyncio.create_task(
        _run_orchestrator(husband_id, body.year, body.ablation, body.auto_commit),
    )
    return {
        "status": "started",
        "husband_id": husband_id,
        "year": body.year,
        "ablation": body.ablation,
        "topic": topic,
    }


@app.post("/api/negotiate/{husband_id}/advance")
async def api_negotiate_advance(husband_id: str):
    """Signal the orchestrator's per-husband Event so it can leave the
    current round_paused frame. 404 if no orchestrator is currently
    running for this husband."""
    if not mas_state.is_session_active(husband_id):
        raise HTTPException(404, f"no active negotiation for {husband_id}")
    mas_state.get_advance_event(husband_id).set()
    return {"status": "ok"}


@app.websocket("/api/negotiate/{husband_id}/stream")
async def api_negotiate_stream(ws: WebSocket, husband_id: str):
    await ws.accept()
    topic = f"negotiate:{husband_id}"
    q = await mas_broker.subscribe(topic)
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
            if event.get("type") == "done":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:   # noqa: BLE001
        log.warning("WS stream error for %s: %s", topic, e)
    finally:
        await mas_broker.unsubscribe(topic, q)
        try:
            await ws.close()
        except Exception:
            pass


class _HintBody(BaseModel):
    text: str
    # 'all' | 'target' | 'candidates' | a candidate id like 'c-12345'.
    role: str = "all"
    # Optional 1-indexed round number this hint targets. The orchestrator
    # uses it to scope when the hint is replayed to agents.
    round: int | None = None


@app.post("/api/negotiate/{husband_id}/hint")
async def api_negotiate_hint(husband_id: str, body: _HintBody):
    """Push the hint into the orchestrator's per-husband Queue. The
    orchestrator drains the queue between rounds and emits its own
    hint_ack frame, so we no longer publish one here.

    The legacy in-memory hint list is still updated so other code paths
    (profiles, list/count endpoints) keep working during the transition.
    """
    payload = {"text": body.text, "role": body.role, "round": body.round}
    await mas_state.get_hint_queue(husband_id).put(payload)
    mas_state.add_hint(husband_id, body.text, body.role)
    return {"status": "ok"}


@app.get("/api/negotiate/{husband_id}/hints")
async def api_negotiate_hints(husband_id: str):
    return mas_state.list_hints(husband_id)


class _OverrideBody(BaseModel):
    wife_id: str
    score: float | None = None
    note: str | None = None
    year: int | None = None
    ablation: str | None = None


@app.post("/api/negotiate/{husband_id}/override")
async def api_negotiate_override(husband_id: str, body: _OverrideBody):
    rec = mas_state.commit_match(
        husband_id=husband_id, wife_id=body.wife_id,
        score=body.score, source="override", note=body.note or "",
        year=body.year, ablation=body.ablation,
    )
    await mas_broker.publish(
        f"negotiate:{husband_id}",
        {"type": "committed", "match": rec},
    )
    return {"status": "ok", "match": rec}


@app.get("/api/negotiate/accepted")
async def api_accepted_all():
    return mas_state.all_accepted()


@app.post("/api/negotiate/{husband_id}/restore")
async def api_negotiate_restore(husband_id: str):
    """Roll back a prior accept for this husband. Removes the record from
    the per-husband latest map and the append-only log, so V1's curve and
    V2's table recompute as if the accept never happened. The frontend
    should also re-add the (h, w) edge to V3's scatter and V4's bipartite
    on receipt of the `match-restored` bus event.
    """
    rec = mas_state.uncommit_match(husband_id)
    if rec is None:
        raise HTTPException(404, f"no accepted match for {husband_id}")
    return {"status": "ok", "removed": rec}


# ── V1 learning curve: MAS recall@1 trajectory vs HGT static baseline ─
@app.get("/api/eval/progress")
async def api_eval_progress(year: int, ablation: str = "ablated"):
    """Per-acceptance running quality of the MAS pipeline against the
    cohort's ground-truth marriage edges, plus the HGT-only baseline as
    a horizontal reference line.

    For each husband we accept (via auto-commit or user override) we
    look up the cohort's positive (label=1) wife. If they match the
    accepted wife, the acceptance is "correct"; otherwise wrong. The
    running recall@1 = (correct so far) / (positives accepted so far).

    Husbands without a known positive in the cohort (e.g. user accepts
    a hard-negative) are excluded from the recall denominator but still
    counted in n_accepted (the x-axis).
    """
    try:
        cohort = load_cohort(year, ablation)
    except HTTPException as e:
        raise e

    # Build husband_id → ground-truth wife_id from the cohort positives.
    gt_wife: dict[str, str] = {}
    for p in cohort["pairs"]:
        if p.get("label") == 1:
            gt_wife.setdefault(p["husband_id"], p["wife_id"])

    # HGT static baseline: precomputed Hungarian recall@1 across all
    # positives in this cohort. Same number V1 used to show in its row.
    positives = [p for p in cohort["pairs"] if p.get("label") == 1]
    n_pos = len(positives)
    correct = sum(1 for p in positives if p.get("hungarian_correct") is True)
    hgt_recall_at_1 = (correct / n_pos) if n_pos else 0.0

    # MAS trajectory.
    log = mas_state.accept_log(year=year, ablation=ablation)
    trajectory = []
    n_accept = 0
    n_eligible = 0   # accepts with a known ground-truth wife in this cohort
    n_correct = 0
    for rec in log:
        n_accept += 1
        true_w = gt_wife.get(rec["husband_id"])
        if true_w is not None:
            n_eligible += 1
            if true_w == rec["wife_id"]:
                n_correct += 1
        trajectory.append({
            "ts": rec["ts"],
            "n_accepted": n_accept,
            "n_eligible": n_eligible,
            "n_correct": n_correct,
            "mas_recall_at_1": (n_correct / n_eligible) if n_eligible else None,
            "husband_id": rec["husband_id"],
            "wife_id": rec["wife_id"],
            "source": rec["source"],
        })

    return {
        "year": year,
        "ablation": ablation,
        "hgt_baseline": {
            "recall_at_1": hgt_recall_at_1,
            "n_positives": n_pos,
        },
        "trajectory": trajectory,
        "n_accepted_total": n_accept,
        "n_eligible_total": n_eligible,
        "n_correct_total": n_correct,
        "mas_recall_at_1_now": (n_correct / n_eligible) if n_eligible else None,
    }


@app.post("/api/eval/reset")
async def api_eval_reset():
    """Clear the accept log + per-husband latest map. Lets you start a
    fresh learning-curve session from V1 without restarting the server."""
    mas_state.reset_log()
    return {"status": "ok"}


# ── LLM config (set DASHSCOPE key + model name from the title bar) ────
class _LLMConfigBody(BaseModel):
    api_key: str | None = None
    model: str | None = None


@app.get("/api/llm_config")
async def api_llm_config_get():
    return mas_agent.get_config()


@app.post("/api/llm_config")
async def api_llm_config_post(body: _LLMConfigBody):
    return mas_agent.set_config(api_key=body.api_key, model=body.model)


import logging   # noqa: E402  (keep at bottom; only used by the WS handler)
log = logging.getLogger("server.main")
