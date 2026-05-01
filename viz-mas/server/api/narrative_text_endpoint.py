"""GET /api/narrative-text/{person_id}?year=N — LLM-narrated life paragraph.

Wraps the existing /api/narrative loader with a Qwen call against
`mas/prompts/narrative_text.txt`. Returns a single 50–110 word paragraph
covering birth, on-register events, and the income arc.

Falls back to a deterministic concatenation of `events_block` +
`income_block` text when the LLM is unavailable or returns malformed JSON
so the V5 popup always has something to render.
"""
from __future__ import annotations

import functools
import logging

from fastapi import APIRouter, HTTPException, Query

from ..data.events_loader import get_birth_year, load_events, load_income
from ..mas.llm_helpers import (
    chat_json, events_block, income_block,
    is_llm_available, render_prompt,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _normalise_id(pid: str) -> str:
    return pid if pid.startswith("P") else f"P{pid}"


def _fallback_paragraph(person_id: str, birth_year, events, income) -> str:
    """Deterministic narrative when the LLM is unavailable."""
    bits = []
    if birth_year is not None:
        bits.append(f"{person_id} (b. {birth_year}) appears in the DS0003 register")
    else:
        bits.append(f"{person_id} appears in the DS0003 register")
    if events:
        first, last = events[0], events[-1]
        evt_first = first.get("event_1") or first.get("event_2") or "?"
        evt_last = last.get("event_1") or last.get("event_2") or "?"
        if first.get("year") == last.get("year"):
            bits.append(f"with {len(events)} life event(s) recorded in {first.get('year')} — including {evt_first}")
        else:
            bits.append(
                f"with {len(events)} life event(s) spanning {first.get('year')}–{last.get('year')} "
                f"(first: {evt_first}; last: {evt_last})"
            )
    else:
        bits.append("with no on-register life events in this window")
    if income:
        ys = [r.get("year") for r in income if r.get("year") is not None]
        levels = [r.get("level") for r in income if r.get("level") is not None]
        if ys:
            kw = "steady"
            if len(set(levels)) > 1:
                kw = "varied"
            bits.append(
                f"and an income trace from {min(ys)}–{max(ys)} ({kw} across {len(ys)} year(s))"
            )
    return ". ".join(bits) + "."


async def _llm_paragraph(person_id, role, birth_year, cohort_year,
                         events, income):
    if not is_llm_available():
        return None
    prompt = render_prompt(
        "narrative_text",
        person_id=person_id,
        role=role or "?",
        birth_year=str(birth_year) if birth_year is not None else "?",
        cohort_year=cohort_year,
        events_block=events_block(events),
        income_block=income_block(income),
    )
    try:
        result = await chat_json(
            messages=[
                {"role": "system",
                 "content": "You produce concise life-history paragraphs."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("narrative-text LLM call failed: %s", exc)
        return None
    if not isinstance(result, dict):
        return None
    text = result.get("narrative")
    if not isinstance(text, str) or len(text.strip()) < 20:
        return None
    return text.strip()


@functools.lru_cache(maxsize=4096)
def _cached_loader(person_id: str, year: int) -> dict:
    """Cache the raw loader output; the LLM call is awaited per request.

    Canonical birth-year policy: DS0001 BIRTHYEAR (admin) first, DS0003
    birth-event year as fallback — same as `/api/narrative`, so every
    surface in the UI shows the same birth year for the same person.
    """
    try:
        from ..mas.profiles import get_profile as _get_profile
        prof = _get_profile(person_id)
        birth = prof.get("birth_year") if isinstance(prof, dict) else None
    except Exception:
        birth = None
    if birth is None:
        birth = get_birth_year(person_id)
    start = birth if birth is not None else year - 80
    events = load_events(person_id, start, year)
    income = load_income(person_id, start, year)
    return {"birth_year": birth, "events": events, "income": income}


_para_cache: dict[str, dict] = {}


@router.get("/narrative-text/{person_id}")
async def api_narrative_text(
    person_id: str,
    year: int = Query(..., ge=1700, le=2000),
    role: str | None = Query(None),
) -> dict:
    cache_key = f"{person_id}|{year}"
    if cache_key in _para_cache:
        return _para_cache[cache_key]

    base = _cached_loader(person_id, year)
    events = base["events"]
    income = base["income"]
    birth = base["birth_year"]
    if not events and not income:
        raise HTTPException(status_code=404, detail="person not found")

    nid = _normalise_id(person_id)
    paragraph = await _llm_paragraph(nid, role, birth, year, events, income)
    used_llm = paragraph is not None
    if paragraph is None:
        paragraph = _fallback_paragraph(nid, birth, events, income)

    payload = {
        "person_id": nid,
        "year": year,
        "birth_year": birth,
        "n_events": len(events),
        "n_income_years": len(income),
        "narrative": paragraph,
        "source": "llm" if used_llm else "fallback",
    }
    _para_cache[cache_key] = payload
    return payload
