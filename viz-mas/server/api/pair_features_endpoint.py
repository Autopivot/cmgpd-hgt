"""Per-pair similarity features for V6's Rules-View bar chart.

For a (husband, wife) pair this endpoint returns four switchable metrics
the bar chart toggles between:

  * ``paternal_lineage_proximity`` — 1 / (1 + min_hop) along the
    undirected paternal kinship graph, capped at 4 hops. 0.5 = 1-hop
    (rare; would mean parent/child), 0.33 = 2-hop, 0.2 = 3-hop, 0.0 = no
    path within 4 hops or self.
  * ``shared_siblings`` — count of common ``FATHER_ID`` between h and
    w (a non-zero value implies they are paternal half- or full-siblings,
    which the V6 view flags as endogamy).
  * ``same_household_history`` — number of distinct panel YEARs in which
    h and w shared the same ``HOUSEHOLD_ID`` (any wave of DS0001).
  * ``same_banner`` — whether their *latest* DS0003 BANNER affiliation
    matches.

Implementation notes:
  - We reuse the cached parquet load done by ``server.data.kinship_loader``
    (FATHER_ID adjacency for the BFS) and ``server.mas.profiles``
    (banner_id, household_id-as-of-first-row); for the per-year
    ``same_household_history`` we maintain our own ``(PERSON_ID, YEAR) →
    HOUSEHOLD_ID`` map at module init since neither sibling module keeps
    the year axis.
  - All reads happen exactly once per process; per-pair results are
    LRU-cached on (h, w) raw ids.
"""
from __future__ import annotations

import functools
import logging
from collections import deque
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException

from ..data import kinship_loader as _kin
from ..mas import profiles as _profiles

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

ROOT = Path(__file__).resolve().parents[2]
CLEAN_PARQUET = ROOT.parent / "data" / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"

_MAX_HOPS = 4

# (raw PERSON_ID without "P") → set of (year, household_id) tuples.
_household_history: dict[str, set[tuple[int, str]]] = {}
_hh_lock = Lock()
_hh_loaded = False


def _strip_prefix(pid: str) -> str:
    pid = str(pid).strip()
    return pid[1:] if pid.startswith("P") else pid


def _is_missing(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in {"", "0", "nan", "None"} or s.lower() == "nan"


def _load_household_history() -> None:
    global _hh_loaded
    if _hh_loaded:
        return
    with _hh_lock:
        if _hh_loaded:
            return
        log.info("loading household-history axis from %s", CLEAN_PARQUET)
        try:
            import pandas as pd
            df = pd.read_parquet(
                CLEAN_PARQUET, columns=["PERSON_ID", "YEAR", "HOUSEHOLD_ID"],
            )
        except Exception as e:   # noqa: BLE001
            log.warning("Failed to load household history (%s); same_household_history will be 0", e)
            _hh_loaded = True
            return

        df = df.dropna(subset=["PERSON_ID", "YEAR", "HOUSEHOLD_ID"])
        # Coerce types defensively — mixed-dtype upstream cleans.
        for row in df.itertuples(index=False):
            pid = str(row.PERSON_ID)
            if _is_missing(pid):
                continue
            try:
                yr = int(row.YEAR)
            except (TypeError, ValueError):
                continue
            hh = str(row.HOUSEHOLD_ID)
            if _is_missing(hh):
                continue
            _household_history.setdefault(pid, set()).add((yr, hh))
        _hh_loaded = True
        log.info("household history ready: %d persons", len(_household_history))


def _paternal_proximity(h_raw: str, w_raw: str) -> float:
    """Bounded BFS on the undirected paternal graph (FATHER_ID and reverse).

    Returns 1 / (1 + min_hop) where min_hop ∈ {1, 2, 3, 4}; 0.0 if no
    path within ``_MAX_HOPS`` hops. Self (h == w) returns 0.0 because
    the spec says 1.0 is "impossible" and we never compute against self
    in real cohorts. Uses the kinship_loader's cached adjacency.
    """
    if h_raw == w_raw:
        return 0.0
    _kin._load()  # ensures father_of / father_to_children populated
    if h_raw not in _kin._sex and w_raw not in _kin._sex:
        return 0.0

    visited = {h_raw}
    frontier = deque([(h_raw, 0)])
    while frontier:
        node, depth = frontier.popleft()
        if depth >= _MAX_HOPS:
            continue
        # Up: father.
        f = _kin._father_of.get(node)
        if f and f not in visited:
            if f == w_raw:
                return 1.0 / (1 + depth + 1)
            visited.add(f)
            frontier.append((f, depth + 1))
        # Down: children via father link only (paternal graph).
        for child in _kin._father_to_children.get(node, ()):
            if child in visited:
                continue
            if child == w_raw:
                return 1.0 / (1 + depth + 1)
            visited.add(child)
            frontier.append((child, depth + 1))
    return 0.0


def _shared_siblings(h_raw: str, w_raw: str) -> int:
    """Number of common FATHER_IDs. With a single father per person this is
    0 or 1, but the contract is a count so the frontend can render it on
    the same axis as the other integer metric."""
    _kin._load()
    f_h = _kin._father_of.get(h_raw)
    f_w = _kin._father_of.get(w_raw)
    if f_h is None or f_w is None:
        return 0
    return 1 if f_h == f_w else 0


def _same_household_history(h_raw: str, w_raw: str) -> int:
    _load_household_history()
    h = _household_history.get(h_raw)
    w = _household_history.get(w_raw)
    if not h or not w:
        return 0
    # Distinct YEARs where both share the same HOUSEHOLD_ID. Build a
    # year→hh dict per side (last write wins; CMGPD has at most one
    # household per person per wave) and intersect.
    h_year_hh = {y: hh for (y, hh) in h}
    overlap = 0
    seen_years: set[int] = set()
    for (y, hh) in w:
        if y in seen_years:
            continue
        if h_year_hh.get(y) == hh:
            overlap += 1
            seen_years.add(y)
    return overlap


def _same_banner(h_raw: str, w_raw: str) -> bool:
    _profiles._load()
    h = _profiles._cache.get(h_raw)
    w = _profiles._cache.get(w_raw)
    if not h or not w:
        return False
    bh = h.get("banner_id")
    bw = w.get("banner_id")
    if bh is None or bw is None:
        return False
    return bh == bw


def _person_known(raw: str) -> bool:
    _kin._load()
    _profiles._load()
    return raw in _kin._sex or raw in _profiles._cache


@functools.lru_cache(maxsize=8192)
def _compute_pair_features(h_raw: str, w_raw: str) -> dict:
    return {
        "paternal_lineage_proximity": _paternal_proximity(h_raw, w_raw),
        "shared_siblings": _shared_siblings(h_raw, w_raw),
        "same_household_history": _same_household_history(h_raw, w_raw),
        "same_banner": _same_banner(h_raw, w_raw),
    }


@router.get("/pair-features/{husband_id}/{wife_id}")
def api_pair_features(husband_id: str, wife_id: str) -> dict:
    """Four-metric similarity backend for the V6 Rules-View bar chart.

    Returns 404 if either id is unknown to both the kinship adjacency
    and the profile cache. Otherwise returns the four metrics; the
    integer metrics are 0 and the boolean ``False`` when there is no
    overlap, never null.
    """
    h_raw = _strip_prefix(husband_id)
    w_raw = _strip_prefix(wife_id)
    if not _person_known(h_raw):
        raise HTTPException(404, f"husband id {husband_id} not in panel")
    if not _person_known(w_raw):
        raise HTTPException(404, f"wife id {wife_id} not in panel")
    return _compute_pair_features(h_raw, w_raw)
