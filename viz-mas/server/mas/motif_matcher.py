"""SEAL motif matcher for round-1 persona context.

The 6-round bilateral marriage negotiation pipeline passes a `motif` field
into the round-1 persona prompt. Frontend defines four exemplar motifs; this
module decides at runtime which (if any) apply to a given (husband, wife)
pair.

Motif IDs (kept in lock-step with `viz-mas/src/api/client.js`):
  - m1_father_brother  — direct patrilineal kin distance == 1
  - m2_uncle_in_law    — patrilineal kin distance in {2, 3}
  - m3_same_household  — same household, OR (same lineage AND patri ≤ 2)
  - m4_banner_endog    — same banner (and banner is known)

Output order is most-specific first: m1 > m2 > m3 > m4. m1 and m2 are
mutually exclusive by construction (different patri_path_count buckets).
"""
from __future__ import annotations

from typing import Optional

_M1 = "m1_father_brother"
_M2 = "m2_uncle_in_law"
_M3 = "m3_same_household"
_M4 = "m4_banner_endog"


def _ppc(pair_record: dict) -> Optional[int]:
    v = pair_record.get("patri_path_count")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def match_motifs(
    husband_profile: dict,
    wife_profile: dict,
    pair_record: dict,
) -> list[str]:
    """Return motif IDs that fit this pair, ordered most-specific first.

    See module docstring for the heuristic definitions. All inputs are
    treated defensively — missing or None fields simply suppress the
    relevant motif rather than raising.
    """
    motifs: list[str] = []
    ppc = _ppc(pair_record)

    # m1 / m2 — mutually exclusive patrilineal-distance buckets.
    if ppc == 1:
        motifs.append(_M1)
    elif ppc in (2, 3):
        motifs.append(_M2)

    # m3 — same household, or same lineage with short patrilineal path.
    hh_h = husband_profile.get("household_id")
    hh_w = wife_profile.get("household_id")
    same_household = hh_h is not None and hh_h == hh_w
    same_lineage = bool(pair_record.get("same_lineage"))
    near_lineage = same_lineage and ppc is not None and ppc <= 2
    if same_household or near_lineage:
        motifs.append(_M3)

    # m4 — banner endogamy (both bannered and equal).
    b_h = husband_profile.get("banner_id")
    b_w = wife_profile.get("banner_id")
    if b_h is not None and b_w is not None and b_h == b_w:
        motifs.append(_M4)

    return motifs
