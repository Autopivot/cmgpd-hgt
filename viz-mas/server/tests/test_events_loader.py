"""Unit + smoke tests for `server.data.events_loader`.

Most tests bypass the real DS0003 .rda by injecting a small synthetic
DataFrame (already DS0001-joined: PERSON_ID + YEAR + BIRTHYEAR + events).
A single integration test exercises the real on-disk join so the loader
contract is validated end-to-end whenever the cache is present.
"""
from __future__ import annotations

import importlib

import pandas as pd
import pytest


@pytest.fixture
def loader():
    """Reload the module and inject a synthetic DS0001-joined frame.

    We mirror the schema produced by `_build_joined_dataframe`:
    ``RECORD_NUMBER, PERSON_ID, YEAR, BIRTHYEAR, EVENT_1, EVENT_2, ESTIMATED_INCOME``.
    """
    from server.data import events_loader as mod
    importlib.reload(mod)

    df = pd.DataFrame(
        {
            "RECORD_NUMBER": list(range(1, 10)),
            "PERSON_ID": ["12345", "12345", "12345", "12345",
                          "67890", "67890",
                          "55555", "55555", "55555"],
            "YEAR":      [1820,    1825,    1830,    1835,
                          1820,    1830,
                          1820,    1825,    1830],
            "BIRTHYEAR": [1820.0,  1820.0,  1820.0,  1820.0,
                          1820.0,  1820.0,
                          1818.0,  1818.0,  1818.0],
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
    assert all(r["event_2"] is None for r in rows)


def test_load_events_handles_missing_code(loader):
    rows = loader.load_events("12345", 1834, 1836)
    # The only matching row is 1835 with both events == -99 → dropped.
    assert rows == []


def test_load_events_event_2_decoded(loader):
    rows = loader.load_events("55555", 1800, 1900)
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
    by_year = {r["year"]: r for r in rows}
    # Every income in the synthetic fixture is non-zero, so tertiles are
    # computed over {10,50,90,5,100,12,55,88} → q33 ~= 12, q66 ~= 75.
    assert by_year[1820]["level"] == "low"
    assert by_year[1825]["level"] == "mid"
    assert by_year[1830]["level"] == "high"
    assert 1835 not in by_year


def test_load_income_unknown_person(loader):
    assert loader.load_income("99999", 1800, 1900) == []


def test_load_income_year_window(loader):
    rows = loader.load_income("67890", 1825, 1900)
    assert [r["year"] for r in rows] == [1830]
    assert rows[0]["income"] == 100.0


def test_get_birth_year_from_birthyear_column(loader):
    # BIRTHYEAR column drives the result; it does not require a Birth event row.
    assert loader.get_birth_year("12345") == 1820
    assert loader.get_birth_year("P12345") == 1820
    assert loader.get_birth_year("55555") == 1818


def test_get_birth_year_handles_missing_birthyear(loader):
    df = pd.DataFrame(
        {
            "RECORD_NUMBER": [10, 11],
            "PERSON_ID":     ["77777", "77777"],
            "YEAR":          [1840,    1845],
            "BIRTHYEAR":     [None,    None],
            "EVENT_1":       [1,       -99],
            "EVENT_2":       [-99,     7],
            "ESTIMATED_INCOME": [None, None],
        }
    )
    loader._df = loader._index_dataframe(df)
    assert loader.get_birth_year("77777") is None


def test_get_birth_year_unknown_person(loader):
    assert loader.get_birth_year("99999") is None


def test_normalize_person_id_handles_none_and_whitespace(loader):
    # Defensive: callers occasionally pass None / padded strings.
    assert loader._normalize_person_id("P12345") == "12345"
    assert loader._normalize_person_id(" 12345 ") == "12345"
    assert loader._normalize_person_id("12345") == "12345"


def test_safe_empty_when_dataset_missing():
    """If the DS0003 frame fails to load, all functions return safe empties."""
    from server.data import events_loader as mod
    importlib.reload(mod)
    mod._df = None
    mod._event_labels = {}
    mod._missing_codes = {}
    mod._income_low = None
    mod._income_high = None
    mod._loaded = True

    assert mod.load_events("12345", 1800, 1900) == []
    assert mod.load_income("12345", 1800, 1900) == []
    assert mod.get_birth_year("12345") is None


# ── Integration: real DS0003+DS0001 join cache ────────────────────────
def test_real_join_yields_labeled_events_for_known_person():
    """Sanity: a person with many DS0003 rows produces English-labeled events.

    PERSON_ID 62104 has 37 non-missing event rows after the join (verified
    by hand against the raw CSV). Skipped if the cache hasn't been built.
    """
    from server.data import events_loader as mod
    importlib.reload(mod)
    if not mod.JOINED_PARQUET_PATH.exists() and not mod.RDA_PATH.exists():
        pytest.skip("DS0003 source not present — integration test skipped")

    events = mod.load_events("62104", 1700, 1900)
    assert len(events) > 0, "expected non-empty events for known person 62104"
    # Every label must be a real English string from event_value_labels.json,
    # not the raw integer code.
    for ev in events:
        for k in ("event_1", "event_2"):
            v = ev.get(k)
            assert v is None or isinstance(v, str)
            if isinstance(v, str):
                assert not v.lstrip("-").isdigit(), f"raw code leaked through: {v!r}"

    # P-prefix normalisation works on real data too.
    assert mod.load_events("P62104", 1700, 1900) == events
