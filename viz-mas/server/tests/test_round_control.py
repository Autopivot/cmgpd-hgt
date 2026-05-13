"""Endpoint tests for the 6-round negotiation round-control surface.

Covers:
  * POST /api/negotiate/{husband_id}        — kicks off background task
  * POST /api/negotiate/{husband_id}/advance — 404 if no session, otherwise sets the Event
  * POST /api/negotiate/{husband_id}/hint    — body lands in the per-husband Queue
                                                with role + round preserved

The real orchestrator (`mas_negotiate_rounds`) is monkey-patched with an
async stub that:
  - awaits the per-husband advance Event
  - records every published frame
  - drains the hint Queue and stashes the items for assertion

Cross-loop synchronization between TestClient's anyio portal and the test
function uses a stdlib ``threading.Event`` (the advisor flagged that
``asyncio.Event`` does not work across event loops).
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from server import main as server_main
from server.mas.state import state as mas_state


def _wait_for_active_sync(husband_id: str, timeout: float = 2.0) -> None:
    """Block (synchronously) until the orchestrator marks itself active."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mas_state.is_session_active(husband_id):
            return
        time.sleep(0.01)
    raise RuntimeError(f"orchestrator never marked {husband_id} active")


def _wait_for_inactive_sync(husband_id: str, timeout: float = 2.0) -> None:
    """Block until the orchestrator marks itself inactive (= done)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not mas_state.is_session_active(husband_id):
            return
        time.sleep(0.01)
    raise RuntimeError(f"orchestrator never finished for {husband_id}")


def _install_stub(monkeypatch, captured: dict[str, Any]) -> threading.Event:
    """Install an orchestrator stub that:
      * records every published frame and the input args
      * blocks on advance_event.wait()
      * drains hint_queue after the advance fires
    Returns a ``threading.Event`` set when the stub finishes — safe to wait
    on from outside TestClient's loop.
    """
    finished = threading.Event()
    captured.setdefault("published", [])
    captured.setdefault("hints", [])

    async def _stub(
        husband_id, year, ablation, publish, advance_event, hint_queue,
        auto_commit=False,
    ):
        captured["husband_id"] = husband_id
        captured["year"] = year
        captured["ablation"] = ablation
        captured["auto_commit"] = auto_commit
        await publish({"type": "round_paused", "round": 1})
        captured["published"].append({"type": "round_paused", "round": 1})
        await advance_event.wait()
        advance_event.clear()
        while not hint_queue.empty():
            try:
                captured["hints"].append(hint_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        await publish({"type": "done"})
        captured["published"].append({"type": "done"})
        finished.set()

    monkeypatch.setattr(server_main, "mas_negotiate_rounds", _stub)
    return finished


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test starts from a clean MAS state."""
    mas_state.reset_log()
    mas_state._hints.clear()
    mas_state._advance_events.clear()
    mas_state._hint_queues.clear()
    mas_state._active_sessions.clear()
    yield


@pytest.fixture
def client():
    return TestClient(server_main.app)


# ── tests ────────────────────────────────────────────────────────────────
def test_negotiate_kicks_off_background_task(monkeypatch, client):
    captured: dict[str, Any] = {}
    finished = _install_stub(monkeypatch, captured)

    r = client.post(
        "/api/negotiate/12345",
        json={"year": 1882, "ablation": "ablated", "auto_commit": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "started"
    assert body["husband_id"] == "12345"
    assert body["year"] == 1882
    assert body["ablation"] == "ablated"

    # Background task should be running and parked on advance_event.wait().
    _wait_for_active_sync("12345")
    assert mas_state.is_session_active("12345")
    assert captured["husband_id"] == "12345"
    assert captured["year"] == 1882
    assert captured["ablation"] == "ablated"
    assert captured["auto_commit"] is False

    # Unblock so the stub finishes (avoids leaking tasks across tests).
    client.post("/api/negotiate/12345/advance")
    assert finished.wait(2.0), "stub never finished after /advance"


def test_advance_returns_404_when_no_session(client):
    r = client.post("/api/negotiate/no-such-husband/advance")
    assert r.status_code == 404


def test_advance_triggers_event_for_active_session(monkeypatch, client):
    captured: dict[str, Any] = {}
    finished = _install_stub(monkeypatch, captured)

    r = client.post("/api/negotiate/12345", json={"year": 1882})
    assert r.status_code == 200

    _wait_for_active_sync("12345")

    r2 = client.post("/api/negotiate/12345/advance")
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok"}

    assert finished.wait(2.0), "orchestrator never observed the advance signal"
    assert {"type": "done"} in captured["published"]
    # Session flag flipped back to inactive.
    _wait_for_inactive_sync("12345")
    assert not mas_state.is_session_active("12345")


def test_hint_pushes_into_queue_with_role_and_round(monkeypatch, client):
    captured: dict[str, Any] = {}
    finished = _install_stub(monkeypatch, captured)

    r = client.post("/api/negotiate/12345", json={"year": 1882})
    assert r.status_code == 200
    _wait_for_active_sync("12345")

    r1 = client.post(
        "/api/negotiate/12345/hint",
        json={"text": "@everyone be honest", "role": "all", "round": 2},
    )
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    r2 = client.post(
        "/api/negotiate/12345/hint",
        json={"text": "lean toward c-99", "role": "c-12345", "round": 4},
    )
    assert r2.status_code == 200

    # Advance so the stub drains the queue.
    client.post("/api/negotiate/12345/advance")
    assert finished.wait(2.0), "stub never finished"

    assert captured["hints"] == [
        {"text": "@everyone be honest", "role": "all", "round": 2},
        {"text": "lean toward c-99", "role": "c-12345", "round": 4},
    ]


def test_hint_default_role_is_all_and_round_optional(monkeypatch, client):
    captured: dict[str, Any] = {}
    finished = _install_stub(monkeypatch, captured)
    client.post("/api/negotiate/h1", json={"year": 1882})
    _wait_for_active_sync("h1")

    r = client.post(
        "/api/negotiate/h1/hint",
        json={"text": "no preference"},
    )
    assert r.status_code == 200

    client.post("/api/negotiate/h1/advance")
    assert finished.wait(2.0)

    assert captured["hints"] == [
        {"text": "no preference", "role": "all", "round": None},
    ]
