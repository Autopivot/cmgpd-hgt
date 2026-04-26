"""In-memory MAS state: hints injected by the user + accepted matches."""
from __future__ import annotations

import time
from collections import defaultdict


class MatchState:
    def __init__(self) -> None:
        # husband_id (str "Pxxx") → list of {text, role, ts}
        self._hints: dict[str, list[dict]] = defaultdict(list)
        # husband_id → {wife_id, score, source, note, ts}
        self._accepted: dict[str, dict] = {}

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
                     note: str = "") -> dict:
        rec = {
            "husband_id": husband_id, "wife_id": wife_id,
            "score": float(score) if score is not None else None,
            "source": source, "note": note, "ts": time.time(),
        }
        self._accepted[husband_id] = rec
        return rec

    def get_accepted(self, husband_id: str) -> dict | None:
        return self._accepted.get(husband_id)

    def all_accepted(self) -> dict[str, dict]:
        return dict(self._accepted)


state = MatchState()
