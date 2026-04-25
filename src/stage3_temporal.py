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


def _ablation_tag(graph: HeteroData) -> str:
    """Tag the graph's ablation state so cache files don't collide.

    `compute_cohort_split` reads only `r_hw`, which `ablate_maternal_edges`
    leaves untouched, so the drop_pairs hash is identical for ablated and
    unablated runs. Without this tag, the second run would silently load
    the first run's cached subgraphs.
    """
    abl = all(graph[et].edge_index.size(1) == 0 for et in config.ABLATE_EDGES)
    return "abl" if abl else "full"


# Bump on schema changes that affect subgraph contents (e.g. v2 introduced
# per-cohort `person.x_macro` injection). Old cache files keyed without the
# version tag will simply not match and get rebuilt.
_CACHE_SCHEMA_VERSION = "v2"


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

    The output also carries a per-cohort macro vector at
    `out["person"].x_macro` (shape `(K,)`), looked up from
    `graph.macro_table` for year `t-1`. The encoder broadcasts this across
    all persons at forward time, replacing the previous (leaky) static
    snapshot of macro covariates.
    """
    if not hasattr(graph, "macro_table"):
        raise RuntimeError(
            "graph.macro_table is missing. The schema changed (macro covariates "
            "are now injected per-cohort). Rerun `python -m src.main --stage "
            "features --force` to rebuild the feature cache with the new schema."
        )

    cache_key = f"sg_{t}_{_CACHE_SCHEMA_VERSION}_{_ablation_tag(graph)}_{_drop_pairs_hash(drop_pairs)}.pt"
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

    # Stash per-cohort macro vector on the person store so the encoder picks
    # it up at forward time. The "<t" causality means the last visible year
    # is t-1; clamp to the table window for defensive indexing.
    n_years = graph.macro_table.size(0)
    macro_idx = max(0, min(t - 1 - config.MIN_YEAR, n_years - 1))
    out["person"].x_macro = graph.macro_table[macro_idx].clone()

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
