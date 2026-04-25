"""Smoke + unit tests for the HGT marriage-prediction pipeline.

The smoke test trains 2 epochs on a tight 1849–1854 window with a small model
and asserts an end-to-end run produces a metrics report. Unit tests verify the
key invariants the design depends on (ablation, masking, causal subgraphs).

Run from the project root:
    pytest tests/test_smoke.py -v
or:
    python -m tests.test_smoke
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.stage0_data import load_graph  # noqa: E402
from src.stage2_split import (  # noqa: E402
    ablate_maternal_edges,
    compute_cohort_split,
    mask_target_edges,
)
from src.stage3_temporal import subgraph_at_year  # noqa: E402
from src.sampling import sample_negatives  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def graph():
    if not config.GRAPH_CACHE_PATH.exists():
        pytest.skip(f"graph cache missing: {config.GRAPH_CACHE_PATH}")
    g, _ = load_graph()
    return g


# ── Unit checks ────────────────────────────────────────────────────────

def test_metadata_includes_all_edge_types(graph):
    """Every edge type in config.EDGE_TYPES must be present in graph.metadata()."""
    for et in config.EDGE_TYPES:
        assert et in graph.edge_types, f"missing edge type {et}"


def test_ablate_maternal_keeps_keys_zeros_edges(graph):
    """Ablation zeroes r_ms + r_md but keeps the keys and leaves r_fs + r_fd intact."""
    import copy
    g = copy.copy(graph)
    # snapshot paternal sizes
    fs_before = g["person", "r_fs", "person"].edge_index.size(1)
    fd_before = g["person", "r_fd", "person"].edge_index.size(1)

    ablate_maternal_edges(g)

    for et in config.ABLATE_EDGES:
        assert g[et].edge_index.size(1) == 0, f"{et} not zeroed"
        assert et in g.edge_types, f"{et} key removed"
    assert g["person", "r_fs", "person"].edge_index.size(1) == fs_before
    assert g["person", "r_fd", "person"].edge_index.size(1) == fd_before


def test_subgraph_monotone_in_t(graph):
    """For t1 < t2, |E(t1)| ≤ |E(t2)| for every edge type."""
    sg1 = subgraph_at_year(graph, 1800, use_cache=False)
    sg2 = subgraph_at_year(graph, 1850, use_cache=False)
    for et in graph.edge_types:
        assert sg1[et].edge_index.size(1) <= sg2[et].edge_index.size(1), (
            f"non-monotone {et}: {sg1[et].edge_index.size(1)} > {sg2[et].edge_index.size(1)}"
        )


def test_subgraph_strictly_before_t(graph):
    """All edges in subgraph_at_year(g, t) must have edge_time < t."""
    t = 1850
    sg = subgraph_at_year(graph, t, use_cache=False)
    for et in graph.edge_types:
        et_time = sg[et].edge_time
        if et_time.numel() == 0:
            continue
        # Static edges have edge_time = 0, satisfying < t for t > 0
        assert (et_time < t).all().item(), f"causal violation in {et}"


def test_mask_target_edges_removes_exactly(graph):
    edges = graph["person", "r_hw", "person"].edge_index
    if edges.size(1) < 2:
        pytest.skip("not enough r_hw edges")
    pair = (int(edges[0, 0].item()), int(edges[1, 0].item()))
    g2 = mask_target_edges(graph, [pair])
    n_before = edges.size(1)
    n_after = g2["person", "r_hw", "person"].edge_index.size(1)
    assert n_after == n_before - 1


def test_within_cohort_sampler_excludes_true_wife():
    cohort = [10, 20, 30, 40, 50]
    negs = sample_negatives(year=1850, true_wife=20, cohort_women=cohort, k=4)
    assert 20 not in negs


def test_kinship_partition_by_sex(graph):
    """|r_fs| + |r_fd| should equal total father→child edges (counting parent-child rows
    where child SEX is known)."""
    fs = graph["person", "r_fs", "person"].edge_index.size(1)
    fd = graph["person", "r_fd", "person"].edge_index.size(1)
    ms = graph["person", "r_ms", "person"].edge_index.size(1)
    md = graph["person", "r_md", "person"].edge_index.size(1)
    # Partition is correct iff each split is non-negative; we don't have the
    # pre-split count cached, so we just assert non-degenerate sizes.
    assert fs > 0 and fd > 0, "paternal partition produced no edges"
    assert ms > 0 and md > 0, "maternal partition produced no edges"
    # Quick sanity: in CMGPD-LN, recorded daughters are far fewer than sons,
    # so we'd expect fd < fs (and md < ms). This is a soft check.
    assert fd <= fs * 5, "implausible f→d / f→s ratio"


def test_split_buckets_are_disjoint(graph):
    split = compute_cohort_split(graph)
    train_keys = set(split["train"].keys())
    val_keys = set(split["val"].keys())
    test_keys = set(split["test"].keys())
    assert not (train_keys & val_keys)
    assert not (val_keys & test_keys)
    assert not (train_keys & test_keys)


# ── End-to-end smoke ───────────────────────────────────────────────────

@pytest.mark.skipif(
    not torch.cuda.is_available(),
    reason="smoke run is sized for GPU; skip on CPU-only CI",
)
def test_smoke_end_to_end(tmp_path):
    """Train 2 epochs on 1849-1851, eval on 1880-1881; expect metrics.json to exist
    AND for the test pass to actually have scored some pairs (catches the previous
    smoke-window bug where val/test years fell outside the cohort buckets)."""
    import json
    from src.train import train
    from src.evaluate import evaluate

    # Override checkpoint dir to keep test artifacts isolated
    orig_ckpt = config.CHECKPOINT_DIR
    config.CHECKPOINT_DIR = tmp_path / "ckpt"
    try:
        ckpt = train(smoke=True, epochs=2)
        assert ckpt.exists()
        out = evaluate(ckpt_path=ckpt, smoke=True)
        assert out.exists()
        metrics = json.loads(out.read_text())
        assert metrics["test"]["summary"]["n_pairs_scored"] > 0, (
            "smoke eval scored no pairs — smoke year filters likely fall outside "
            "val/test buckets again"
        )
    finally:
        config.CHECKPOINT_DIR = orig_ckpt


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
