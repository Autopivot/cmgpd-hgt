"""LLM-driven NLP hint router.

The 6-round negotiation pipeline accepts user supervision via the
`POST /api/negotiate/{id}/hint` endpoint. That path takes pre-structured
text (frontend regex matches `@c-Pxxxx: eliminate` style commands) and
drops anything else into the chat-log. This module exposes the
*free-text* alternative: arbitrary natural-language guidance is sent to
Qwen, parsed into a strict action schema, and then dispatched against
the in-memory MAS state — persona-field overrides, score adjustments,
eliminations, or generic inject_directive routing through the existing
hint queue.

Public entry point:
    parse_and_dispatch(session_id, free_text, context) -> dict

The returned dict contains:
    {
      "actions_applied": [...],
      "rationale": "...",
      "warnings": [...],
      "raw_actions": [...],
    }

Defensive design: if the LLM is unavailable, returns invalid JSON, or
rejects the request, we fall back to a single inject_directive containing
the raw user text so the user's guidance is never lost.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .llm_helpers import chat_json, is_llm_available, render_prompt
from .state import state as mas_state

log = logging.getLogger(__name__)


# Permitted enum members per action type.
_PERSONA_FIELDS = {
    "banner", "income_decile", "marriage_history", "values",
    "traits", "red_flags", "headline",
}
_SCORE_DIMS = {"h_to_w", "w_to_h", "trust", "values", "compatibility", "both"}
_ACTION_TYPES = {
    "modify_persona_field", "modify_score", "eliminate",
    "inject_directive", "noop_with_reason",
}


def _normalize_candidate_id(raw: str) -> str:
    """Coerce 'P12345' / '12345' / 'c-P12345' into the canonical 'c-Pxxxxx'."""
    s = (raw or "").strip()
    if not s:
        return s
    if s.startswith("c-"):
        return s
    if s.startswith("P"):
        return f"c-{s}"
    if s.lstrip("-").isdigit():
        return f"c-P{s}"
    return s


async def _llm_parse(free_text: str, context: dict) -> dict:
    """Render hint_router.txt + call Qwen. Returns the parsed dict or {}."""
    cand_ids = context.get("candidate_ids") or []
    current_round = context.get("current_round")
    user_block = (
        f"context.candidate_ids = {json.dumps(cand_ids)}\n"
        f"context.current_round = {current_round!r}\n"
        f"user: {free_text!r}"
    )
    try:
        system_prompt = render_prompt("hint_router")
    except Exception as exc:  # pragma: no cover
        log.error("hint_router prompt render failed: %s", exc)
        return {}
    try:
        result = await chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_block},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        log.warning("hint_router LLM call failed: %s", exc)
        return {}
    if not isinstance(result, dict):
        return {}
    return result


def _validate_action(action: dict, candidate_ids: list[str],
                     warnings: list[str]) -> dict | None:
    """Return a normalized action dict or None (with a warning logged)."""
    if not isinstance(action, dict):
        warnings.append(f"action not a dict: {action!r}")
        return None
    a_type = action.get("type")
    if a_type not in _ACTION_TYPES:
        warnings.append(f"unknown action type: {a_type!r}")
        return None

    if a_type == "noop_with_reason":
        return {"type": a_type, "reason": str(action.get("reason") or "")[:500]}

    if a_type == "inject_directive":
        target = action.get("target") or "all"
        if target not in ("all", "target"):
            target = _normalize_candidate_id(str(target))
        text = str(action.get("text") or "").strip()
        if not text:
            warnings.append("inject_directive missing text")
            return None
        return {"type": a_type, "target": target, "text": text[:500]}

    target = _normalize_candidate_id(str(action.get("target") or ""))
    if not target.startswith("c-"):
        warnings.append(f"action {a_type} target not a candidate id: {target!r}")
        return None
    if candidate_ids and target not in candidate_ids:
        warnings.append(f"action {a_type} target {target!r} not in context.candidate_ids")
        # Still allow dispatch — the user may know something we don't.

    if a_type == "eliminate":
        return {"type": a_type, "target": target}

    if a_type == "modify_persona_field":
        field = str(action.get("field") or "").strip()
        if field not in _PERSONA_FIELDS:
            warnings.append(f"unknown persona field: {field!r}")
            return None
        return {
            "type": a_type, "target": target, "field": field,
            "new_value": action.get("new_value"),
        }

    if a_type == "modify_score":
        dim = str(action.get("dimension") or "").strip()
        if dim not in _SCORE_DIMS:
            warnings.append(f"unknown score dimension: {dim!r}")
            return None
        delta = action.get("delta")
        absolute = action.get("absolute_value")
        if delta is None and absolute is None:
            warnings.append("modify_score missing both delta and absolute_value")
            return None
        try:
            delta_f = float(delta) if delta is not None else None
            abs_f = float(absolute) if absolute is not None else None
        except (TypeError, ValueError):
            warnings.append(f"modify_score numeric parse failed: {action!r}")
            return None
        return {
            "type": a_type, "target": target, "dimension": dim,
            "delta": delta_f, "absolute_value": abs_f,
        }

    return None  # pragma: no cover


def _dispatch_action(session_id: str, action: dict, current_round: int | None,
                     warnings: list[str]) -> dict:
    """Apply a normalized action to mas_state. Returns the (possibly augmented)
    action with an added `applied: bool` flag."""
    a_type = action["type"]
    husband_id = session_id

    if a_type == "noop_with_reason":
        log.info("hint_router noop for %s: %s", husband_id, action.get("reason"))
        return {**action, "applied": False}

    if a_type == "inject_directive":
        target = action["target"]
        role = "all" if target in ("all", "target") else target
        if target == "target":
            role = "target"
        mas_state.push_hint(husband_id, action["text"], role=role,
                            round_n=current_round)
        log.info("hint_router inject_directive for %s -> %s: %s",
                 husband_id, role, action["text"][:120])
        return {**action, "applied": True}

    target = action["target"]
    cid = target[2:] if target.startswith("c-") else target  # strip 'c-' for state ops

    if a_type == "eliminate":
        mas_state.eliminate_candidate(husband_id, target)
        # Also surface as a directive so the next-round prompt mentions it.
        mas_state.push_hint(
            husband_id,
            f"Candidate {target} has been eliminated by the supervisor and "
            f"should not appear in further consideration.",
            role="all", round_n=current_round,
        )
        log.info("hint_router eliminated %s for %s", target, husband_id)
        return {**action, "applied": True}

    if a_type == "modify_persona_field":
        field = action["field"]
        new_value = action["new_value"]
        mas_state.set_persona_override(husband_id, target, field, new_value)
        mas_state.push_hint(
            husband_id,
            f"Update for {target}: persona field '{field}' is now {new_value!r}. "
            f"Treat this as authoritative in the next round.",
            role=target, round_n=current_round,
        )
        log.info("hint_router persona_override %s.%s=%r for %s",
                 target, field, new_value, husband_id)
        return {**action, "applied": True}

    if a_type == "modify_score":
        dim = action["dimension"]
        delta = action.get("delta")
        absolute = action.get("absolute_value")
        mas_state.set_score_override(
            husband_id, target, dim, delta=delta, absolute=absolute,
        )
        if absolute is not None:
            phrasing = f"set the {dim} score for {target} to {absolute:.2f}"
        else:
            sign = "+" if (delta or 0) >= 0 else ""
            phrasing = f"adjust the {dim} score for {target} by {sign}{delta:.2f}"
        mas_state.push_hint(
            husband_id,
            f"Score override: {phrasing}. Apply this in the next round's "
            f"scoring before any other adjustment.",
            role="all", round_n=current_round,
        )
        log.info("hint_router score_override %s.%s delta=%r abs=%r for %s",
                 target, dim, delta, absolute, husband_id)
        return {**action, "applied": True}

    warnings.append(f"unhandled action at dispatch time: {action!r}")
    return {**action, "applied": False}


async def parse_and_dispatch(session_id: str, free_text: str,
                             context: dict) -> dict:
    """Parse `free_text` via Qwen, dispatch the resulting actions against
    the in-memory MAS state for `session_id` (a husband id), and return a
    structured report.

    On any failure (no API key, JSON parse error, empty action list) we
    fall back to a single inject_directive containing the raw text so the
    user's guidance is preserved as a soft hint.
    """
    free_text = (free_text or "").strip()
    context = context or {}
    candidate_ids = [str(c) for c in (context.get("candidate_ids") or [])]
    current_round = context.get("current_round")
    warnings: list[str] = []

    log.info(
        "hint_router parse session=%s round=%s text=%r ctx=%d-cands",
        session_id, current_round, free_text[:200], len(candidate_ids),
    )

    if not free_text:
        return {
            "actions_applied": [],
            "rationale": "Empty hint text — nothing to dispatch.",
            "warnings": ["empty free_text"],
            "raw_actions": [],
        }

    # Path 1: LLM available — let Qwen extract structured actions.
    parsed: dict = {}
    if is_llm_available():
        parsed = await _llm_parse(free_text, {
            "candidate_ids": candidate_ids,
            "current_round": current_round,
        })
    else:
        warnings.append("DASHSCOPE_API_KEY not set; skipping LLM parse")

    raw_actions = parsed.get("actions") if isinstance(parsed, dict) else None
    rationale = (parsed.get("rationale") if isinstance(parsed, dict) else "") or ""

    # Path 2 (defensive): no usable actions — fall back to inject_directive.
    if not raw_actions or not isinstance(raw_actions, list):
        warnings.append(
            "LLM produced no structured actions; falling back to inject_directive",
        )
        fallback = {
            "type": "inject_directive", "target": "all",
            "text": free_text[:500],
        }
        applied = _dispatch_action(session_id, fallback, current_round, warnings)
        return {
            "actions_applied": [applied],
            "rationale": rationale or "Fallback: raw text injected as a directive.",
            "warnings": warnings,
            "raw_actions": [fallback],
        }

    # Path 3: validate + dispatch each action in order.
    applied_list: list[dict] = []
    for action in raw_actions:
        norm = _validate_action(action, candidate_ids, warnings)
        if norm is None:
            continue
        applied_list.append(_dispatch_action(session_id, norm, current_round, warnings))

    if not applied_list:
        warnings.append(
            "all actions rejected during validation; falling back to inject_directive",
        )
        fallback = {
            "type": "inject_directive", "target": "all",
            "text": free_text[:500],
        }
        applied_list.append(
            _dispatch_action(session_id, fallback, current_round, warnings),
        )

    log.info("hint_router dispatched %d action(s) for %s", len(applied_list), session_id)
    return {
        "actions_applied": applied_list,
        "rationale": rationale,
        "warnings": warnings,
        "raw_actions": raw_actions,
    }
