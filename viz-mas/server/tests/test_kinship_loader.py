"""Unit tests for the V6 kinship-graph backend."""
from __future__ import annotations

import pytest

from server.data import kinship_loader as kl


# P259640 (male, son) and P260107 (female, daughter) share parents
# F=258108, M=258964 in the cleaned DS0001 parquet — verified at module
# write time. They are siblings and a stable fixture pair.
_KNOWN_PERSON = "P259640"
_KNOWN_SIBLING = "P260107"


def test_single_person_lookup_has_focal_and_edges():
    out = kl.khop_kinship(_KNOWN_PERSON, k=1)
    assert out["focal_id"] == _KNOWN_PERSON

    focal = [n for n in out["nodes"] if n.get("role") == "focal"]
    assert len(focal) == 1
    assert focal[0]["id"] == _KNOWN_PERSON

    # Known person has parents + at least one sibling → non-empty edges.
    assert out["edges"], "expected non-empty edges for a known person"
    # All node ids are P-prefixed, all edges reference known nodes.
    node_ids = {n["id"] for n in out["nodes"]}
    assert all(nid.startswith("P") for nid in node_ids)
    for e in out["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids
        assert e["type"] in {"r_fs", "r_fd", "r_ms", "r_md", "r_sib"}


def test_p_prefix_and_bare_numeric_match():
    a = kl.khop_kinship(_KNOWN_PERSON, k=1)
    b = kl.khop_kinship(_KNOWN_PERSON.lstrip("P"), k=1)
    assert a == b


def test_sibling_edges_dedup():
    """For each unordered pair of siblings, exactly one r_sib edge."""
    out = kl.khop_kinship(_KNOWN_PERSON, k=1)
    sib_pairs = []
    for e in out["edges"]:
        if e["type"] == "r_sib":
            sib_pairs.append(frozenset({e["source"], e["target"]}))
    assert len(sib_pairs) == len(set(sib_pairs)), "duplicate r_sib edges"
    # Each r_sib must include the focal at one end (k=1 only surfaces
    # focal↔sibling pairs, not sibling↔sibling).
    for p in sib_pairs:
        assert _KNOWN_PERSON in p


def test_multi_dedupes_nodes_and_edges():
    """Two siblings share parents → merged node set is the union, not
    the concatenation, and edges between identical (source,target,type)
    tuples are kept once."""
    a = kl.khop_kinship(_KNOWN_PERSON, k=1)
    b = kl.khop_kinship(_KNOWN_SIBLING, k=1)
    merged = kl.khop_kinship_multi([_KNOWN_PERSON, _KNOWN_SIBLING], k=1)

    node_ids = [n["id"] for n in merged["nodes"]]
    assert len(node_ids) == len(set(node_ids)), "node ids not deduped"
    expected = {n["id"] for n in a["nodes"]} | {n["id"] for n in b["nodes"]}
    assert set(node_ids) == expected

    edge_keys = [(e["source"], e["target"], e["type"]) for e in merged["edges"]]
    assert len(edge_keys) == len(set(edge_keys)), "edge tuples not deduped"

    # Both ids should appear as focals.
    assert merged["focal_ids"] == [_KNOWN_PERSON, _KNOWN_SIBLING]
    # Each focal node should be marked role='focal' in the merged set.
    roles = {n["id"]: n.get("role") for n in merged["nodes"]}
    assert roles[_KNOWN_PERSON] == "focal"
    assert roles[_KNOWN_SIBLING] == "focal"


def test_unknown_person_returns_focal_only_no_crash():
    bogus = "P999999999"
    out = kl.khop_kinship(bogus, k=1)
    assert out == {
        "focal_id": bogus,
        "nodes": [{"id": bogus, "role": "focal"}],
        "edges": [],
    }
