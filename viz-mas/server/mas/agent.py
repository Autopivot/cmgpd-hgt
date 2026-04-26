"""LLM agent — Qwen via DashScope's OpenAI-compatible endpoint, with a
deterministic stub fallback when no API key is configured.

Both backends share the same async signature so the negotiator does not
care which is in use. The stub also produces faux reasoning text token
by token so V5's streaming UI works without an API key.

Adapted from D:/projects/jiapu-hgt-final/backend/app/mas/agent.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from .ws_broker import broker

log = logging.getLogger(__name__)

# ── Runtime config (mutable so the /api/llm_config endpoint can update it)
_cfg = {
    "api_key": os.environ.get("DASHSCOPE_API_KEY", "").strip(),
    "base_url": os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "model": os.environ.get("QWEN_MODEL", "qwen-plus-2025-04-28"),
    "max_concurrency": int(os.environ.get("LLM_MAX_CONCURRENCY", "8")),
    "temperature": 0.3,
}


def get_config() -> dict:
    return {
        "api_key_set": bool(_cfg["api_key"]),
        "model": _cfg["model"],
        "use_llm": bool(_cfg["api_key"]),
    }


def set_config(*, api_key: str | None = None, model: str | None = None) -> dict:
    if api_key is not None:
        _cfg["api_key"] = api_key.strip()
    if model:
        _cfg["model"] = model.strip()
    # Reset the singleton so the next call picks the new config.
    global _singleton
    _singleton = None
    return get_config()


SYSTEM_PROMPT = (
    "You are a historical reasoning engine for marriage matching in Qing-dynasty "
    "Liaoning (1749-1909). You evaluate compatibility based on injected social "
    "rules and family context. You are not a free agent — you score rule-weighted "
    "compatibility, not personal preference. Always respond in valid JSON."
)


def _build_evaluation_prompt(target_profile: dict, candidates: list[dict],
                             macro_rules: str, micro_rules: str) -> str:
    cand_lines = []
    for c in candidates:
        p = c.get("person", c)
        motif = c.get("motif", {})
        motif_desc = (f" structural-motif-match={motif.get('motif_id', 'none')}"
                      if motif.get("matched") else "")
        cand_lines.append(
            f"  - candidate {p['id']}: sex={p.get('sex','?')}, "
            f"born={p.get('birth_year','?')}, "
            f"banner={p.get('banner_id','?')}, "
            f"community={p.get('community_id','?')}, "
            f"household={p.get('household_id','?')},"
            f" hgt_pre_score={c.get('pre_score', '?')}{motif_desc}"
        )
    return f"""You are person {target_profile['id']}.
Your profile:
- sex: {target_profile.get('sex', '?')}
- born: {target_profile.get('birth_year', '?')}
- banner: {target_profile.get('banner_id', '?')}
- community: {target_profile.get('community_id', '?')}
- household: {target_profile.get('household_id', '?')}

Macro rules from Domain A (transferred common knowledge):
{macro_rules}

Micro rules (structural patterns):
{micro_rules}

Evaluate each of the {len(candidates)} candidates below as a potential spouse.
Score from 1 to 10 considering: age compatibility (husband 0-5y older is typical),
banner / social class alignment, household complementarity, sibling-precedent
patterns, and any structural motif match. Use the HGT pre-score as a prior
(higher = the model already favours this pair).

Candidates:
{chr(10).join(cand_lines)}

