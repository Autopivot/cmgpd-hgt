"""In-memory MAS state: hints injected by the user + accepted matches.

Also holds the per-husband asyncio primitives (advance Event + hint Queue)
used by the 6-round bilateral negotiation orchestrator
(`mas/negotiator_rounds.py`). Those primitives are created lazily on first
access, so HTTP handlers and the orchestrator both grab the same instance.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class MatchState:
    def __init__(self) -> None:
        # husband_id (str "Pxxx") → list of {text, role, ts}
        self._hints: dict[str, list[dict]] = defaultdict(list)
        # husband_id → {wife_id, score, source, note, ts, year, ablation}
        self._accepted: dict[str, dict] = {}
        # Append-only log of all accept events in arrival order. Drives the
        # V1 learning-curve plot (x = cumulative accept count over time).
        self._accept_log: list[dict] = []
        # 6-round orchestrator plumbing. Both keyed by husband_id and lazily
        # created on first access so handlers + orchestrator share instances.
        self._advance_events: dict[str, asyncio.Event] = {}
        self._hint_queues: dict[str, asyncio.Queue] = {}
        # husband_id → True while an orchestrator task is live. Lets /advance
        # respond 404 when the user hits it without a running session.
        self._active_sessions: dict[str, bool] = {}

    # ── Round-control plumbing (6-round orchestrator) ──────────────────
    def get_advance_event(self, husband_id: str) -> asyncio.Event:
        """Returns the asyncio.Event for this husband; creates if missing."""
        ev = self._advance_events.get(husband_id)
        if ev is None:
            ev = asyncio.Event()
            self._advance_events[husband_id] = ev
        return ev

    def get_hint_queue(self, husband_id: str) -> asyncio.Queue:
        """Returns the asyncio.Queue for this husband; creates if missing."""
        q = self._hint_queues.get(husband_id)
        if q is None:
            q = asyncio.Queue()
            self._hint_queues[husband_id] = q
        return q

    def reset_session(self, husband_id: str) -> None:
        """Clears advance event + drains hint queue for a fresh negotiation."""
        if husband_id in self._advance_events:
            self._advance_events[husband_id].clear()
        if husband_id in self._hint_queues:
            q = self._hint_queues[husband_id]
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break

    def mark_session_active(self, husband_id: str) -> None:
        self._active_sessions[husband_id] = True

    def mark_session_inactive(self, husband_id: str) -> None:
        self._active_sessions.pop(husband_id, None)

    def is_session_active(self, husband_id: str) -> bool:
        return bool(self._active_sessions.get(husband_id))

    # ── Hints ──────────────────────────────────────────────────────────
    def add_hint(self, husband_id: str, text: str, role: str = "all") -> None:
        self._hints[husband_id].append({
            "text": text, "role": role, "ts": time.time(),
        })

    def get_hints(self, husband_id: str, role: str | None = None) -> list[dict]:
        items = self._hints.get(husband_id, [])
        if role is None or role == "all":
            return list(items)
        return [h for h in items if h["role"] in ("all", role)]

    def list_hints(self, husband_id: str) -> list[dict]:
        return self.get_hints(husband_id)

    def count_hints(self, husband_id: str) -> int:
        return len(self._hints.get(husband_id, []))

    def reset_hints(self, husband_id: str) -> None:
        self._hints.pop(husband_id, None)

    def hints_as_string(self, husband_id: str, role: str | None = None) -> str:
        items = self.get_hints(husband_id, role)
        if not items:
            return ""
        lines = [f"  - [{h['role']}] {h['text']}" for h in items]
        return "User-supplied directives:\n" + "\n".join(lines)

    # ── Accepted matches ───────────────────────────────────────────────
    def commit_match(self, *, husband_id: str, wife_id: str,
                     score: float | None = None,
                     source: str = "negotiate",
                     note: str = "",
                     year: int | None = None,
                     ablation: str | None = None) -> dict:
        rec = {
            "husband_id": husband_id, "wife_id": wife_id,
            "score": float(score) if score is not None else None,
            "source": source, "note": note, "ts": time.time(),
            "year": int(year) if year is not None else None,
            "ablation": ablation,
        }
        self._accepted[husband_id] = rec
        self._accept_log.append(rec)
        return rec

    def get_accepted(self, husband_id: str) -> dict | None:
        return self._accepted.get(husband_id)

    def all_accepted(self) -> dict[str, dict]:
        return dict(self._accepted)

    def accept_log(self, year: int | None = None,
                   ablation: str | None = None) -> list[dict]:
        """Time-ordered acceptance events, optionally filtered by cohort."""
        out = self._accept_log
        if year is not None:
            out = [r for r in out if r.get("year") == int(year)]
        if ablation is not None:
            out = [r for r in out if r.get("ablation") == ablation]
        return list(out)

    def reset_log(self) -> None:
        """Clear the accept log AND the per-husband latest map.
        Used by /api/eval/reset to start a clean learning-curve session."""
        self._accept_log.clear()
        self._accepted.clear()

    def uncommit_match(self, husband_id: str) -> dict | None:
        """Reverse a prior accept. Removes the per-husband latest record AND
        every entry for this husband from the append-only log so the V1
        learning-curve recomputes correctly. Returns the last record removed,
        or None if there was nothing to undo.

        Used by POST /api/negotiate/{husband_id}/restore for cumulative-error
        recovery — the user can roll a bad accept back out of V2/V3/V4.
        """
        rec = self._accepted.pop(husband_id, None)
        # Strip every log entry for this husband so the recall-at-1 curve
        # doesn't keep counting an accept that has been rolled back.
        self._accept_log = [
            r for r in self._accept_log if r.get("husband_id") != husband_id
        ]
        return rec


state = MatchState()
