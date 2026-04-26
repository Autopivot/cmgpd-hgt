"""Unit tests for `server.mas.motif_matcher.match_motifs`.

Covers each motif individually, ordering of combinations, defensive None
handling, and one integration-style test that pulls a real pair from
`viz/data/cohort_1882.json`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.mas.motif_matcher import match_motifs

# Resolve the cohort fixture relative to this file so the test still works
# regardless of pytest's invocation cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COHORT_1882 = _REPO_ROOT / "viz" / "data" / "cohort_1882.json"


@pytest.fixture(scope="module")
def cohort_1882() -> dict:
    if not _COHORT_1882.exists():
        pytest.skip("cohort_1882.json not available")
    return json.loads(_COHORT_1882.read_text(encoding="utf-8"))


def _profile(**overrides) -> dict:
    base = {
        "id": "P0",
        "sex": "?",
        "birth_year": None,
        "banner_id": None,
        "community_id": None,
        "household_id": None,
    }
    base.update(overrides)
    return base


# --- single-motif cases -----------------------------------------------------


def test_m1_father_brother_matches_when_patri_path_count_is_one():
    h = _profile(id="P1", banner_id=None, household_id="H1")
    w = _profile(id="P2", banner_id=None, household_id="H2")
    pair = {"patri_path_count": 1, "same_lineage": False}
    assert match_motifs(h, w, pair) == ["m1_father_brother"]


def test_m2_uncle_in_law_matches_for_ppc_two_or_three():
    h = _profile(id="P1")
    w = _profile(id="P2")
    for ppc in (2, 3):
        pair = {"patri_path_count": ppc, "same_lineage": False}
        # ppc<=2 + same_lineage=False means m3 should NOT fire here.
        assert match_motifs(h, w, pair) == ["m2_uncle_in_law"], f"ppc={ppc}"


def test_m3_same_household_matches_on_household_equality():
    h = _profile(id="P1", household_id="H_SAME")
    w = _profile(id="P2", household_id="H_SAME")
    pair = {"patri_path_count": 9, "same_lineage": False}
    assert match_motifs(h, w, pair) == ["m3_same_household"]


def test_m3_via_same_lineage_short_patri_co_fires_with_m2():
    # m3-via-lineage requires ppc<=2, which always also triggers m1 or m2.
    # Test the m2 + m3 combo (ppc=2) here.
    h = _profile(id="P1", household_id="H1")
    w = _profile(id="P2", household_id="H2")
    pair = {"patri_path_count": 2, "same_lineage": True}
    assert match_motifs(h, w, pair) == ["m2_uncle_in_law", "m3_same_household"]


def test_m4_banner_endog_matches_when_banners_equal():
    h = _profile(id="P1", banner_id=5)
    w = _profile(id="P2", banner_id=5)
    pair = {"patri_path_count": 99, "same_lineage": False}
    assert match_motifs(h, w, pair) == ["m4_banner_endog"]


# --- combinations / ordering -----------------------------------------------


def test_m1_and_m4_ordered_correctly():
    h = _profile(id="P1", banner_id=3, household_id="H1")
    w = _profile(id="P2", banner_id=3, household_id="H2")
    pair = {"patri_path_count": 1, "same_lineage": False}
    assert match_motifs(h, w, pair) == ["m1_father_brother", "m4_banner_endog"]


def test_all_three_compatible_motifs_ordered():
    # m1 + m3 (via same_lineage AND ppc<=2) + m4
    h = _profile(id="P1", banner_id=7, household_id="H1")
    w = _profile(id="P2", banner_id=7, household_id="H2")
    pair = {"patri_path_count": 1, "same_lineage": True}
    assert match_motifs(h, w, pair) == [
        "m1_father_brother",
        "m3_same_household",
        "m4_banner_endog",
    ]


def test_m1_and_m2_are_mutually_exclusive():
    h = _profile(id="P1")
    w = _profile(id="P2")
    for ppc in (1, 2, 3):
        out = match_motifs(h, w, {"patri_path_count": ppc, "same_lineage": False})
        has_m1 = "m1_father_brother" in out
        has_m2 = "m2_uncle_in_law" in out
        assert not (has_m1 and has_m2), f"ppc={ppc} produced both m1 and m2"


# --- defensive / no-match ---------------------------------------------------


def test_no_match_returns_empty_list():
    h = _profile(id="P1")
    w = _profile(id="P2")
    pair = {"patri_path_count": 9, "same_lineage": False}
    assert match_motifs(h, w, pair) == []


def test_none_banner_does_not_match_m4_even_when_both_none():
    h = _profile(id="P1", banner_id=None)
    w = _profile(id="P2", banner_id=None)
    pair = {"patri_path_count": 99, "same_lineage": False}
    assert "m4_banner_endog" not in match_motifs(h, w, pair)


def test_none_household_does_not_match_m3_even_when_both_none():
    h = _profile(id="P1", household_id=None)
    w = _profile(id="P2", household_id=None)
    pair = {"patri_path_count": 99, "same_lineage": False}
    assert match_motifs(h, w, pair) == []


def test_missing_patri_path_count_is_safe():
    h = _profile(id="P1", banner_id=4)
    w = _profile(id="P2", banner_id=4)
    # No patri_path_count key, no same_lineage; only m4 should fire.
    pair = {}
    assert match_motifs(h, w, pair) == ["m4_banner_endog"]


def test_same_lineage_with_long_patri_path_does_not_fire_m3():
    # same_lineage=True, but ppc>2 → m3 must NOT fire.
    h = _profile(id="P1", household_id="H1")
    w = _profile(id="P2", household_id="H2")
    pair = {"patri_path_count": 9, "same_lineage": True}
    assert match_motifs(h, w, pair) == []


# --- integration with real cohort data --------------------------------------


def test_real_cohort_pair_with_ppc_one_fires_m1(cohort_1882):
    sample = next(p for p in cohort_1882["pairs"] if p.get("patri_path_count") == 1)
    # Minimal-fallback profiles so the test does not depend on the parquet
    # feature store being present in CI.
    h = _profile(id=sample["husband_id"])
    w = _profile(id=sample["wife_id"])
    motifs = match_motifs(h, w, sample)
    assert "m1_father_brother" in motifs
    assert "m2_uncle_in_law" not in motifs


def test_real_cohort_banner_endog_when_profiles_share_banner(cohort_1882):
    sample = cohort_1882["pairs"][0]
    # Force a shared, known banner so m4 fires regardless of parquet state.
    h = _profile(id=sample["husband_id"], banner_id=1)
    w = _profile(id=sample["wife_id"], banner_id=1)
    motifs = match_motifs(h, w, sample)
    assert "m4_banner_endog" in motifs
