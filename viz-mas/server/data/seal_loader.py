"""SEAL motif-subgraph loader for V6's per-edge sub-window.

When the user clicks any r_hw edge in V6 (potential or confirmed), V6 calls
``GET /api/seal/{husband_id}/{wife_id}`` and renders the returned subgraph
in a popover.

This module currently ships a **STUB** that returns a canned sample so the
frontend is reviewer-replayable end-to-end. A future replacement should
extract the real enclosing subgraph from the HGT graph and apply DRNL
labelling per the SEAL paper. The contract below pins the strict output
format the frontend depends on.

──────────────────────────────────────────────────────────────────────────
REAL-DATA CONTRACT (when SEAL subgraph extraction is implemented)
──────────────────────────────────────────────────────────────────────────

Input
-----
* ``husband_id`` and ``wife_id`` — both ``P<digits>`` strings present in the
  cleaned DS0001 graph. Inputs may arrive without the ``P`` prefix; the
  loader must accept both forms and emit the prefixed form on output.

Graph access
------------
* Read ``data/processed/hgt_pipeline/graph.pt`` (the same HeteroData object
  the HGT encoder consumes).
* Restrict to person→person edges: ``r_fs, r_fd, r_ms, r_md, r_sib`` plus
  the contextual co-residence edges ``r_hh`` and ``r_cb`` if needed.
* Extract the *enclosing k-hop subgraph* :math:`\\mathcal{N}_k(m, w)` with
  :math:`k = 2` recommended (see ``SEAL`` original paper, Zhang & Chen
  NeurIPS 2018, §3).

DRNL labelling
--------------
* Apply Double-Radius Node Labelling: for each node :math:`v` in
  :math:`\\mathcal{N}_k(m, w)`, compute
  :math:`\\ell(v) = 1 + \\min(d(v,m), d(v,w)) + (d_s/2)(d_s + d_t - 1)`
  where :math:`d_s = \\min(d(v,m), d(v,w))` and
  :math:`d_t = \\max(d(v,m), d(v,w))`. Husband gets label 1; wife gets
  label 1 too (they are the focal pair).

Motif identity
--------------
* Classify the resulting labelled subgraph against the four canonical
  exemplars currently used by ``server/mas/motif_matcher.py``:
  ``m1_father_brother``, ``m2_uncle_in_law``, ``m3_same_household``,
  ``m4_banner_endog``. Use canonical-form match (Weisfeiler–Lehman or
  graph-isomorphism check on small k=2 neighbourhoods). Pairs that match
  no exemplar emit ``motif_id = "none"``.

──────────────────────────────────────────────────────────────────────────
STRICT OUTPUT FORMAT (versioned: v1)
──────────────────────────────────────────────────────────────────────────

::

    {
      "version":      "v1",
      "husband_id":   "P<int>",          # always prefixed
      "wife_id":      "P<int>",
      "motif_id":     "m1_father_brother" | "m2_uncle_in_law"
                    | "m3_same_household" | "m4_banner_endog" | "none",
      "motif_label":  str,               # human-readable, e.g. "Father → brother → wife"
      "drnl_radius":  int,               # k of the enclosing subgraph (1, 2, 3, ...)
      "nodes": [
        {
          "id":         "P<int>" | "anchor:<descr>",   # synthetic anchors allowed for missing nodes
          "drnl_label": int,             # >= 1; husband + wife share the lowest band
          "role":       "husband" | "wife" | "ancestor" | "kin" | "anchor",
          "is_focal":   bool,            # True iff role in {husband, wife}
          "sex":        "M" | "F" | "?"
        }, ...
      ],
      "edges": [
        {
          "source":        str,          # node id
          "target":        str,          # node id
          "type":          "r_fs" | "r_fd" | "r_ms" | "r_md" | "r_sib"
                         | "r_hh" | "r_cb" | "r_hw",
          "is_motif_edge": bool          # True iff this edge is part of the
                                         # canonical motif pattern that
                                         # classifies the subgraph
        }, ...
      ]
    }

Invariants the frontend relies on
---------------------------------
1. ``nodes`` always contains the focal pair: at least one node with
   ``role == "husband"`` and one with ``role == "wife"``.
2. Every ``edge.source`` and ``edge.target`` references some
   ``node.id`` (no dangling endpoints).
3. ``motif_id == "none"`` is permitted; in that case the subgraph still
   carries the focal pair plus their immediate kinship edges, so the user
   sees something useful.
4. ``drnl_label`` is monotone with distance from the focal pair: focal
   nodes have the smallest labels.
"""
from __future__ import annotations

from typing import Final

# ── Static stub exemplars keyed by a synthetic motif id ──────────────────
# The frontend renders whatever subgraph this returns; for now we cycle
# through the four canonical motifs deterministically by hashing the
# husband/wife ids so a clicked edge always shows the same subgraph.

