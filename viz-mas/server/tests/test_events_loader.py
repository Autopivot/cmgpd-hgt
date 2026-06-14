"""Unit tests for `server.data.events_loader`.

These tests bypass the real DS0003 .rda by injecting a small synthetic
DataFrame into the module-level cache. We exercise:
  * label substitution (1→Death, 6→Birth, 7→In-Marriage)
  * missing-code (-99) handling
  * year window filtering
  * PERSON_ID normalisation ("P12345" vs "12345")
  * income bucketing (low/mid/high)
  * graceful empty return on unknown person
  * graceful empty return when DS0003 is unavailable
"""
from __future__ import annotations

import importlib

import pandas as pd
import pytest


# Always reload the module so cache state from one test does not leak into
# another. Using a fixture keeps the import path explicit for pytest.
@pytest.fixture
def loader(monkeypatch):
    from server.data import events_loader as mod
    importlib.reload(mod)

    df = pd.DataFrame(
        {
            "PERSON_ID": ["12345", "12345", "12345", "12345",
                          "67890", "67890",
                          "55555", "55555", "55555"],
            "YEAR":      [1820,    1825,    1830,    1835,
                          1820,    1830,
                          1820,    1825,    1830],
            # 1=Death, 6=Birth, 7=In-Marriage, -99=Missing.
            "EVENT_1":   [6,       7,       1,       -99,
                          6,       1,
                          6,       -99,     -99],
            "EVENT_2":   [-99,     -99,     -99,     -99,
                          -99,     -99,
                          -99,     7,       -99],
            "ESTIMATED_INCOME": [10.0,   50.0,   90.0,   None,
                                 5.0,    100.0,
                                 12.0,   55.0,   88.0],
        }
    )

    # Minimal label table mirrors DS0003 codebook entries exercised by tests.
    mod._event_labels = {
        "EVENT_1": {1: "Death", 6: "Birth", 7: "In-Marriage", -99: "Missing"},
        "EVENT_2": {1: "Death", 6: "Birth", 7: "In-Marriage", -99: "Missing"},
    }
    mod._missing_codes = {"EVENT_1": -99, "EVENT_2": -99}
    mod._df = mod._index_dataframe(df)
    mod._income_low, mod._income_high = mod._compute_income_quantiles(mod._df)
    mod._loaded = True
    return mod


def test_load_events_basic_labels(loader):
    rows = loader.load_events("12345", 1800, 1850)
    # Rows where both events are -99 are dropped (1835 row).
    assert [r["year"] for r in rows] == [1820, 1825, 1830]
    assert rows[0]["event_1"] == "Birth"
    assert rows[1]["event_1"] == "In-Marriage"
    assert rows[2]["event_1"] == "Death"
    # All event_2 cells in this person are missing → None.
    assert all(r["event_2"] is None for r in rows)


def test_load_events_handles_missing_code(loader):
    rows = loader.load_events("12345", 1834, 1836)
    # The only matching row is 1835 with both events == -99 → dropped.
    assert rows == []


def test_load_events_event_2_decoded(loader):
    rows = loader.load_events("55555", 1800, 1900)
    # Row 1825 has EVENT_2 == 7 → "In-Marriage". 1830 row both -99 → dropped.
    years = [r["year"] for r in rows]
    assert years == [1820, 1825]
    assert rows[1]["event_2"] == "In-Marriage"
    assert rows[1]["event_1"] is None


def test_load_events_year_window(loader):
    rows = loader.load_events("12345", 1825, 1830)
    assert [r["year"] for r in rows] == [1825, 1830]


def test_load_events_person_id_with_p_prefix(loader):
    bare = loader.load_events("12345", 1800, 1900)
    prefixed = loader.load_events("P12345", 1800, 1900)
    assert bare == prefixed
    assert len(bare) > 0


def test_load_events_unknown_person(loader):
    assert loader.load_events("99999", 1800, 1900) == []
    assert loader.load_events("P99999", 1800, 1900) == []


def test_load_events_sorted_ascending(loader):
    rows = loader.load_events("12345", 1800, 1900)
    years = [r["year"] for r in rows]
    assert years == sorted(years)


def test_load_income_buckets(loader):
    rows = loader.load_income("12345", 1800, 1900)
    # Income 10/50/90 across a global pool of {10,50,90,5,100,12,55,88}.
    # 33rd ≈ 12, 66th ≈ 75 → 10→low, 50→mid, 90→high.
    by_year = {r["year"]: r for r in rows}
    assert by_year[1820]["level"] == "low"
    assert by_year[1825]["level"] == "mid"
    assert by_year[1830]["level"] == "high"
    # Null-income row (1835) is dropped.
    assert 1835 not in by_year


def test_load_income_unknown_person(loader):
    assert loader.load_income("99999", 1800, 1900) == []


def test_load_income_year_window(loader):
    rows = loader.load_income("67890", 1825, 1900)
    assert [r["year"] for r in rows] == [1830]
    assert rows[0]["income"] == 100.0


def test_get_birth_year(loader):
    # Person 12345 has Birth (EVENT_1==6) at 1820.
    assert loader.get_birth_year("12345") == 1820
    assert loader.get_birth_year("P12345") == 1820
    # Person 67890 also has Birth in 1820.
    assert loader.get_birth_year("67890") == 1820


def test_get_birth_year_no_match(loader, monkeypatch):
    # Inject a person with no Birth events at all.
    df = pd.DataFrame(
        {
            "PERSON_ID": ["77777", "77777"],
            "YEAR":      [1840,    1845],
            "EVENT_1":   [1,       -99],
            "EVENT_2":   [-99,     7],
            "ESTIMATED_INCOME": [None, None],
        }
    )
    loader._df = loader._index_dataframe(df)
    assert loader.get_birth_year("77777") is None


def test_get_birth_year_unknown_person(loader):
    assert loader.get_birth_year("99999") is None


def test_safe_empty_when_dataset_missing(monkeypatch):
    """If the DS0003 frame fails to load, all functions return safe empties."""
    from server.data import events_loader as mod
    importlib.reload(mod)
    # Simulate a fully missing dataset: cache populated with no rows.
    mod._df = None
    mod._event_labels = {}
    mod._missing_codes = {}
    mod._income_low = None
    mod._income_high = None
    mod._loaded = True

    assert mod.load_events("12345", 1800, 1900) == []
    assert mod.load_income("12345", 1800, 1900) == []
    assert mod.get_birth_year("12345") is None
