"""Unit tests for ``GET /api/narrative/{person_id}``.

These tests do NOT touch the real DS0003 loader. We monkey-patch the three
functions that ``server.main`` imported at module level
(``load_events``, ``load_income``, ``get_birth_year``) so the endpoint runs
against fixture data only.

Coverage:
  * Response shape and types match the contract.
  * The ``year`` query param is forwarded to the loader as ``end_year``.
  * Birth-year fallback: when DS0003 has no birth, ``start = year - 80``.
  * 404 when both events and income are empty.
  * PERSON_ID normalisation: "12345" → "P12345" in the response body.
  * Pre-prefixed "P12345" passes through unchanged.
  * ``year`` query-param bounds (FastAPI rejects out-of-range values).
"""
from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_client(monkeypatch, *, events, income, birth):
    """Build a TestClient with the loader monkey-patched.

    ``events`` and ``income`` are either lists (returned verbatim regardless
    of args) or callables ``(person_id, start, end) -> list``.
    """
    from server import main as srv

    calls: dict[str, list] = {"events": [], "income": [], "birth": []}

    def _events(person_id, start, end):
        calls["events"].append((person_id, start, end))
        return events(person_id, start, end) if callable(events) else events

    def _income(person_id, start, end):
        calls["income"].append((person_id, start, end))
        return income(person_id, start, end) if callable(income) else income

    def _birth(person_id):
        calls["birth"].append(person_id)
        return birth(person_id) if callable(birth) else birth

    monkeypatch.setattr(srv, "load_events", _events)
    monkeypatch.setattr(srv, "load_income", _income)
    monkeypatch.setattr(srv, "get_birth_year", _birth)
    return TestClient(srv.app), calls


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------
def test_narrative_returns_full_payload(monkeypatch):
    events_fx = [
        {"year": 1860, "event_1": "Birth", "event_2": None},
        {"year": 1872, "event_1": "Returned after absconding", "event_2": None},
        {"year": 1882, "event_1": "In-Marriage", "event_2": None},
    ]
    income_fx = [
        {"year": 1865, "income": 0.5, "level": "mid"},
        {"year": 1880, "income": 1.2, "level": "high"},
    ]
    client, _ = _build_client(monkeypatch, events=events_fx, income=income_fx, birth=1860)

    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200
    body = resp.json()
    assert body["person_id"] == "P12345"
    assert body["birth_year"] == 1860
    assert body["events"] == events_fx
    assert body["income"] == income_fx
    assert isinstance(body["events"], list)
    assert isinstance(body["income"], list)


def test_narrative_passes_year_through_to_loader_as_end_year(monkeypatch):
    """The endpoint forwards ``year`` to the loader as the upper-bound arg."""
    client, calls = _build_client(
        monkeypatch,
        events=[{"year": 1865, "event_1": "Birth", "event_2": None}],
        income=[],
        birth=1860,
    )
    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200

    # Both loaders called once, with end_year = 1882 and start = birth (1860).
    assert calls["events"] == [("12345", 1860, 1882)]
    assert calls["income"] == [("12345", 1860, 1882)]
    assert calls["birth"] == ["12345"]


def test_narrative_birth_unknown_uses_year_minus_80(monkeypatch):
    """When DS0003 has no birth year, start defaults to year - 80."""
    client, calls = _build_client(
        monkeypatch,
        events=[{"year": 1850, "event_1": "Death", "event_2": None}],
        income=[],
        birth=None,
    )
    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200
    body = resp.json()
    assert body["birth_year"] is None
    # start = 1882 - 80 = 1802
    assert calls["events"] == [("12345", 1802, 1882)]
    assert calls["income"] == [("12345", 1802, 1882)]


# ---------------------------------------------------------------------------
# 404 when nothing to show
# ---------------------------------------------------------------------------
def test_narrative_404_when_loader_returns_empty(monkeypatch):
    client, _ = _build_client(monkeypatch, events=[], income=[], birth=None)
    resp = client.get("/api/narrative/99999?year=1882")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "person not found"}


def test_narrative_200_with_only_events(monkeypatch):
    """Events alone are enough to keep the response 200."""
    client, _ = _build_client(
        monkeypatch,
        events=[{"year": 1860, "event_1": "Birth", "event_2": None}],
        income=[],
        birth=1860,
    )
    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] != []
    assert body["income"] == []


def test_narrative_200_with_only_income(monkeypatch):
    """Income alone is also enough for a 200."""
    client, _ = _build_client(
        monkeypatch,
        events=[],
        income=[{"year": 1865, "income": 0.5, "level": "mid"}],
        birth=None,
    )
    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert body["income"] != []


# ---------------------------------------------------------------------------
# PERSON_ID normalisation
# ---------------------------------------------------------------------------
def test_narrative_normalises_bare_id_to_p_prefix(monkeypatch):
    client, _ = _build_client(
        monkeypatch,
        events=[{"year": 1860, "event_1": "Birth", "event_2": None}],
        income=[],
        birth=1860,
    )
    resp = client.get("/api/narrative/12345?year=1882")
    assert resp.status_code == 200
    assert resp.json()["person_id"] == "P12345"


def test_narrative_preserves_existing_p_prefix(monkeypatch):
    client, calls = _build_client(
        monkeypatch,
        events=[{"year": 1860, "event_1": "Birth", "event_2": None}],
        income=[],
        birth=1860,
    )
    resp = client.get("/api/narrative/P12345?year=1882")
    assert resp.status_code == 200
    body = resp.json()
    # Response keeps the prefix once, doesn't double-prefix.
    assert body["person_id"] == "P12345"
    # The loader is invoked with whatever the client sent — the contract
    # says the loader must tolerate both forms.
    assert calls["events"][0][0] == "P12345"


# ---------------------------------------------------------------------------
# Query param validation
# ---------------------------------------------------------------------------
def test_narrative_year_query_param_required(monkeypatch):
    client, _ = _build_client(monkeypatch, events=[], income=[], birth=None)
    resp = client.get("/api/narrative/12345")
    # Missing required query param → 422 Unprocessable Entity.
    assert resp.status_code == 422


def test_narrative_year_out_of_range_rejected(monkeypatch):
    client, _ = _build_client(monkeypatch, events=[], income=[], birth=None)
    # The endpoint declares 1700 <= year <= 2000.
    too_low = client.get("/api/narrative/12345?year=1600")
    too_high = client.get("/api/narrative/12345?year=2100")
    assert too_low.status_code == 422
    assert too_high.status_code == 422
