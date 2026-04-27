"""6-round bilateral marriage negotiation orchestrator.

Replaces the single-shot ``negotiator.py`` flow. Each husband negotiation
plays out as six discrete rounds, each gated on a user-driven advance:

    Round 1 — persona       : every actor (husband + K candidates) reads
                              their DS0003 life history + HGT pre-score
                              and emits a persona resume.
    Round 2 — impressions   : target reads candidate resumes, asks one
                              pointed question per candidate, candidates
                              answer. Both sides score each other.
    Round 3 — deep-dive     : same loop, focus on values + household fit.
    Round 4 — rebuttals     : same loop, focus on flaws / red flags.
    Round 5 — alignment     : same loop, focus on long-term alignment.
    Round 6 — final         : compute final score = (s+t)/2 − λ·|s−t|
                              with λ = 0.3; emit final_ranking.

The orchestrator pauses after every round (a ``round_paused`` frame) and
awaits an ``asyncio.Event`` that the FastAPI ``/advance`` endpoint sets
when the user clicks "Approve & Advance". Hints arrive through an
``asyncio.Queue`` and are drained between rounds; each drained hint
emits a ``hint_ack`` frame and is appended to per-actor system context
for the next round's prompt.

Round 1 personas, the husband's per-round queries, and each candidate's
per-round answers are produced by ``llm_helpers.chat_json`` against the
prompt templates in ``server/mas/prompts/*.txt``. When the API key is
unset (``is_llm_available() == False``) or any individual call fails
(parse error, API error, missing keys), the orchestrator falls back to
the deterministic heuristics preserved below — so dev mode without a
key still produces all six rounds and the same protocol frames.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from .profiles import get_profile
from .state import state

# Sibling units 1/2/3 land in parallel; degrade independently so that e.g.
# Unit 1 landing alone still gives heuristic personas access to real events.
try:
    from server.data.events_loader import (
        load_events, load_income, get_birth_year,
    )
    _EVENTS_LOADER_AVAILABLE = True
except ImportError:
    _EVENTS_LOADER_AVAILABLE = False

try:
    from server.mas.llm_helpers import (
        chat_json, render_prompt, events_block, income_block, is_llm_available,
    )
    _LLM_HELPERS_AVAILABLE = True
except ImportError:
    _LLM_HELPERS_AVAILABLE = False

try:
    from server.mas.motif_matcher import match_motifs
    _MOTIF_MATCHER_AVAILABLE = True
except ImportError:
    _MOTIF_MATCHER_AVAILABLE = False

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DATA = ROOT.parent / "viz" / "data"

TOP_K_CANDIDATES = 8
COMMIT_THRESHOLD = 6.5
LAMBDA_GAP = 0.3                      # final-score gap penalty
ROUND_LABELS = {
    1: "persona",
    2: "impressions",
    3: "deep-dive",
    4: "rebuttals",
    5: "alignment",
    6: "final",
}
ROUND_FOCUS = {
    2: "form initial impressions and question any obvious red flags",
    3: "probe values, household fit, and shared priorities",
    4: "test honesty by following up on weaknesses or contradictions",
    5: "evaluate long-term alignment and complementarity",
}

PublishFn = Callable[[dict[str, Any]], Awaitable[None]]


# ── Helpers ───────────────────────────────────────────────────────────


def _cohort_path(year: int, ablation: str) -> Path:
    suffix = "__unablated" if ablation == "unablated" else ""
    return CANONICAL_DATA / f"cohort_{year}{suffix}.json"


def _load_cohort(year: int, ablation: str) -> dict:
    with _cohort_path(year, ablation).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _safe_load_narrative(person_id: str, year: int) -> dict:
    """Returns {events, income, birth_year} — empty if DS0003 not available.

    Short-circuits when no parquet cache exists: the .rda direct-load path
    via pyreadr blocks the event loop for 30+ seconds on a 1.5M-row file,
    and DS0003 doesn't actually have the YEAR/PERSON_ID columns the loader
    expects (verified empirically — it has FOUNDER_ID and no time series).
    Skipping the load lets round 1 paint immediately and rounds 2-5 still
    run in stub mode.
    """
    cache = ROOT.parent / "data" / "processed" / "ds0003" / "ds0003_joined.parquet"
    if not cache.exists() or not _EVENTS_LOADER_AVAILABLE:
        return {"events": [], "income": [], "birth_year": None}
    try:
        birth = get_birth_year(person_id)
        start = birth if birth is not None else year - 80
        return {
            "events": load_events(person_id, start, year),
            "income": load_income(person_id, start, year),
            "birth_year": birth,
        }
    except Exception as exc:
        log.warning("narrative load failed for %s: %s", person_id, exc)
        return {"events": [], "income": [], "birth_year": None}


def _persona_from_heuristic(profile: dict, narrative: dict, pre_score: float | None) -> dict:
    """Deterministic persona used by the stub backend (and as fallback when
    Qwen returns garbage). Pulls signal from sex + birth year + banner +
    income trajectory + event types."""
    sex = "female" if profile.get("sex") in (1, "1", "F") else "male"
    by = profile.get("birth_year") or narrative.get("birth_year")
    banner = profile.get("banner_id")
    events = narrative.get("events") or []
    income = narrative.get("income") or []
    event_kinds = {e.get("event_1") for e in events} | {e.get("event_2") for e in events}
    event_kinds.discard(None)
    inc_levels = [r.get("level") for r in income if r.get("level")]
    inc_high = sum(1 for l in inc_levels if l == "high")
    inc_low = sum(1 for l in inc_levels if l == "low")

    traits: list[str] = []
    if banner is not None: traits.append(f"banner-{banner} household")
    if "Returned after absconding" in event_kinds: traits.append("turbulent youth")
    if inc_high >= 3: traits.append("financially established")
    if inc_low >= 3 and inc_high == 0: traits.append("modest means")
    if "In-Marriage" in event_kinds: traits.append("prior marriage exposure")
    if not traits: traits.append("typical commoner profile")

    values = ["banner endogamy", "lineage continuity"]
    if pre_score is not None and pre_score > 1.0:
        values.append("HGT-favoured pairing")

    red_flags: list[str] = []
    if "Lost" in event_kinds: red_flags.append("disappearance years on register")
    if inc_low >= 3 and inc_high >= 1:
        red_flags.append("volatile income trajectory")
    if pre_score is not None and pre_score < -1.0:
        red_flags.append("HGT pre-score is negative")

    headline = f"{sex.title()} born {by or '?'}, banner {banner or '?'}; {traits[0]}"
    return {
        "headline": headline,
        "traits": traits,
        "values": values,
        "red_flags": red_flags,
    }


def _question_for_red_flag(persona: dict, focus: str) -> str:
    flag = (persona.get("red_flags") or [""])[0]
    if flag:
        return f"On {focus}: can you explain {flag}?"
    return f"On {focus}: what would you bring to a household at this stage of life?"


def _answer_in_persona(persona: dict, query: str) -> str:
    trait = (persona.get("traits") or ["a steady disposition"])[0]
    val = (persona.get("values") or ["lineage continuity"])[0]
    return (
        f"As someone with {trait}, I see this through the lens of {val}. "
        f"Regarding your concern, I would offer evidence from my register record."
    )


def _score_pair(my_persona: dict, other_persona: dict, pre_score: float | None,
                round_n: int) -> tuple[float, str]:
    """Heuristic scoring: persona overlap + HGT prior, with mild round-over-round
    convergence (rounds tighten as agents learn each other)."""
    s = 5.0
    reasons: list[str] = []

    my_vals = set(my_persona.get("values") or [])
    other_vals = set(other_persona.get("values") or [])
    overlap = len(my_vals & other_vals)
    if overlap:
        s += 0.6 * overlap
        reasons.append(f"shared values ({overlap})")

    other_flags = other_persona.get("red_flags") or []
    if other_flags:
        s -= 0.5 * len(other_flags)
        reasons.append(f"flags {len(other_flags)}")

    if pre_score is not None:
        s += 0.4 * float(pre_score)
        reasons.append(f"HGT {pre_score:+.2f}")

    # Slight per-round convergence: variance shrinks each round (agents
    # update toward the mean of their initial impression).
    if round_n > 2:
        s = 5.0 + (s - 5.0) * (1.0 + 0.1 * (round_n - 2))

    s = max(0.0, min(10.0, round(s, 2)))
    if not reasons:
        reasons.append("baseline impression")
    return s, "; ".join(reasons)


def _final_score(s: float, t: float, lam: float = LAMBDA_GAP) -> float:
    """(s + t)/2 − λ·|s − t|. Rewards mutual-high with small gap."""
    if s is None or t is None:
        return float(min(s or 0.0, t or 0.0)) * 0.5
    return round((s + t) / 2.0 - lam * abs(s - t), 4)


async def _drain_hints(publish: PublishFn, queue: asyncio.Queue,
                       hint_log: dict[str, list[str]]) -> None:
    """Pull every queued hint, emit hint_ack, route into per-role log."""
    while not queue.empty():
        try:
            h = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        role = h.get("role", "all")
        text = h.get("text", "")
        hint_log.setdefault(role, []).append(text)
        await publish({"type": "hint_ack", "role": role, "text": text,
                       "round": h.get("round")})


def _hint_context(hint_log: dict[str, list[str]], for_role: str) -> str:
    """Most-recent 3 hints addressed to ``for_role`` or 'all' as a system note."""
    bag: list[str] = []
    bag.extend(hint_log.get("all", [])[-3:])
    bag.extend(hint_log.get(for_role, [])[-3:])
    if not bag:
        return ""
    return "User guidance: " + " | ".join(bag[-3:])


def _hint_block(hint_log: dict[str, list[str]], for_role: str) -> str:
    """Wrap _hint_context for prompt injection (renders blank when no hints)."""
    ctx = _hint_context(hint_log, for_role)
    if not ctx:
        return ""
    return f"USER GUIDANCE\n-------------\n{ctx}"


def _sex_for_prompt(profile: dict) -> str:
    """Render sex codes from either CMGPD raw (1/2) or display ('M'/'F') form."""
    raw = profile.get("sex")
    if raw in ("M", "m", 2, "2"):
        return "male"
    if raw in ("F", "f", 1, "1"):
        return "female"
    return "?"


def _resume_block(person_id: str, resume: dict) -> str:
    """Render a resume dict for inclusion in query/answer prompts."""
    headline = resume.get("headline", "")
    traits = ", ".join(resume.get("traits") or []) or "—"
    values = ", ".join(resume.get("values") or []) or "—"
    flags = ", ".join(resume.get("red_flags") or []) or "—"
    return (
        f"id: {person_id}\n"
        f"headline: {headline}\n"
        f"traits: {traits}\n"
        f"values: {values}\n"
        f"red_flags: {flags}"
    )


def _normalize_score(value: Any, default: float = 5.0) -> float:
    """Coerce LLM int score (1-10) to a clamped float in [0, 10]."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(10.0, round(v, 2)))


