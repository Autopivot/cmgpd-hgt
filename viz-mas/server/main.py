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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "public" / "data"           # primary
FALLBACK_DATA_DIR = ROOT.parent / "viz" / "data"   # secondary if public/data is empty

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
    p = DATA_DIR / name
    if p.exists():
        return p
    p2 = FALLBACK_DATA_DIR / name
    if p2.exists():
        return p2
    raise HTTPException(404, f"cohort {year} ({ablation}) not found")


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


# ── WebSocket: streamed agent negotiation ─────────────────────────────
@app.websocket("/api/negotiate/{pair_id}/stream")
async def negotiate_stream(ws: WebSocket, pair_id: int, year: int = 1882, ablation: str = "ablated"):
    await ws.accept()
    try:
        c = load_cohort(year, ablation)
        if not (0 <= pair_id < len(c["pairs"])):
            await ws.send_json({"event": "error", "message": f"pair id {pair_id} out of range"})
            await ws.close()
            return
        pair = c["pairs"][pair_id]
        s = float(pair.get("score", 0.0))
        gap = float(pair.get("score_gap", 0.0))
        patri = float(pair.get("patri_path_count", 0.0))
        same_lin = bool(pair.get("same_lineage", False))
        era = pair.get("era") or "regular"
        hungarian = pair.get("hungarian_correct")

        # Open frame
        await ws.send_json({
            "event": "round-start",
            "pair_id": pair_id,
            "husband_id": pair["husband_id"],
            "wife_id": pair["wife_id"],
        })
        await asyncio.sleep(0.20)

        # Stream agents one at a time, applying the live macro weights.
        agents = [
            ("paternal-prior",
             _macro.paternal_lineage * (0.6 * patri) - 1.0,
             "patrilineal scaffold; +0.6 logit per visible 2-hop path"),
            ("sibling-overlap",
             _macro.sibling_overlap * (0.35 if patri >= 2 else 0.0),
             "shared siblings via father-of-husband"),
            ("household-share",
             _macro.household_share * (0.45 if patri >= 3 else 0.0),
             "pre-marriage co-residence"),
            ("banner-match",
             _macro.banner_match * 0.3,
             "same banner endogamy bonus"),
            ("macro-temporal",
             _macro.macro_era * {"regular": 0.4, "catchup": 0.0, "late": 0.2}.get(era, 0.0),
             f"cohort era = {era}"),
            ("endogamy-veto",
             -2.0 if same_lin else 0.0,
             "same-lineage = strict veto" if same_lin else "cross-lineage ok"),
        ]
        for name, score, note in agents:
            await ws.send_json({
                "event": "agent",
                "agent": name,
                "score": float(score),
                "note": note,
            })
            await asyncio.sleep(0.30)

        # Final aggregate frame
        accept = (hungarian is True) if hungarian is not None else (s > 0)
        await ws.send_json({
            "event": "final",
            "final_score": s,
            "score_gap": gap,
            "accept": bool(accept),
            "hungarian_correct": hungarian,
        })

    except WebSocketDisconnect:
        return
    finally:
        try:
            await ws.close()
        except Exception:
            pass
