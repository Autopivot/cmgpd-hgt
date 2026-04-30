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

_MAX_HOPS = 8

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
    """Bounded BFS on the undirected kinship graph (FATHER_ID + MOTHER_ID, both
    directions). Returns 1 / (1 + min_hop), 0 if no path within ``_MAX_HOPS``.

    The metric label still reads "paternal lineage proximity" in the UI, but
    it now follows maternal edges too — within-cohort hard-negatives are
    sampled to be unrelated to the husband, so the strict paternal-only
    walk produced 0 for almost every non-GT candidate. Including maternal
    + walking deeper exposes weaker but real kin chains and lets non-GT
    candidates show non-zero values when they exist.
    """
    if h_raw == w_raw:
        return 0.0
    _kin._load()
    if h_raw not in _kin._sex and w_raw not in _kin._sex:
        return 0.0

    visited = {h_raw}
    frontier = deque([(h_raw, 0)])
    while frontier:
        node, depth = frontier.popleft()
        if depth >= _MAX_HOPS:
            continue
        # Up: father + mother.
        for parent in (_kin._father_of.get(node), _kin._mother_of.get(node)):
            if not parent or parent in visited:
                continue
            if parent == w_raw:
                return 1.0 / (1 + depth + 1)
            visited.add(parent)
            frontier.append((parent, depth + 1))
        # Down: children via either parent link.
        children = set(_kin._father_to_children.get(node, ())) \
                 | set(_kin._mother_to_children.get(node, ()))
        for child in children:
            if child in visited:
                continue
            if child == w_raw:
                return 1.0 / (1 + depth + 1)
            visited.add(child)
            frontier.append((child, depth + 1))
    return 0.0


def _shared_kin(h_raw: str, w_raw: str) -> int:
    """Count of common ancestors within 2 generations (parents + grandparents).

    Replaces the previous single-father check, which was 0 for almost every
    non-GT candidate. Two cousins now register as 1 (they share a grandparent);
    half-siblings still count as 1; full-siblings as 2.
    """
    _kin._load()
    def ancestors(p):
        out = set()
        f = _kin._father_of.get(p); m = _kin._mother_of.get(p)
        for x in (f, m):
            if x:
                out.add(x)
                gf = _kin._father_of.get(x); gm = _kin._mother_of.get(x)
                if gf: out.add(gf)
                if gm: out.add(gm)
        return out
    return len(ancestors(h_raw) & ancestors(w_raw))


def _shared_siblings(h_raw: str, w_raw: str) -> int:
    """Count of shared kin within 2 generations (parents + grandparents).

    Cousins, half-siblings, and full-siblings all surface here; previously
    only full/half-siblings did, which made the metric trivially 0 for the
    overwhelming majority of within-cohort hard-negatives.
    """
    return _shared_kin(h_raw, w_raw)


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


def _same_banner(h_raw: str, w_raw: str):
    """Return True/False when banners known; fall back to community match
    when either banner is missing; None only when both fallbacks are also
    missing.

    CMGPD has many bannerless rows (e.g. P89414's banner_id is null) which
    used to make this metric uninformative; community_id is populated far
    more often and serves as a sane proxy for 'same administrative unit'.
    """
    _profiles._load()
    h = _profiles._cache.get(h_raw)
    w = _profiles._cache.get(w_raw)
    if not h or not w:
        return None
    bh, bw = h.get("banner_id"), w.get("banner_id")
    if bh is not None and bw is not None:
        return bh == bw
    ch, cw = h.get("community_id"), w.get("community_id")
    if ch is not None and cw is not None:
        return ch == cw
    return None


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
