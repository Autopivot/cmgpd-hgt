"""In-memory MAS state: hints injected by the user + accepted matches."""
from __future__ import annotations

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


state = MatchState()
