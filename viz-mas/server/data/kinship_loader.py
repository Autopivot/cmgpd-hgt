"""K-hop person-only kinship subgraph lookup for the V6 candidate-graph UI.

Reads the cleaned DS0001 parquet once, builds parent/child adjacency
dicts keyed by raw PERSON_ID (no "P" prefix), then serves
`khop_kinship(pid)` queries with parents + children + siblings for k=1.

Mirrors the lazy-load + threading.Lock pattern from `server/mas/profiles.py`.
The frontend (and cohort JSONs) prefix PERSON_ID with "P"; this module
normalises on input and re-applies the prefix on output.
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CLEAN_PARQUET = ROOT.parent / "data" / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"

# In CMGPD-LN, FATHER_ID/MOTHER_ID == "0" or NaN encodes "missing".
_MISSING = {"", "0", "nan", "None"}

_lock = Lock()
_loaded = False
_father_of: dict[str, str] = {}
_mother_of: dict[str, str] = {}
_father_to_children: dict[str, list[str]] = {}
_mother_to_children: dict[str, list[str]] = {}
_sex: dict[str, str] = {}


def _strip_prefix(pid: str) -> str:
    """Cohort JSONs use "P12345"; the parquet stores raw "12345"."""
    pid = str(pid).strip()
    return pid[1:] if pid.startswith("P") else pid


def _add_prefix(pid: str) -> str:
    return pid if pid.startswith("P") else f"P{pid}"


def _is_missing(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in _MISSING or s.lower() == "nan"


def _load() -> None:
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        log.info("loading kinship adjacency from %s", CLEAN_PARQUET)
        try:
            import pandas as pd
            df = pd.read_parquet(
                CLEAN_PARQUET,
                columns=["PERSON_ID", "SEX", "FATHER_ID", "MOTHER_ID"],
            )
        except Exception as e:
            log.warning(
                "Failed to load kinship parquet (%s); kinship API will be empty", e,
            )
            _loaded = True
            return

        # Per-person attrs are stable across panel waves; take first row per PID.
        # CMGPD-LN: SEX 1=Female, 2=Male.
        df = df.drop_duplicates(subset="PERSON_ID", keep="first")

        for row in df.itertuples(index=False):
            pid = str(row.PERSON_ID)
            if _is_missing(pid):
                continue
            try:
                sex_raw = int(row.SEX) if row.SEX == row.SEX else 0  # NaN check
            except (TypeError, ValueError):
                sex_raw = 0
            _sex[pid] = "F" if sex_raw == 1 else "M" if sex_raw == 2 else "?"

            f = str(row.FATHER_ID) if not _is_missing(row.FATHER_ID) else None
            m = str(row.MOTHER_ID) if not _is_missing(row.MOTHER_ID) else None
            if f is not None:
                _father_of[pid] = f
                _father_to_children.setdefault(f, []).append(pid)
            if m is not None:
                _mother_of[pid] = m
                _mother_to_children.setdefault(m, []).append(pid)

        _loaded = True
        log.info(
            "kinship adjacency ready: %d persons, %d father-links, %d mother-links",
            len(_sex), len(_father_of), len(_mother_of),
        )


def _edge_type(parent: str, child: str) -> str:
    """`r_fs` father→son, `r_fd` father→daughter, `r_ms` mother→son,
    `r_md` mother→daughter. Used by the V6 frontend to colour-code edges."""
    parent_sex = _sex.get(parent, "?")
    child_sex = _sex.get(child, "?")
    if parent_sex == "M":
        return "r_fs" if child_sex == "M" else "r_fd"
    return "r_ms" if child_sex == "M" else "r_md"


def _focal_only(person_id: str) -> dict:
    return {
        "focal_id": _add_prefix(person_id),
        "nodes": [{"id": _add_prefix(person_id), "role": "focal"}],
        "edges": [],
    }


def khop_kinship(person_id: str, k: int = 1) -> dict:
    """Return a person's k-hop person-only family subgraph.

    For k=1 includes parents (FATHER_ID, MOTHER_ID), children (reverse
    lookup), and siblings (children of either same father OR same mother,
    excluding the focal). Edge types are `r_fs` / `r_fd` / `r_ms` / `r_md`
    for parent→child and `r_sib` for the undirected sibling pair (emitted
    once per pair). Output ids always carry the "P" prefix.
    """
    _load()
    raw = _strip_prefix(person_id)
    if raw not in _sex:
        return _focal_only(person_id)

    # Collect kin (k=1 only — multi-hop deferred until UI needs it).
    nodes: dict[str, dict] = {raw: {"id": _add_prefix(raw), "sex": _sex.get(raw, "?"), "role": "focal"}}
    edges: list[dict] = []

    def _add_kin(pid: str) -> None:
        if pid not in nodes:
            nodes[pid] = {"id": _add_prefix(pid), "sex": _sex.get(pid, "?"), "role": "kin"}

    # Parents → focal.
    father = _father_of.get(raw)
    mother = _mother_of.get(raw)
    if father is not None:
        _add_kin(father)
        edges.append({"source": _add_prefix(father), "target": _add_prefix(raw),
                      "type": _edge_type(father, raw)})
    if mother is not None:
        _add_kin(mother)
        edges.append({"source": _add_prefix(mother), "target": _add_prefix(raw),
                      "type": _edge_type(mother, raw)})

    # Focal → children. A child can appear via either father_to_children
    # or mother_to_children depending on the focal's sex; the union covers
    # both branches in case of inconsistent rows.
    children = set(_father_to_children.get(raw, [])) | set(_mother_to_children.get(raw, []))
    for child in sorted(children):
        _add_kin(child)
        edges.append({"source": _add_prefix(raw), "target": _add_prefix(child),
                      "type": _edge_type(raw, child)})

    # Siblings: union of (father's other children) and (mother's other children).
    sibs: set[str] = set()
    if father is not None:
        sibs.update(_father_to_children.get(father, []))
    if mother is not None:
        sibs.update(_mother_to_children.get(mother, []))
    sibs.discard(raw)
    # Stable order: sort by id so the JSON is deterministic across calls.
    for sib in sorted(sibs):
        _add_kin(sib)
        a, b = (raw, sib) if raw < sib else (sib, raw)
        edges.append({"source": _add_prefix(a), "target": _add_prefix(b), "type": "r_sib"})

    return {
        "focal_id": _add_prefix(raw),
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def khop_kinship_multi(person_ids: list[str], k: int = 1) -> dict:
    """Merge per-person k-hop subgraphs, deduplicating nodes by id and
    edges by (source, target, type). Useful for V6's "husband + top-K
    candidates" panel where overlapping kin should appear once."""
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    focal_ids: list[str] = []

    for pid in person_ids:
        sub = khop_kinship(pid, k=k)
        focal_ids.append(sub["focal_id"])
        for n in sub["nodes"]:
            nid = n["id"]
            # If a kin node from one subgraph is the focal of another, prefer
            # "focal" so the frontend highlights it correctly.
            if nid not in nodes or n.get("role") == "focal":
                nodes[nid] = n
        for e in sub["edges"]:
            edges[(e["source"], e["target"], e["type"])] = e

    return {
        "focal_ids": focal_ids,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
