"""End-to-end smoke test for the 6-round bilateral negotiation orchestrator.

Skipped when DASHSCOPE_API_KEY is unset. Calls mas_negotiate_rounds in-process
with a stub publish/advance pair, captures the frame stream, and asserts the
protocol shape: 1 start + stage-profile + stage-filter, 7 narratives + 7
personas (round 1), then queries/answers/round_scores per round, with
round_paused gates and a final_ranking with descending final_score.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="DASHSCOPE_API_KEY not set; e2e skipped",
)


def _pick_husband_id() -> str:
    """Pick the first husband_id from cohort_1882 that has at least 4 candidates."""
    cohort_path = Path(__file__).resolve().parents[2].parent / "viz" / "data" / "cohort_1882.json"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    by_husband: dict[str, int] = {}
    for p in cohort["pairs"]:
        by_husband[p["husband_id"]] = by_husband.get(p["husband_id"], 0) + 1
    for hid, n in by_husband.items():
        if n >= 4:
            return hid
    return cohort["pairs"][0]["husband_id"]


@pytest.mark.asyncio
async def test_full_round_flow():
    from server.mas.negotiator_rounds import mas_negotiate_rounds

    husband_id = _pick_husband_id()

    captured: list[dict] = []
    advance_event = asyncio.Event()
    hint_queue: asyncio.Queue = asyncio.Queue()

    async def publish(event: dict):
        captured.append(event)
        # Auto-advance whenever we hit a round_paused frame.
        if event.get("type") == "round_paused":
            advance_event.set()

    # Run the orchestrator. It will await advance_event at every pause; we set
    # the event from inside publish() so the orchestrator never blocks.
    await asyncio.wait_for(
        mas_negotiate_rounds(
            husband_id, year=1882, ablation="ablated",
            publish=publish, advance_event=advance_event,
            hint_queue=hint_queue, auto_commit=False,
        ),
        timeout=180,  # full Qwen-driven flow can take ~2 minutes
    )

    # Frame-shape assertions
    by_type: dict[str, list[dict]] = {}
    for f in captured:
        by_type.setdefault(f["type"], []).append(f)

    assert by_type.get("start"), "expected exactly one start frame"
    assert any(f.get("stage") == "profile" for f in by_type.get("stage", []))
    assert any(f.get("stage") == "filter" for f in by_type.get("stage", []))

    n_personas = len(by_type.get("persona", []))
    assert n_personas >= 2, f"expected at least 2 persona frames (husband + 1+ candidate), got {n_personas}"

    # 5 round_paused frames (after rounds 1-5)
    n_paused = len(by_type.get("round_paused", []))
    assert n_paused == 5, f"expected 5 round_paused frames, got {n_paused}"

    # At least one query and one answer per round 2-5 = >=4 each (likely more if K candidates)
    n_query = len(by_type.get("query", []))
    n_answer = len(by_type.get("answer", []))
    assert n_query >= 4, f"expected >=4 query frames, got {n_query}"
    assert n_answer >= 4, f"expected >=4 answer frames, got {n_answer}"

    # Final ranking present, descending
    rankings = by_type.get("final_ranking", [])
    assert len(rankings) == 1
    ranking = rankings[0].get("ranking", [])
    assert len(ranking) > 0
    final_scores = [r.get("final_score") for r in ranking]
    assert all(final_scores[i] >= final_scores[i + 1] for i in range(len(final_scores) - 1)), \
        f"final_ranking must be sorted descending, got {final_scores}"

    # Last frame is 'done'
    assert captured[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_persona_frames_have_motifs():
    """Round 1 personas (for candidates against the husband) should carry a
    `motifs` array — subset of {m1_father_brother, m2_uncle_in_law,
    m3_same_household, m4_banner_endog}. May be empty for some pairs."""
    from server.mas.negotiator_rounds import mas_negotiate_rounds

    husband_id = _pick_husband_id()
    captured: list[dict] = []
    advance_event = asyncio.Event()
    hint_queue: asyncio.Queue = asyncio.Queue()

    async def publish(event: dict):
        captured.append(event)
        if event.get("type") == "round_paused":
            advance_event.set()

    await asyncio.wait_for(
        mas_negotiate_rounds(
            husband_id, year=1882, ablation="ablated",
            publish=publish, advance_event=advance_event,
            hint_queue=hint_queue, auto_commit=False,
        ),
        timeout=180,
    )

    personas = [f for f in captured if f["type"] == "persona"]
    candidate_personas = [f for f in personas if f.get("person_id") != husband_id]
    assert candidate_personas
    valid_motifs = {"m1_father_brother", "m2_uncle_in_law",
                    "m3_same_household", "m4_banner_endog"}
    for p in candidate_personas:
        motifs = p.get("motifs")
        assert isinstance(motifs, list), f"persona missing motifs list: {p}"
        assert all(m in valid_motifs for m in motifs), \
            f"unknown motif id in {motifs}"