_STUB_M1: Final[dict] = {
    "version":     "v1",
    "motif_id":    "m1_father_brother",
    "motif_label": "Father → brother → wife",
    "drnl_radius": 2,
    "nodes": [
        {"id": "anchor:husband",       "drnl_label": 1, "role": "husband",  "is_focal": True,  "sex": "M"},
        {"id": "anchor:wife",          "drnl_label": 1, "role": "wife",     "is_focal": True,  "sex": "F"},
        {"id": "anchor:husb-father",   "drnl_label": 2, "role": "ancestor", "is_focal": False, "sex": "M"},
        {"id": "anchor:husb-brother",  "drnl_label": 3, "role": "kin",      "is_focal": False, "sex": "M"},
        {"id": "anchor:wife-father",   "drnl_label": 2, "role": "ancestor", "is_focal": False, "sex": "M"},
    ],
    "edges": [
        {"source": "anchor:husb-father",  "target": "anchor:husband",      "type": "r_fs",  "is_motif_edge": True},
        {"source": "anchor:husb-father",  "target": "anchor:husb-brother", "type": "r_fs",  "is_motif_edge": True},
        {"source": "anchor:husb-brother", "target": "anchor:wife",         "type": "r_hw",  "is_motif_edge": True},
        {"source": "anchor:wife-father",  "target": "anchor:wife",         "type": "r_fd",  "is_motif_edge": False},
        {"source": "anchor:husband",      "target": "anchor:wife",         "type": "r_hw",  "is_motif_edge": True},
    ],
}

_STUB_M3: Final[dict] = {
    "version":     "v1",
    "motif_id":    "m3_same_household",
    "motif_label": "Co-resident kin (same household)",
    "drnl_radius": 1,
    "nodes": [
        {"id": "anchor:husband", "drnl_label": 1, "role": "husband", "is_focal": True,  "sex": "M"},
        {"id": "anchor:wife",    "drnl_label": 1, "role": "wife",    "is_focal": True,  "sex": "F"},
        {"id": "anchor:hh-head", "drnl_label": 2, "role": "kin",     "is_focal": False, "sex": "M"},
        {"id": "anchor:sibling", "drnl_label": 2, "role": "kin",     "is_focal": False, "sex": "F"},
    ],
    "edges": [
        {"source": "anchor:hh-head", "target": "anchor:husband", "type": "r_fs",  "is_motif_edge": True},
        {"source": "anchor:hh-head", "target": "anchor:sibling", "type": "r_fd",  "is_motif_edge": True},
        {"source": "anchor:husband", "target": "anchor:sibling", "type": "r_sib", "is_motif_edge": True},
        {"source": "anchor:husband", "target": "anchor:wife",    "type": "r_hw",  "is_motif_edge": True},
    ],
}

_STUB_M4: Final[dict] = {
    "version":     "v1",
    "motif_id":    "m4_banner_endog",
    "motif_label": "Banner endogamy (same banner affiliation)",
    "drnl_radius": 1,
    "nodes": [
        {"id": "anchor:husband",       "drnl_label": 1, "role": "husband",  "is_focal": True,  "sex": "M"},
        {"id": "anchor:wife",          "drnl_label": 1, "role": "wife",     "is_focal": True,  "sex": "F"},
        {"id": "anchor:husb-father",   "drnl_label": 2, "role": "ancestor", "is_focal": False, "sex": "M"},
        {"id": "anchor:wife-father",   "drnl_label": 2, "role": "ancestor", "is_focal": False, "sex": "M"},
        {"id": "anchor:banner-anchor", "drnl_label": 3, "role": "anchor",   "is_focal": False, "sex": "?"},
    ],
    "edges": [
        {"source": "anchor:husb-father",   "target": "anchor:husband",       "type": "r_fs", "is_motif_edge": False},
        {"source": "anchor:wife-father",   "target": "anchor:wife",          "type": "r_fd", "is_motif_edge": False},
        {"source": "anchor:husb-father",   "target": "anchor:banner-anchor", "type": "r_cb", "is_motif_edge": True},
        {"source": "anchor:wife-father",   "target": "anchor:banner-anchor", "type": "r_cb", "is_motif_edge": True},
        {"source": "anchor:husband",       "target": "anchor:wife",          "type": "r_hw", "is_motif_edge": True},
    ],
}

_STUB_NONE: Final[dict] = {
    "version":     "v1",
    "motif_id":    "none",
    "motif_label": "No canonical motif match — focal pair only",
    "drnl_radius": 1,
    "nodes": [
        {"id": "anchor:husband", "drnl_label": 1, "role": "husband", "is_focal": True, "sex": "M"},
        {"id": "anchor:wife",    "drnl_label": 1, "role": "wife",    "is_focal": True, "sex": "F"},
    ],
    "edges": [
        {"source": "anchor:husband", "target": "anchor:wife", "type": "r_hw", "is_motif_edge": True},
    ],
}

_STUB_CYCLE: Final[list[dict]] = [_STUB_M1, _STUB_M3, _STUB_M4, _STUB_NONE]


def _normalise(person_id: str) -> str:
    return person_id if person_id.startswith("P") else f"P{person_id}"


def get_seal_subgraph(husband_id: str, wife_id: str) -> dict:
    """STUB. Return a canned SEAL motif subgraph for a (husband, wife) pair.

    Selection is deterministic across the four exemplars by hashing the
    pair id, so a given clicked edge always produces the same subgraph
    until the real implementation lands. The output's ``husband_id`` and
    ``wife_id`` fields hold the actual queried pair so the frontend can
    label the focal nodes correctly.

    To migrate to real data, swap the body of this function for the
    DRNL+motif-classification pipeline described in the module docstring.
    The output schema is fixed (``version: "v1"``).
    """
    h = _normalise(husband_id)
    w = _normalise(wife_id)
    template = _STUB_CYCLE[(hash((h, w)) & 0xFFFFFFFF) % len(_STUB_CYCLE)]
    return {**template, "husband_id": h, "wife_id": w}
