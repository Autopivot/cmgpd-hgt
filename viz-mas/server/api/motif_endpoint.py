"""GET /api/motifs/{husband_id}/{wife_id}?year=N — live motif detection.

Bridges the viz-mas server to the seal motif-detection package living in
the sibling cmgpd-hgt repo. At import time we:

  1. Append `D:/projects/cmgpd-hgt` to sys.path so `seal` is importable.
  2. Load the motif catalog (catalog.json) so the endpoint can join the
     live `present`/`supporting_path_count` results against the catalog's
     curated English explanations and historical meanings.
  3. Load the HGT pipeline graph (`graph.pt` — HeteroData + id_maps) once.

Any of those three failing flips a module-level flag; the route then
returns HTTP 503 with a structured error so the frontend can fall back
to its static motif list cleanly.

Each query runs `seal.scripts.motif_detect.detect_for_query(graph, h_idx,
w_idx, year, catalog)`. Results are filtered to motifs with `present=true`
and merged with catalog metadata (English name, explanation, historical
meaning, expected coverage). Wrapped in `lru_cache(maxsize=4096)` keyed by
(husband_id, wife_id, year) since detection is several-hundred-ms per call
and V6's UI re-fires it on every selection.

Person ids arrive prefixed ("P89414"); the graph's id_map keys are the
unprefixed string form ("89414"). We strip a leading "P" before lookup.
"""
from __future__ import annotations

import functools
import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ── Paths ────────────────────────────────────────────────────────────
_SEAL_REPO = Path("D:/projects/cmgpd-hgt")
_CATALOG_PATH = _SEAL_REPO / "seal" / "motifs" / "catalog.json"

# Make NEW/ importable so `src.config` resolves regardless of cwd.
_NEW_ROOT = Path(__file__).resolve().parents[3]
if str(_NEW_ROOT) not in sys.path:
    sys.path.insert(0, str(_NEW_ROOT))

# Make cmgpd-hgt importable for the `seal` package.
if str(_SEAL_REPO) not in sys.path:
    sys.path.append(str(_SEAL_REPO))

# ── Module-level state set up at import (or left None on failure) ─────
_graph = None
_id_map_person: dict | None = None
_catalog: dict | None = None
_detect_for_query = None
_unavailable_reason: str | None = None


def _load_resources() -> None:
    """Try to load seal + catalog + graph; on any failure, set
    `_unavailable_reason` so the route returns 503 with a useful message.
    """
    global _graph, _id_map_person, _catalog, _detect_for_query, _unavailable_reason

    # 1. seal package importability
    try:
        from seal.scripts.motif_detect import detect_for_query as _detect
    except Exception as exc:  # noqa: BLE001
        _unavailable_reason = f"cannot import seal.scripts.motif_detect: {exc!r}"
        logger.warning("motif_endpoint unavailable: %s", _unavailable_reason)
        return
    _detect_for_query = _detect

    # 2. catalog
    try:
        with _CATALOG_PATH.open(encoding="utf-8") as fh:
            _catalog = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        _unavailable_reason = f"cannot read catalog at {_CATALOG_PATH}: {exc!r}"
        logger.warning("motif_endpoint unavailable: %s", _unavailable_reason)
        return

    # 3. graph + id_maps from the HGT pipeline
    try:
        from src.config import GRAPH_CACHE_PATH
        import torch
        ck = torch.load(str(GRAPH_CACHE_PATH), weights_only=False)
        _graph = ck["data"]
        _id_map_person = ck["id_maps"]["person"]
    except Exception as exc:  # noqa: BLE001
        _unavailable_reason = f"cannot load graph.pt: {exc!r}"
        logger.warning("motif_endpoint unavailable: %s", _unavailable_reason)
        return

    logger.info(
        "motif_endpoint ready: %d persons, %d catalog motifs",
        int(_graph["person"].num_nodes), len(_catalog["motifs"]),
    )


_load_resources()


# ── Catalog lookup helpers ───────────────────────────────────────────
_CAT_INDEX: dict[str, dict] = (
    {m["id"]: m for m in _catalog["motifs"]} if _catalog else {}
)


def _strip_prefix(person_id: str) -> str:
    """Person ids in viz/MAS land carry a leading 'P' (e.g. 'P89414').
    The HGT id_map keys are unprefixed strings ('89414'). Normalise.
    """
    pid = str(person_id)
    return pid[1:] if pid.startswith("P") else pid


