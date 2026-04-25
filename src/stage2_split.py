"""Cohort-year split + maternal-edge ablation + target-edge masking.

Three operations on the HeteroData graph produced by stage0:

  compute_cohort_split(graph, train_end, val_end)
      Bin r_hw edges by marriage year into train/val/test buckets.

  ablate_maternal_edges(graph)
      Zero out the maternal edge types (config.ABLATE_EDGES) globally so the
      HGT layers learn aggregators that don't depend on them. Keys are
      preserved so HGTConv's per-edge-type projections stay registered.

  mask_target_edges(graph, pairs_to_hide)
      Remove specified r_hw edges from the message-passing graph (used at
      val/test time so the target edges aren't visible during encoding).
"""
from __future__ import annotations

import copy
import logging
from collections import defaultdict
from typing import Iterable

import torch
from torch_geometric.data import HeteroData

from . import config

log = logging.getLogger(__name__)

PairList = list[tuple[int, int, int]]  # (husband_idx, wife_idx, marriage_year)


# ── Cohort split ───────────────────────────────────────────────────────

def compute_cohort_split(
    graph: HeteroData,
    train_end: int = config.TRAIN_END_YEAR,
    val_end: int = config.VAL_END_YEAR,
) -> dict:
    """Bin r_hw edges by marriage year.

    Returns {
        "train": dict[year -> PairList],
        "val":   dict[year -> PairList],
        "test":  dict[year -> PairList],
        "all_test_pairs":  set[(h, w)],   # for masking
        "all_val_pairs":   set[(h, w)],
    }
    """
    edge_index = graph["person", "r_hw", "person"].edge_index
    edge_time = graph["person", "r_hw", "person"].edge_time

    train: dict[int, PairList] = defaultdict(list)
    val: dict[int, PairList] = defaultdict(list)
    test: dict[int, PairList] = defaultdict(list)

    src = edge_index[0].tolist()
    dst = edge_index[1].tolist()
    times = edge_time.tolist()

    for h, w, t in zip(src, dst, times):
        if t < config.MIN_YEAR or t > config.MAX_YEAR:
            continue
        if t <= train_end:
            train[t].append((h, w, t))
        elif t <= val_end:
            val[t].append((h, w, t))
        else:
            test[t].append((h, w, t))

    n_train = sum(len(v) for v in train.values())
    n_val = sum(len(v) for v in val.values())
    n_test = sum(len(v) for v in test.values())
    log.info(
        "cohort split: train=%d (years %d–%d), val=%d (%d–%d), test=%d (%d–%d)",
        n_train, config.MIN_YEAR, train_end,
        n_val, train_end + 1, val_end,
        n_test, val_end + 1, config.MAX_YEAR,
    )

    val_set = {(h, w) for pairs in val.values() for (h, w, _) in pairs}
    test_set = {(h, w) for pairs in test.values() for (h, w, _) in pairs}

    return {
        "train": dict(train),
        "val": dict(val),
        "test": dict(test),
        "all_val_pairs": val_set,
        "all_test_pairs": test_set,
    }


# ── Maternal-edge ablation ─────────────────────────────────────────────

def ablate_maternal_edges(graph: HeteroData) -> HeteroData:
    """Zero the edge types listed in config.ABLATE_EDGES.

    Mutates `graph` in place AND returns it for chaining. The edge type keys
    are preserved (HGTConv expects them in graph.metadata()); only the
    edge_index/edge_time tensors are replaced with empty tensors.
    """
    for et in config.ABLATE_EDGES:
        store = graph[et]
        n_before = store.edge_index.size(1) if store.edge_index.numel() else 0
        store.edge_index = torch.zeros((2, 0), dtype=torch.long)
        store.edge_time = torch.zeros((0,), dtype=torch.long)
        log.info("ablated %s: %d → 0 edges", et, n_before)
    return graph


# ── Target-edge masking ────────────────────────────────────────────────

def _shallow_copy_graph(graph: HeteroData) -> HeteroData:
    """Shallow copy: new HeteroData but tensors share storage.

    PyG's HeteroData supports `copy.copy` semantics that preserve tensor
    identity, which is what we need — node features (huge) must NOT be
    cloned.
    """
    return copy.copy(graph)


def mask_target_edges(
    graph: HeteroData,
    pairs_to_hide: Iterable[tuple[int, int]],
) -> HeteroData:
    """Return a copy of the graph with given r_hw edges removed.

    Only the r_hw edge_index/edge_time are rebuilt; all other stores are
    shared by reference.
    """
    pairs = {(int(h), int(w)) for h, w in pairs_to_hide}
    if not pairs:
        return graph

    out = _shallow_copy_graph(graph)
    src = graph["person", "r_hw", "person"].edge_index[0]
    dst = graph["person", "r_hw", "person"].edge_index[1]
    t = graph["person", "r_hw", "person"].edge_time

    keep_mask = torch.ones(src.size(0), dtype=torch.bool)
    src_l = src.tolist()
    dst_l = dst.tolist()
    for i, (h, w) in enumerate(zip(src_l, dst_l)):
        if (h, w) in pairs:
            keep_mask[i] = False

    out["person", "r_hw", "person"].edge_index = torch.stack(
        [src[keep_mask], dst[keep_mask]], dim=0
    )
    out["person", "r_hw", "person"].edge_time = t[keep_mask]
    n_removed = (~keep_mask).sum().item()
    log.debug("mask_target_edges: removed %d r_hw edges", n_removed)
    return out
