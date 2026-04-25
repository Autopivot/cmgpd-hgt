"""Per-year causal subgraphs.

Given a HeteroData graph with `edge_time` annotations on every edge type,
`subgraph_at_year(g, t)` returns a copy whose edges are restricted to
`edge_time < t`. This enforces "no future leakage" for the marriage
prediction task: when scoring candidates marrying in year t, the encoder
sees only what was observable strictly before t.

Static edge types (r_hc, r_cb in our schema have edge_time == 0) are kept
unconditionally — `0 < t` for any t > 0 in our 1749–1909 range.

Subgraphs are cached on disk because they're expensive to rebuild every
epoch and node features are shared by reference (cheap to copy the
HeteroData container).
"""
from __future__ import annotations

import copy
import hashlib
import logging
from pathlib import Path
from typing import Iterable

import torch
from torch_geometric.data import HeteroData

from . import config

log = logging.getLogger(__name__)


def _drop_pairs_hash(pairs: Iterable[tuple[int, int]] | None) -> str:
    if not pairs:
        return "none"
    sorted_pairs = sorted((int(h), int(w)) for h, w in pairs)
    h = hashlib.sha1()
    for hp, wp in sorted_pairs:
        h.update(f"{hp},{wp};".encode())
    return h.hexdigest()[:12]


def subgraph_at_year(
    graph: HeteroData,
    t: int,
    *,
    drop_pairs: Iterable[tuple[int, int]] | None = None,
    use_cache: bool = True,
) -> HeteroData:
    """Build (or load) a subgraph containing edges with edge_time < t.

    drop_pairs: r_hw pairs to forcibly remove on top of the time filter
                (e.g., val/test pairs we don't want to leak even though
                their edge_time is < t).
    """
    cache_key = f"sg_{t}_{_drop_pairs_hash(drop_pairs)}.pt"
    cache_path = config.SUBGRAPH_CACHE_DIR / cache_key
    if use_cache and cache_path.exists():
        return torch.load(str(cache_path), weights_only=False)

    out = copy.copy(graph)  # shallow: tensors shared except those we replace
    drop_set = {(int(h), int(w)) for h, w in (drop_pairs or [])}

    for edge_type in graph.edge_types:
        store = graph[edge_type]
        ei = store.edge_index
        et = store.edge_time
        if ei.numel() == 0:
            # Preserve empty stores as-is
            out[edge_type].edge_index = ei
            out[edge_type].edge_time = et
            continue

        # Static (untimed) edges: keep all (membership stays valid through time)
        if et.numel() == 0 or (et == 0).all():
            keep = torch.ones(ei.size(1), dtype=torch.bool)
        else:
            keep = et < t

        if drop_set and edge_type == ("person", "r_hw", "person"):
            src_l = ei[0].tolist()
            dst_l = ei[1].tolist()
            for i, (h, w) in enumerate(zip(src_l, dst_l)):
                if (h, w) in drop_set:
                    keep[i] = False

        out[edge_type].edge_index = ei[:, keep]
        out[edge_type].edge_time = et[keep] if et.numel() else et

    if use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(out, str(cache_path))

    return out


def clear_subgraph_cache() -> int:
    """Delete cached subgraphs (e.g., after schema change). Returns # files removed."""
    d: Path = config.SUBGRAPH_CACHE_DIR
    if not d.exists():
        return 0
    n = 0
    for f in d.glob("sg_*.pt"):
        f.unlink()
        n += 1
    log.info("cleared %d cached subgraphs from %s", n, d)
    return n