@functools.lru_cache(maxsize=4096)
def _detect_cached(husband_id: str, wife_id: str, year: int) -> dict:
    """Run detect_for_query and project to the response shape.

    Cache is keyed by the raw ids + year — the projected response is
    pure data, so caching it avoids re-running BFS on repeated UI clicks.
    """
    h_key = _strip_prefix(husband_id)
    w_key = _strip_prefix(wife_id)
    if h_key not in _id_map_person:
        raise HTTPException(404, f"husband_id {husband_id} not in graph id_map")
    if w_key not in _id_map_person:
        raise HTTPException(404, f"wife_id {wife_id} not in graph id_map")
    h_idx = int(_id_map_person[h_key])
    w_idx = int(_id_map_person[w_key])

    report = _detect_for_query(_graph, h_idx, w_idx, int(year), _catalog)

    motif_ids: list[str] = []
    details: list[dict] = []
    for m in report.get("motifs", []):
        if not m.get("present"):
            continue
        cat = _CAT_INDEX.get(m["id"], {})
        motif_ids.append(m["id"])
        details.append({
            "id": m["id"],
            "name_en": cat.get("name_en", m.get("name_zh", m["id"])),
            "explanation_en": cat.get("explanation_en", ""),
            "relations": list(m.get("relations", [])),
            "length": int(m.get("length", len(m.get("relations", [])))),
            "supporting_path_count": int(m.get("supporting_path_count", 0)),
            "historical_meaning": cat.get("historical_meaning", ""),
            "expected_coverage_pct": cat.get("expected_coverage_pct"),
        })

    # Augment with non-kin "context motifs" — banner/community/co-residence
    # overlap. These aren't in the seal catalog (which is kinship-only) but
    # historians want to see *something* on hard-negative candidates that have
    # no kin path to the husband. Renders the same way in MotifMiniGlyph.
    for ctx in _context_motifs(husband_id, wife_id):
        motif_ids.append(ctx["id"])
        details.append(ctx)

    return {"motif_ids": motif_ids, "details": details}


_CTX_MOTIFS = [
    {
        "id": "CTX_same_banner",
        "name_en": "same banner",
        "explanation_en": "x and y share the same banner affiliation. Banner endogamy was the dominant marriage rule for Qing bannermen households; cross-banner unions required permission and are notably rarer in CMGPD-LN.",
        "relations": ["r_banner_endogamy"],
        "historical_meaning": "Banner-endogamous match.",
    },
    {
        "id": "CTX_same_community",
        "name_en": "same community",
        "explanation_en": "x and y were registered in the same community (village/garrison) cluster. Same-community marriages were the practical norm given travel constraints.",
        "relations": ["r_co_community"],
        "historical_meaning": "Community-local match.",
    },
    {
        "id": "CTX_co_resident",
        "name_en": "co-resident at some panel year",
        "explanation_en": "x and y shared the same HOUSEHOLD_ID in at least one CMGPD-LN wave. Possible adoption, fostering, or pre-marriage residence.",
        "relations": ["r_co_household"],
        "historical_meaning": "Shared household at some point.",
    },
    {
        "id": "CTX_same_region",
        "name_en": "same region",
        "explanation_en": "x and y were registered in the same broad region (e.g. North Liaoning). Weaker than community overlap but still constrains how far the marriage market reached.",
        "relations": ["r_co_region"],
        "historical_meaning": "Region-local match.",
    },
]


def _context_motifs(husband_id: str, wife_id: str) -> list[dict]:
    """Profile/parquet-driven non-kin motif checks. Cheap; no graph BFS."""
    out: list[dict] = []
    try:
        from ..mas import profiles as _profiles
        _profiles._load()
        h = _profiles._cache.get(_strip_prefix(husband_id))
        w = _profiles._cache.get(_strip_prefix(wife_id))
    except Exception:
        h = w = None
    if h and w:
        bh, bw = h.get("banner_id"), w.get("banner_id")
        if bh is not None and bw is not None and bh == bw:
            out.append({**_CTX_MOTIFS[0], "length": 1, "supporting_path_count": 1, "expected_coverage_pct": None})
        ch, cw = h.get("community_id"), w.get("community_id")
        if ch is not None and cw is not None and ch == cw:
            out.append({**_CTX_MOTIFS[1], "length": 1, "supporting_path_count": 1, "expected_coverage_pct": None})
        # Region overlap is the weakest geographic context but very informative
        # for hard-negatives that share neither banner nor community.
        rh, rw = h.get("region_id"), w.get("region_id")
        if rh is not None and rw is not None and rh == rw:
            out.append({**_CTX_MOTIFS[3], "length": 1, "supporting_path_count": 1, "expected_coverage_pct": None})

    # Co-residence — use the household-history axis already loaded for V6
    # similarity. Imported lazily to avoid a circular at module init.
    try:
        from .pair_features_endpoint import _same_household_history, _strip_prefix as _sp
        if _same_household_history(_sp(husband_id), _sp(wife_id)) > 0:
            out.append({**_CTX_MOTIFS[2], "length": 1, "supporting_path_count": 1, "expected_coverage_pct": None})
    except Exception:
        pass
    return out


# ── Route ────────────────────────────────────────────────────────────
@router.get("/motifs/{husband_id}/{wife_id}")
def get_motifs(husband_id: str, wife_id: str, year: int) -> dict:
    """Return the list of motifs that are *present* on the (husband, wife)
    pair at `year`, plus catalog metadata for each one.

    Response:
        {
          "motif_ids": ["M01_direct_sibling", ...],
          "details":   [{id, name_en, explanation_en, relations, length,
                         supporting_path_count, historical_meaning,
                         expected_coverage_pct}, ...]
        }

    503 when the seal package or graph cache wasn't available at boot.
    """
    if _unavailable_reason is not None:
        raise HTTPException(
            status_code=503,
            detail={"error": "motif service unavailable", "reason": _unavailable_reason},
        )
    return _detect_cached(str(husband_id), str(wife_id), int(year))
