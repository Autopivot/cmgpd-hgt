"""Reusable Qwen helpers for the V5 6-round bilateral negotiation pipeline.

The 6-round orchestrator (Unit 4) calls into these helpers to render prompt
templates and invoke Qwen with JSON-output guarantees. We deliberately keep
this module independent of the legacy single-shot `agent.QwenAgent` API so
the new round-based code can evolve without breaking `evaluate_candidates`.

Public API:
    chat_json         — async; call Qwen with a messages list, parse JSON,
                        retry once on parse failure, return {} on give-up.
    render_prompt     — read server/mas/prompts/{name}.txt, str.format(**kwargs).
    events_block      — format Unit 1's load_events output as a per-line block.
    income_block      — format Unit 1's load_income output as a per-line block.
    is_llm_available  — True iff DASHSCOPE_API_KEY is configured.

The DashScope OpenAI-compatible endpoint and model id are read from the same
mutable `_cfg` dict that `agent.py` uses, so updates via /api/llm_config
propagate to both code paths.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import agent as _agent_mod

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Cached AsyncOpenAI client, keyed by (api_key, base_url) so /api/llm_config
# updates are picked up automatically without a manual reset.
_client_cache: dict[tuple[str, str], Any] = {}


def _get_client() -> Any:
    """Return a cached AsyncOpenAI client for the current `_cfg`."""
    from openai import AsyncOpenAI
    cfg = _agent_mod._cfg
    key = (cfg["api_key"], cfg["base_url"])
    client = _client_cache.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        _client_cache[key] = client
    return client


def is_llm_available() -> bool:
    """True iff DASHSCOPE_API_KEY is set in agent's `_cfg`."""
    return bool(_agent_mod._cfg.get("api_key"))


def render_prompt(template_name: str, **kwargs: Any) -> str:
    """Read `server/mas/prompts/{template_name}.txt` and substitute `{field}`
    placeholders via `str.format(**kwargs)`.

    Raises:
        FileNotFoundError: if the template file does not exist.
        KeyError: if a `{field}` in the template has no matching kwarg.
    """
    path = _PROMPTS_DIR / f"{template_name}.txt"
    template = path.read_text(encoding="utf-8")
    return template.format(**kwargs)


def events_block(events: list[dict]) -> str:
    """Format Unit 1's `load_events` output into a per-line block.

    Each row looks like {"year": 1862, "event_1": "Birth", "event_2": None}.
    Returns a friendly fallback string when the list is empty.
    """
    if not events:
        return "(no events on register)"
    lines: list[str] = []
    for row in events:
        year = row.get("year")
        parts = [p for p in (row.get("event_1"), row.get("event_2")) if p]
        if not parts:
            continue
        lines.append(f"{year}: {' / '.join(parts)}")
    return "\n".join(lines) if lines else "(no events on register)"


def income_block(income: list[dict]) -> str:
    """Format Unit 1's `load_income` output into a per-line block.

    Each row looks like {"year": 1862, "income": 24, "level": "mid"}.
    Returns a friendly fallback string when the list is empty.
    """
    if not income:
        return "(no income on register)"
    lines: list[str] = []
    for row in income:
        year = row.get("year")
        amount = row.get("income")
        level = row.get("level")
        if amount is None:
            continue
        # Print integers without trailing .0 if the source is whole-valued.
        try:
            amt_num = float(amount)
            amt_str = str(int(amt_num)) if amt_num.is_integer() else f"{amt_num:.2f}"
        except (TypeError, ValueError):
            amt_str = str(amount)
        if level:
            lines.append(f"{year}: {amt_str} ({level})")
        else:
            lines.append(f"{year}: {amt_str}")
    return "\n".join(lines) if lines else "(no income on register)"


async def chat_json(
    messages: list[dict],
    *,
    json_schema_hint: dict | None = None,
    max_retries: int = 2,
    temperature: float = 0.7,
) -> dict:
    """Call Qwen and parse the JSON response.

    On parse failure, retry up to `max_retries` more times with an explicit
    "respond with valid JSON only" reminder appended to the conversation.
    Returns `{}` if every attempt fails or the API key is missing.

    Args:
        messages: OpenAI-style chat messages, e.g.
                  `[{"role": "system", "content": "..."}, {"role": "user", ...}]`.
        json_schema_hint: optional dict serialised into the system message as
                          plaintext to nudge the model toward a particular
                          output shape (this is NOT a real JSON-schema; the
                          DashScope endpoint only enforces "json_object").
        max_retries: total additional attempts after the first (so total calls
                     are at most `max_retries + 1`).
        temperature: sampling temperature passed to the model.
    """
    if not is_llm_available():
        log.warning("chat_json called but DASHSCOPE_API_KEY is not set; returning {}")
        return {}

    # Inject schema hint into the first system message (or prepend one).
    msgs: list[dict] = [dict(m) for m in messages]
    if json_schema_hint:
        hint = (
            "Your response MUST be a single JSON object matching this shape:\n"
            f"{json.dumps(json_schema_hint, ensure_ascii=False, indent=2)}"
        )
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = f"{msgs[0]['content']}\n\n{hint}"
        else:
            msgs.insert(0, {"role": "system", "content": hint})

    try:
        client = _get_client()
    except ImportError as exc:  # pragma: no cover - openai is a hard dep
        log.error("openai package missing: %s", exc)
        return {}
    model = _agent_mod._cfg["model"]

    attempts = max(1, max_retries + 1)
    for attempt in range(attempts):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                log.warning(
                    "chat_json: JSON parse failed on attempt %d/%d (%s); raw=%r",
                    attempt + 1, attempts, exc, content[:200],
                )
                # Append a corrective reminder for the next attempt.
                msgs = msgs + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply was not valid JSON. Respond "
                            "with a SINGLE valid JSON object only — no prose, "
                            "no markdown fences."
                        ),
                    },
                ]
                continue
            if isinstance(parsed, dict):
                return parsed
            # Some models wrap the object in a list; unwrap if exactly one item.
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                return parsed[0]
            log.warning("chat_json: parsed JSON is not a dict (%s)", type(parsed).__name__)
            return {}
        except Exception as exc:
            log.warning(
                "chat_json: API call failed on attempt %d/%d (%s)",
                attempt + 1, attempts, exc,
            )
    return {}
