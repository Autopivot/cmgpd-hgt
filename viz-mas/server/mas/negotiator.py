"""Multi-agent negotiation for one husband.

Adapts the reference negotiator (jiapu-hgt-final) to our cohort-driven
data model. For a given husband (identified by his "Pxxx" id and a
cohort year):

  1. Profile stage — load his profile from the cleaned CMGPD parquet.
  2. Filter stage — pick the top-K candidate wives from the cohort
     JSON, ranked by HGT pre-score. Each candidate is itself a person
     with a profile.
  3. Target stage — call the LLM agent ONCE with the husband's
     perspective; it scores all K candidates 1-10. Tokens stream out
     over the WS topic in real time.
  4. Bilateral stage — for each candidate scoring ≥ THRESHOLD, call
     the LLM agent with the candidate's perspective so SHE scores HIM
     back. Concurrent via asyncio.gather. Each candidate is its own
     LLM call → "every person gets to communicate".
  5. Final ranking — combined score = ((target_score + candidate_score)
     / 2) * γ_pre, where γ_pre = sigmoid(HGT_logit). Sort, emit.

Each event is published to the broker on topic `negotiate:{husband_id}`
so the V5 frontend can render the rounds incrementally.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path
from typing import Any

from .agent import get_agent
from .profiles import get_profile
from .state import state
from .ws_broker import broker

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DATA = ROOT.parent / "viz" / "data"

# Negotiation knobs.
TOP_K_CANDIDATES = 8           # filter to top-K HGT-scored wives per husband
BILATERAL_THRESHOLD = 5        # only call candidate-side LLM if target score >= this
COMMIT_THRESHOLD = 6.5         # auto-accept when final score >= this on a 1-10 scale


def _cohort_path(year: int, ablation: str) -> Path:
    suffix = "__unablated" if ablation == "unablated" else ""
    return CANONICAL_DATA / f"cohort_{year}{suffix}.json"


def _load_cohort(year: int, ablation: str) -> dict:
    p = _cohort_path(year, ablation)
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _macro_rules() -> str:
    return (
        "  - Banner endogamy is the strong norm (≈70% of marriages within-banner).\n"
        "  - Husband is typically 0–5 years older than wife.\n"
        "  - Same-village marriages are common but not required.\n"
        "  - Hypergamy (lower→higher household status) is the typical direction.\n"
        "  - Sibling-precedent: families repeat partnerships across generations."
    )


def _micro_rules() -> str:
    return (
        "  - Father → brother → wife: husband's brother previously married into the\n"
        "    candidate's lineage (strong prior).\n"
        "  - Uncle-in-law triangle: husband's father has a prior tie to candidate's\n"
        "    paternal household.\n"
        "  - Pre-marriage co-residence: husband and candidate observed in the\n"
        "    same household before marriage year (rare but very strong)."
    )


async def _publish_stage(topic: str, stage: str, **kwargs) -> None:
    await broker.publish(topic, {"type": "stage", "stage": stage, **kwargs})


async def negotiate(husband_id: str, year: int, ablation: str,
                    *, auto_commit: bool = False) -> dict:
    """Run the full pipeline for one husband. Returns the final result dict
    and publishes WS events along the way.
    """
    topic = f"negotiate:{husband_id}"
    agent = get_agent()

    await broker.publish(topic, {
        "type": "start",
        "husband_id": husband_id, "year": year, "ablation": ablation,
    })

    # ── Stage 1: profile ───────────────────────────────────────────────
    husband = get_profile(husband_id)
    husband["sex"] = "M"   # by construction in this dataset
    await _publish_stage(topic, "profile", profile=husband)

    # ── Stage 2: filter — top-K wife candidates from the cohort ────────
    try:
        cohort = _load_cohort(year, ablation)
    except FileNotFoundError:
        await broker.publish(topic, {
            "type": "error",
            "error": f"cohort {year} ({ablation}) not found",
        })
        await broker.close(topic)
        return {"error": "cohort missing"}

    # Pick all pairs scored against this husband; keep top-K by score.
    pairs_for_h = [p for p in cohort["pairs"] if p["husband_id"] == husband_id]
    if not pairs_for_h:
        await broker.publish(topic, {
            "type": "error",
            "error": f"no candidates in cohort {year} for {husband_id}",
        })
        await broker.close(topic)
        return {"error": "no candidates"}
    pairs_for_h.sort(key=lambda p: p["score"], reverse=True)
    pairs_top = pairs_for_h[:TOP_K_CANDIDATES]

    # Build candidate records with profiles.
    candidates: list[dict] = []
    for p in pairs_top:
        wife_profile = get_profile(p["wife_id"])
        wife_profile["sex"] = "F"
        candidates.append({
            "person": wife_profile,
            "pre_score": float(p["score"]),
            "hgt_label": int(p.get("label", 0)),
            "score_gap": float(p.get("score_gap", 0.0)),
            "motif": {},   # space for motif enrichment later
        })

    await _publish_stage(topic, "filter",
                        funnel={"in_cohort": len(pairs_for_h), "kept": len(candidates)},
                        candidates=[
                            {"person": c["person"], "pre_score": c["pre_score"],
                             "hgt_label": c["hgt_label"], "score_gap": c["score_gap"]}
                            for c in candidates
                        ])

    # ── Stage 3: target agent scores all candidates ────────────────────
    macro = _macro_rules() + "\n" + state.hints_as_string(husband_id, role="target")
    micro = _micro_rules()
    target_scores = await agent.evaluate_candidates(
        target_profile=husband,
        candidates=candidates,
        macro_rules=macro,
        micro_rules=micro,
        topic=topic,
        side="target",
    )
    await broker.publish(topic, {"type": "target_scores", "scores": target_scores})

    # ── Stage 4: bilateral — each candidate ≥ threshold scores back ────
    cand_macro = _macro_rules() + "\n" + state.hints_as_string(husband_id, role="candidates")
    bilateral: dict[str, dict] = {}

    async def _eval_one(c: dict) -> tuple[str, dict]:
        wife = c["person"]
        result = await agent.evaluate_one(
            target_profile=husband,         # wife is told to score this person
            candidate_profile=wife,         # ...as if she's the evaluator
            macro_rules=cand_macro,
            micro_rules=micro,
            topic=topic,
        )
        return wife["id"], result

    tasks = []
    for ts in target_scores:
        if ts["score"] < BILATERAL_THRESHOLD:
            continue
        c_match = next((cc for cc in candidates if cc["person"]["id"] == ts["candidate_id"]), None)
        if c_match:
            tasks.append(_eval_one(c_match))
    if tasks:
        for cid, res in await asyncio.gather(*tasks, return_exceptions=False):
            bilateral[cid] = res
    await broker.publish(topic, {"type": "bilateral_scores", "scores": bilateral})

    # ── Stage 5: final ranking ─────────────────────────────────────────
    target_by_id = {ts["candidate_id"]: ts for ts in target_scores}
    ranking = []
    for c in candidates:
        cid = c["person"]["id"]
        ts = target_by_id.get(cid, {"score": 5, "reason": "no target score"})
        bs = bilateral.get(cid)
        if bs:
            avg = (ts["score"] + bs["score"]) / 2.0
        else:
            avg = ts["score"] * 0.85   # penalise candidates that didn't get bilateral
        gamma_pre = _sigmoid(c["pre_score"])
        final_score = avg * gamma_pre
        ranking.append({
            "candidate_id": cid,
            "wife_id": cid,
            "target_score": ts["score"],
            "target_reason": ts.get("reason", ""),
            "candidate_score": bs["score"] if bs else None,
            "candidate_reason": bs["reason"] if bs else None,
            "pre_score": c["pre_score"],
            "score_gap": c["score_gap"],
            "hgt_label": c["hgt_label"],
            "final_score": round(final_score, 4),
        })
    ranking.sort(key=lambda r: r["final_score"], reverse=True)

    chosen = None
    if ranking and ranking[0]["final_score"] >= COMMIT_THRESHOLD * _sigmoid(2.0):
        # Above threshold (scaled by sigmoid prior of a moderately confident logit).
        chosen = ranking[0]

    await broker.publish(topic, {
        "type": "final_ranking",
        "ranking": ranking,
        "chosen": chosen,
    })

    if auto_commit and chosen:
        rec = state.commit_match(
            husband_id=husband_id, wife_id=chosen["wife_id"],
            score=chosen["final_score"], source="auto",
        )
        await broker.publish(topic, {"type": "committed", "match": rec})

    await broker.close(topic)
    return {
        "husband_id": husband_id, "year": year, "ablation": ablation,
        "n_candidates": len(candidates), "ranking": ranking, "chosen": chosen,
    }