def _resume_is_valid(resume: Any) -> bool:
    """Reject empty / malformed resume dicts so we cleanly fall back."""
    if not isinstance(resume, dict):
        return False
    if not resume.get("headline"):
        return False
    # traits/values/red_flags must be present (lists; possibly empty).
    for k in ("traits", "values", "red_flags"):
        if k not in resume:
            return False
    return True


# ── Per-call LLM wrappers (each falls back to heuristic on any failure) ──


async def _persona_call(
    *, person_id: str, role: str, profile: dict, narrative: dict,
    pre_score: float | None, year: int, ablation: str,
    hint_log: dict[str, list[str]], hint_role: str,
) -> dict:
    """Render persona.txt + chat_json. On any failure return heuristic."""
    if not _LLM_HELPERS_AVAILABLE or not is_llm_available():
        return _persona_from_heuristic(profile, narrative, pre_score)
    try:
        prompt = render_prompt(
            "persona",
            person_id=person_id,
            role=role,
            sex=_sex_for_prompt(profile),
            birth_year=profile.get("birth_year") or narrative.get("birth_year") or "?",
            banner_id=profile.get("banner_id") if profile.get("banner_id") is not None else "?",
            community_id=profile.get("community_id") if profile.get("community_id") is not None else "?",
            household_id=profile.get("household_id") or "?",
            pre_score=(f"{pre_score:+.3f}" if pre_score is not None else "n/a"),
            events_block=events_block(narrative.get("events") or []),
            income_block=income_block(narrative.get("income") or []),
            year=year,
            ablation=ablation,
            hint_block=_hint_block(hint_log, hint_role),
        )
        result = await chat_json(
            messages=[
                {"role": "system",
                 "content": "You produce concise persona resumes for historical figures."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        if not _resume_is_valid(result):
            log.warning("persona for %s: invalid resume %r; falling back", person_id, result)
            return _persona_from_heuristic(profile, narrative, pre_score)
        # Coerce list fields to actual lists (some models return stringy values).
        for k in ("traits", "values", "red_flags"):
            v = result.get(k)
            if isinstance(v, str):
                result[k] = [v]
            elif not isinstance(v, list):
                result[k] = []
        return result
    except Exception as exc:
        log.warning("persona LLM call failed for %s (%s); using heuristic", person_id, exc)
        return _persona_from_heuristic(profile, narrative, pre_score)


async def _query_call(
    *, husband_id: str, husband_persona: dict, candidates: list[dict],
    round_focus: str, hint_log: dict[str, list[str]], round_n: int,
) -> dict[str, dict]:
    """Single husband call returning {cid: {score: float, reason: str, query: str}}.

    Heuristic fallback fills any candidate the LLM omitted.
    """
    fallback: dict[str, dict] = {}
    for c in candidates:
        cid = c["person"]["id"]
        h_score, h_reason = _score_pair(husband_persona, c["persona"],
                                        c["pre_score"], round_n)
        h_query = _question_for_red_flag(c["persona"], round_focus)
        fallback[cid] = {"score": h_score, "reason": h_reason, "query": h_query}

    if not _LLM_HELPERS_AVAILABLE or not is_llm_available():
        return fallback

    try:
        cand_block = "\n\n".join(
            _resume_block(c["person"]["id"], c["persona"]) for c in candidates
        )
        prompt = render_prompt(
            "query",
            asker_id=husband_id,
            asker_role="target",
            asker_resume=_resume_block(husband_id, husband_persona),
            round_focus=round_focus,
            candidate_block=cand_block,
            hint_block=_hint_block(hint_log, "target"),
        )
        result = await chat_json(
            messages=[
                {"role": "system",
                 "content": ("You are roleplaying a Qing-dynasty marriage candidate. "
                             "Produce JSON exactly matching the requested schema.")},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
    except Exception as exc:
        log.warning("query LLM call failed (%s); using heuristic", exc)
        return fallback

    if not isinstance(result, dict):
        return fallback

    out = dict(fallback)
    for entry in result.get("scores") or []:
        cid = str(entry.get("candidate_id") or "")
        if cid in out:
            out[cid] = {
                **out[cid],
                "score": _normalize_score(entry.get("score"), out[cid]["score"]),
                "reason": (entry.get("reason") or out[cid]["reason"])[:500],
            }
    for entry in result.get("queries") or []:
        cid = str(entry.get("candidate_id") or "")
        if cid in out:
            text = entry.get("text") or out[cid]["query"]
            out[cid]["query"] = str(text)[:500]
    return out


async def _answer_call(
    *, husband_id: str, husband_persona: dict, candidate: dict,
    question_text: str, round_focus: str, hint_log: dict[str, list[str]],
    round_n: int,
) -> dict:
    """Per-candidate call returning {answer, score, reason}."""
    cid = candidate["person"]["id"]
    h_score, h_reason = _score_pair(candidate["persona"], husband_persona,
                                    candidate["pre_score"], round_n)
    h_answer = _answer_in_persona(candidate["persona"], question_text)
    fallback = {"answer": h_answer, "score": h_score, "reason": h_reason}

    if not _LLM_HELPERS_AVAILABLE or not is_llm_available():
        return fallback

    try:
        prompt = render_prompt(
            "answer",
            answerer_id=cid,
            answerer_role="candidate",
            asker_id=husband_id,
            answerer_resume=_resume_block(cid, candidate["persona"]),
            asker_resume=_resume_block(husband_id, husband_persona),
            question_text=question_text,
            round_focus=round_focus,
            hint_block=_hint_block(hint_log, f"c-{cid}"),
        )
        result = await chat_json(
            messages=[
                {"role": "system",
                 "content": ("You are roleplaying a Qing-dynasty marriage candidate. "
                             "Produce JSON exactly matching the requested schema.")},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
    except Exception as exc:
        log.warning("answer LLM call failed for %s (%s); using heuristic", cid, exc)
        return fallback

    if not isinstance(result, dict) or not result.get("answer"):
        return fallback
    return {
        "answer": str(result.get("answer"))[:1000],
        "score": _normalize_score(result.get("score"), h_score),
        "reason": str(result.get("reason") or h_reason)[:500],
    }


# ── Main orchestrator ─────────────────────────────────────────────────


async def mas_negotiate_rounds(
    husband_id: str,
    year: int,
    ablation: str,
    publish: PublishFn,
    advance_event: asyncio.Event,
    hint_queue: asyncio.Queue,
    auto_commit: bool = False,
) -> None:
    hint_log: dict[str, list[str]] = {}

    # ── start ──
    await publish({"type": "start", "husband_id": husband_id,
                   "year": year, "ablation": ablation})

    # ── stage:profile ──
    husband = get_profile(husband_id)
    husband.setdefault("sex", "M")
    await publish({"type": "stage", "stage": "profile", "profile": husband})

    # ── stage:filter (top-K candidates from cohort JSON) ──
    try:
        cohort = _load_cohort(year, ablation)
    except FileNotFoundError:
        await publish({"type": "error",
                       "error": f"cohort {year} ({ablation}) not found"})
        await publish({"type": "done"})
        return

    pairs_for_h = sorted(
        (p for p in cohort["pairs"] if p["husband_id"] == husband_id),
        key=lambda p: p["score"], reverse=True,
    )
    if not pairs_for_h:
        await publish({"type": "error",
                       "error": f"no candidates in cohort {year} for {husband_id}"})
        await publish({"type": "done"})
        return

    pairs_top = pairs_for_h[:TOP_K_CANDIDATES]
    candidates: list[dict] = []
    for p in pairs_top:
        wife_profile = get_profile(p["wife_id"])
        wife_profile.setdefault("sex", "F")
        candidates.append({
            "person": wife_profile,
            "pre_score": float(p["score"]),
            "hgt_label": int(p.get("label", 0)),
            "score_gap": float(p.get("score_gap", 0.0)),
            "pair_record": p,
        })

    await publish({
        "type": "stage", "stage": "filter",
        "funnel": {"in_cohort": len(pairs_for_h), "kept": len(candidates)},
        "candidates": [
            {"person": c["person"], "pre_score": c["pre_score"],
             "hgt_label": c["hgt_label"], "score_gap": c["score_gap"]}
            for c in candidates
        ],
    })

    # ── narrative pre-fetch (husband + each candidate) ──
    husband_narr = _safe_load_narrative(husband_id, year)
    await publish({"type": "narrative", "person_id": husband_id, **husband_narr})
    for c in candidates:
        cid = c["person"]["id"]
        c["narrative"] = _safe_load_narrative(cid, year)
        await publish({"type": "narrative", "person_id": cid, **c["narrative"]})

    # ───────────────────────────── ROUND 1: PERSONA ─────────────────────
    await publish({"type": "round_start", "round": 1, "label": ROUND_LABELS[1]})

    # Run K+1 persona calls concurrently. Husband has no motif (no self-pair).
    for c in candidates:
        c["motifs"] = (
            match_motifs(husband, c["person"], c["pair_record"])
            if _MOTIF_MATCHER_AVAILABLE else []
        )

    persona_tasks = [asyncio.create_task(_persona_call(
        person_id=husband_id, role="target", profile=husband,
        narrative=husband_narr, pre_score=None,
        year=year, ablation=ablation, hint_log=hint_log, hint_role="target",
    ))]
    for c in candidates:
        cid = c["person"]["id"]
        persona_tasks.append(asyncio.create_task(_persona_call(
            person_id=cid, role="candidate", profile=c["person"],
            narrative=c["narrative"], pre_score=c["pre_score"],
            year=year, ablation=ablation, hint_log=hint_log, hint_role=f"c-{cid}",
        )))

    persona_results = await asyncio.gather(*persona_tasks)
    husband_persona = persona_results[0]
    await publish({"type": "persona", "person_id": husband_id,
                   "resume": husband_persona, "motifs": []})
    for c, persona in zip(candidates, persona_results[1:]):
        cid = c["person"]["id"]
        c["persona"] = persona
        await publish({"type": "persona", "person_id": cid,
                       "resume": persona, "motifs": c.get("motifs") or []})

    await publish({"type": "round_paused", "round": 1, "awaiting": "user_advance"})
    await advance_event.wait(); advance_event.clear()
    await _drain_hints(publish, hint_queue, hint_log)

    # ───────────────────────── ROUNDS 2–5: QUERY/ANSWER/SCORE ───────────
    round_pairs: list[dict] = []
    for round_n in range(2, 6):
        await publish({"type": "round_start", "round": round_n,
                       "label": ROUND_LABELS[round_n]})
        focus = ROUND_FOCUS[round_n]

        # Single husband call: scores all K candidates and drafts K queries.
        query_map = await _query_call(
            husband_id=husband_id, husband_persona=husband_persona,
            candidates=candidates, round_focus=focus, hint_log=hint_log,
            round_n=round_n,
        )

        # Emit one query frame per candidate (preserves cohort ordering).
        for c in candidates:
            cid = c["person"]["id"]
            await publish({"type": "query", "from": "target",
                           "to": f"c-{cid}", "text": query_map[cid]["query"]})

        # Per-candidate answer calls in parallel.
        answer_tasks = [
            asyncio.create_task(_answer_call(
                husband_id=husband_id, husband_persona=husband_persona,
                candidate=c, question_text=query_map[c["person"]["id"]]["query"],
                round_focus=focus, hint_log=hint_log, round_n=round_n,
            ))
            for c in candidates
        ]
        answer_results = await asyncio.gather(*answer_tasks)

        round_pairs = []
        for c, ans in zip(candidates, answer_results):
            cid = c["person"]["id"]
            await publish({"type": "answer", "from": f"c-{cid}",
                           "to": "target", "text": ans["answer"]})
            qm = query_map[cid]
            round_pairs.append({
                "candidate_id": cid,
                "target_score": _normalize_score(qm["score"]),
                "candidate_score": _normalize_score(ans["score"]),
                "target_reason": qm["reason"],
                "candidate_reason": ans["reason"],
            })

        await publish({"type": "round_scores", "round": round_n, "pairs": round_pairs})
        await publish({"type": "round_paused", "round": round_n,
                       "awaiting": "user_advance"})
        await advance_event.wait(); advance_event.clear()
        await _drain_hints(publish, hint_queue, hint_log)

    # ────────────────────────────── ROUND 6: FINAL ──────────────────────
    await publish({"type": "round_start", "round": 6, "label": ROUND_LABELS[6]})

    # Use the latest round 5 scores as input to the formula.
    last_scores = {p["candidate_id"]: p for p in round_pairs}
    ranking: list[dict] = []
    for c in candidates:
        cid = c["person"]["id"]
        sp = last_scores.get(cid, {})
        t = sp.get("target_score")
        s = sp.get("candidate_score")
        ranking.append({
            "candidate_id": cid,
            "wife_id": cid,
            "target_score": t,
            "candidate_score": s,
            "target_reason": sp.get("target_reason"),
            "candidate_reason": sp.get("candidate_reason"),
            "pre_score": c["pre_score"],
            "score_gap": c["score_gap"],
            "lambda": LAMBDA_GAP,
            "final_score": _final_score(s if s is not None else 0.0,
                                         t if t is not None else 0.0),
        })
    ranking.sort(key=lambda r: r["final_score"], reverse=True)

    chosen = None
    if auto_commit and ranking and ranking[0]["final_score"] >= COMMIT_THRESHOLD:
        chosen = ranking[0]

    await publish({"type": "final_ranking", "ranking": ranking, "chosen": chosen})

    if chosen is not None:
        rec = state.commit_match(
            husband_id=husband_id, wife_id=chosen["wife_id"],
            score=chosen["final_score"], source="auto-rounds",
            year=year, ablation=ablation,
        )
        await publish({"type": "committed", "match": rec})

    await publish({"type": "done"})