Respond as a JSON object with key "evaluations" containing an array of
{{"candidate_id": "Pxxx", "score": int, "reason": "..."}} entries. Use the
exact candidate_id strings from the list above.
"""


# ── Real Qwen backend ─────────────────────────────────────────────────
class QwenAgent:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from openai import AsyncOpenAI  # noqa: WPS433
        self.client = AsyncOpenAI(
            api_key=api_key or _cfg["api_key"],
            base_url=_cfg["base_url"],
        )
        self.model = model or _cfg["model"]
        self.semaphore = asyncio.Semaphore(_cfg["max_concurrency"])

    async def evaluate_candidates(
        self, target_profile: dict, candidates: list[dict],
        macro_rules: str, micro_rules: str, topic: str,
        temperature: float | None = None, side: str = "target",
    ) -> list[dict]:
        prompt = _build_evaluation_prompt(target_profile, candidates, macro_rules, micro_rules)
        async with self.semaphore:
            await broker.publish(topic, {
                "type": "agent_prompt",
                "side": side,
                "person_id": target_profile["id"],
                "prompt": prompt,
            })
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature if temperature is not None else _cfg["temperature"],
                    response_format={"type": "json_object"},
                    stream=True,
                )
                buf: list[str] = []
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        buf.append(delta)
                        await broker.publish(topic, {
                            "type": "agent_token",
                            "side": side,
                            "person_id": target_profile["id"],
                            "delta": delta,
                        })
                full_text = "".join(buf)
                try:
                    parsed = json.loads(full_text)
                except json.JSONDecodeError:
                    log.warning("Failed to parse JSON from %s: %s", self.model, full_text[:200])
                    return _fallback_scores(candidates)
                evals = parsed.get("evaluations") or parsed.get("scores") or []
                return _normalize_evals(evals, candidates)
            except Exception as e:
                log.warning("Qwen call failed (%s); falling back to stub", e)
                return await StubAgent().evaluate_candidates(
                    target_profile, candidates, macro_rules, micro_rules,
                    topic, side=side,
                )

    async def evaluate_one(self, target_profile: dict, candidate_profile: dict,
                           macro_rules: str, micro_rules: str, topic: str) -> dict:
        # Bilateral evaluation: candidate scores target back. We swap so the
        # candidate is the "I" and the original target is the only candidate.
        result = await self.evaluate_candidates(
            target_profile=candidate_profile,
            candidates=[{"person": target_profile, "pre_score": None, "motif": {}}],
            macro_rules=macro_rules,
            micro_rules=micro_rules,
            topic=topic,
            side="candidate",
        )
        return result[0] if result else {
            "candidate_id": target_profile["id"], "score": 5, "reason": "default",
        }


# ── Deterministic stub backend ─────────────────────────────────────────
class StubAgent:
    """Heuristic scoring + faux token streaming for offline / no-API mode."""

    async def evaluate_candidates(
        self, target_profile: dict, candidates: list[dict],
        macro_rules: str, micro_rules: str, topic: str,
        temperature: float = 0.3, side: str = "target",
    ) -> list[dict]:
        await broker.publish(topic, {
            "type": "agent_prompt", "side": side,
            "person_id": target_profile["id"],
            "prompt": "(stub agent — heuristic scoring; configure DASHSCOPE_API_KEY for real Qwen)",
        })
        results = []
        for c in candidates:
            p = c.get("person", c)
            motif = c.get("motif", {})
            score, reason = self._score(target_profile, p, motif, c.get("pre_score"))
            results.append({"candidate_id": p["id"], "score": score, "reason": reason})
            await self._stream_text(topic, target_profile["id"], reason, side=side)
        return results

    async def evaluate_one(self, target_profile: dict, candidate_profile: dict,
                           macro_rules: str, micro_rules: str, topic: str) -> dict:
        score, reason = self._score(candidate_profile, target_profile, {}, None)
        await self._stream_text(topic, candidate_profile["id"], reason, side="candidate")
        return {"candidate_id": target_profile["id"], "score": score, "reason": reason}

    def _score(self, t: dict, c: dict, motif: dict, pre_score: float | None) -> tuple[int, str]:
        score = 5.0
        reasons = []
        if t.get("banner_id") is not None and t.get("banner_id") == c.get("banner_id"):
            score += 2.0; reasons.append(f"same banner ({t['banner_id']})")
        elif t.get("banner_id") is not None and c.get("banner_id") is not None:
            score -= 1.0; reasons.append("different banner")
        if t.get("community_id") is not None and t.get("community_id") == c.get("community_id"):
            score += 1.0; reasons.append("same community")
        ty = t.get("birth_year"); cy = c.get("birth_year")
        if ty and cy:
            gap = abs(int(ty) - int(cy))
            if gap <= 5:    score += 1.5; reasons.append(f"close age (Δ={gap}y)")
            elif gap <= 10: score += 0.5; reasons.append(f"reasonable age (Δ={gap}y)")
            else:           score -= 1.0; reasons.append(f"large age gap (Δ={gap}y)")
        if motif.get("matched"):
            score += 1.5 * float(motif.get("avg_score", 0.0))
            reasons.append(f"motif match {motif.get('motif_id')}")
        if pre_score is not None:
            # HGT prior: each unit of logit ≈ 0.4 score points.
            score += 0.4 * float(pre_score)
            reasons.append(f"HGT pre-score {pre_score:+.2f}")
        score = max(1, min(10, int(round(score))))
        if not reasons:
            reasons.append("default heuristic")
        return score, "; ".join(reasons)

    async def _stream_text(self, topic: str, person_id: str, text: str, side: str = "target") -> None:
        for word in text.split():
            await broker.publish(topic, {
                "type": "agent_token", "side": side,
                "person_id": person_id, "delta": word + " ",
            })
            await asyncio.sleep(0.01)


def _fallback_scores(candidates: list[dict]) -> list[dict]:
    return [{"candidate_id": c.get("person", c)["id"], "score": 5, "reason": "fallback"}
            for c in candidates]


def _normalize_evals(raw: list[dict], candidates: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for r in raw:
        cid = r.get("candidate_id")
        if cid is None:
            continue
        cid = str(cid)
        try: score = int(r.get("score", 5))
        except (TypeError, ValueError): score = 5
        by_id[cid] = {
            "candidate_id": cid,
            "score": max(1, min(10, score)),
            "reason": (r.get("reason") or "")[:500],
        }
    out = []
    for c in candidates:
        cid = c.get("person", c)["id"]
        if cid in by_id:
            out.append(by_id[cid])
        else:
            out.append({"candidate_id": cid, "score": 5, "reason": "no LLM output"})
    return out


# ── Selector ───────────────────────────────────────────────────────────
_singleton: Any = None


def get_agent():
    global _singleton
    if _singleton is None:
        if _cfg["api_key"]:
            try:
                _singleton = QwenAgent()
                log.info("Using QwenAgent (model=%s)", _cfg["model"])
            except Exception as e:
                log.warning("QwenAgent init failed (%s); falling back to stub", e)
                _singleton = StubAgent()
        else:
            _singleton = StubAgent()
            log.info("Using StubAgent (no DASHSCOPE_API_KEY set)")
    return _singleton
