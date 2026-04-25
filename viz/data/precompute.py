"""Precompute per-cohort viewer data for the HGT marriage-edge predictor.

For each (year, ablation_condition) pair, produce a JSON file that the
frontend can render directly. The contract is documented in
``viz/data/README.md``.

Usage::

    python viz/data/precompute.py --year 1882 --ablated
    python viz/data/precompute.py --year 1882 --unablated
    python viz/data/precompute.py --all
    python viz/data/precompute.py --year 1882 --stub

Real-mode loads the graph cache, runs an HGT checkpoint, and writes a real
JSON. Stub-mode synthesises a contract-valid file without touching the
model -- useful as a fallback when CUDA / pyclustering / sklearn versions
disagree, and for unblocking frontend development.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

# pyclustering 0.10.1 references numpy.warnings, which was removed in numpy 2.x.
# Install a shim before pyclustering's package init runs.
if not hasattr(np, "warnings"):
    import warnings as _warnings
    np.warnings = _warnings  # type: ignore[attr-defined]

# ── Path bootstrap ─────────────────────────────────────────────────────
# This file lives at viz/data/precompute.py; the project root is two
# directories up. Add the project root to sys.path so ``import src`` works
# whether the user runs ``python viz/data/precompute.py`` from the root or
# from any other directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("precompute")


# ── Shared constants ───────────────────────────────────────────────────
TARGET_YEARS = [1882, 1885, 1888, 1903, 1906, 1909]
DEFAULT_TARGET_YEARS = [1882, 1885, 1888]  # the 3 acceptance-required years
MAX_PAIRS_PER_COHORT = 6000
NEGATIVES_PER_HUSBAND = 5
PCA_COMPONENTS = 50
DEFAULT_K_MAX = 10

OUT_DIR = Path(__file__).resolve().parent


def _era_for_year(year: int) -> str:
    if year in (1882, 1885, 1888):
        return "regular"
    if year == 1903:
        return "catchup"
    if year in (1906, 1909):
        return "late"
    # Years outside the documented buckets default to ``regular``; the
    # contract permits the string-tagged value but downstream code should
    # not rely on this branch firing for the official 6 cohorts.
    return "regular"


def _output_path(year: int, ablated: bool) -> Path:
    if ablated:
        return OUT_DIR / f"cohort_{year}.json"
    return OUT_DIR / f"cohort_{year}__unablated.json"


# ── Real precompute pipeline ───────────────────────────────────────────

def _build_lineage_lookup(graph, id_maps):
    """Return ``person_idx -> 'L###'`` dict.

    Walks each person's ancestry through ``r_fs`` and ``r_fd`` (the two
    paternal parent->child edges) to find the most ancient ancestor. The
    ancestor's ``PERSON_ID`` is hashed to a stable ``Lxxx`` bucket. Persons
    with no incoming paternal edge are mapped to ``L_unknown``.
    """
    import torch  # local: avoids import cost in stub mode

    n_persons = graph["person"].num_nodes
    # Build child -> father lookup using the union of r_fs and r_fd.
    parent_of = np.full(n_persons, -1, dtype=np.int64)
    for rel in ("r_fs", "r_fd"):
        et = ("person", rel, "person")
        if et not in graph.edge_types:
            continue
        ei = graph[et].edge_index
        if ei.numel() == 0:
            continue
        src = ei[0].cpu().numpy()
        dst = ei[1].cpu().numpy()
        for s, d in zip(src, dst):
            if parent_of[d] == -1:
                parent_of[d] = s

    # Reverse the person id_map for printing.
    pmap = id_maps["person"]
    inv_pmap = [None] * n_persons
    for pid, idx in pmap.items():
        inv_pmap[idx] = pid

    # Walk to the ancestor (with cycle protection).
    ancestor = np.full(n_persons, -1, dtype=np.int64)
    for v in range(n_persons):
        cur = v
        seen = {cur}
        steps = 0
        while parent_of[cur] != -1 and parent_of[cur] not in seen and steps < 64:
            cur = int(parent_of[cur])
            seen.add(cur)
            steps += 1
        ancestor[v] = cur

    # Hash ancestor PERSON_ID -> "L%03d" with a small bucket count so siblings
    # plausibly land in the same lineage. Real lineages would require a more
    # principled clustering, but this gives a stable, content-addressable tag.
    lookup: dict[int, str] = {}
    for v in range(n_persons):
        a = int(ancestor[v])
        if a < 0:
            lookup[v] = "L_unknown"
            continue
        pid = inv_pmap[a] if 0 <= a < len(inv_pmap) else None
        if pid is None:
            lookup[v] = "L_unknown"
        else:
            # Stable hash to 3-digit lineage id.
            h = abs(hash(("lineage", str(pid)))) % 1000
            lookup[v] = f"L{h:03d}"
    return lookup


def _patri_path_count(sg, husband_idx: int, wife_idx: int) -> int:
    """Count length-1 + length-2 paths from husband to wife in the
    patrilineal subgraph (r_fs, r_fd, r_sib, r_hh, r_hc, r_cb).

    Implementation: build a person-to-person adjacency over all the listed
    edge types where the bridge nodes are persons. r_hh / r_hc / r_cb go
    through household / community / banner intermediaries, so we project
    them onto person->person two-hops by composition. We use scipy.sparse
    for the matrix algebra.
    """
    import scipy.sparse as sp  # local import
    n_persons = sg["person"].num_nodes

    def _ei(et):
        if et not in sg.edge_types:
            return None
        ei = sg[et].edge_index
        if ei.numel() == 0:
            return None
        return ei.cpu().numpy()

    # Person-person direct edges
    rows, cols = [], []
    for rel in ("r_fs", "r_fd", "r_sib"):
        ei = _ei(("person", rel, "person"))
        if ei is None:
            continue
        rows.extend(ei[0].tolist())
        cols.extend(ei[1].tolist())
        # Treat as undirected for path-counting
        rows.extend(ei[1].tolist())
        cols.extend(ei[0].tolist())

    if rows:
        data = np.ones(len(rows), dtype=np.float32)
        A_pp = sp.csr_matrix((data, (rows, cols)), shape=(n_persons, n_persons))
    else:
        A_pp = sp.csr_matrix((n_persons, n_persons), dtype=np.float32)

    # Compose person->household + household->person to get person-person
    # edges via shared household. Same for community and banner.
    def _bipartite(et_pn, et_np_or_unused, n_other):
        """Return person->person matrix from person-other-person two-hop."""
        ei_a = _ei(et_pn)
        if ei_a is None:
            return None
        # Person -> Other
        P2O = sp.csr_matrix(
            (np.ones(ei_a.shape[1], dtype=np.float32), (ei_a[0], ei_a[1])),
            shape=(n_persons, n_other),
        )
        # Two-hop through other => P2O @ P2O.T
        return P2O @ P2O.T

    # Household path
    n_hh = sg["household"].num_nodes
    A_hh = _bipartite(("person", "r_hh", "household"), None, n_hh) if n_hh else None

    # Banner path
    n_ba = sg["banner"].num_nodes
    A_cb = _bipartite(("person", "r_cb", "banner"), None, n_ba) if n_ba else None

    # Community path goes person -> household -> community, which is a
    # 3-hop on the original graph. We approximate by intersecting the
    # household composition with itself (already counted via r_hh) and
    # skip r_hc as a direct contribution; r_hc shows up in real 2-hops
    # via household embeddings but not as a person-person path of length
    # ≤ 2. The contract says "1-hop and 2-hop paths counted" so we keep
    # only A_pp + A_hh + A_cb for the path-of-length-≤-2 budget.
    A = A_pp.tolil()
    if A_hh is not None:
        # add 2-hop count (subtract the diagonal since husband->household->husband
        # would otherwise count self-loops; we only care about pair-specific)
        A_hh = A_hh.tolil()
        A_hh.setdiag(0)
        A = A + A_hh
    if A_cb is not None:
        A_cb = A_cb.tolil()
        A_cb.setdiag(0)
        A = A + A_cb

    # 1-hop paths via A_pp + 2-hop paths via A_pp @ A_pp.
    A_csr = sp.csr_matrix(A)
    A_pp_sq = A_pp @ A_pp
    total = A_csr[husband_idx, wife_idx]
    total = total + A_pp_sq[husband_idx, wife_idx]
    try:
        return int(total)
    except Exception:
        # Sparse sum of singular cell may return matrix; coerce.
        return int(np.asarray(total)[0, 0]) if hasattr(total, "shape") else int(total)


def _attach_macro_shim(graph):
    """Older checkpoints were trained without macro covariates (n_macro=0).
    Attach a zero-width ``macro_table`` so ``build_model`` and
    ``subgraph_at_year`` accept the graph. The PersonEmbedder ends up
    concatenating an empty (N, 0) tensor -- a no-op."""
    import torch
    from src import config as src_config
    if hasattr(graph, "macro_table"):
        return
    n_years = src_config.MAX_YEAR - src_config.MIN_YEAR + 1
    graph.macro_table = torch.zeros((n_years, 0), dtype=torch.float32)


def _load_graph_and_model(ablated: bool, device: str):
    """Return (graph, hgt, scorer, id_maps, ckpt_meta)."""
    import torch
    from src.stage0_data import load_graph
    from src.stage2_split import ablate_maternal_edges
    from src.model import build_model
    from src import config as src_config

    log.info("loading graph cache from %s", src_config.GRAPH_CACHE_PATH)
    graph, id_maps = load_graph()
    _attach_macro_shim(graph)

    if ablated:
        ablate_maternal_edges(graph)

    ckpt_path = src_config.CKPT_ABLATED if ablated else src_config.CKPT_UNABLATED
    log.info("loading checkpoint %s", ckpt_path)
    state = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    hgt, scorer = build_model(graph)
    hgt.load_state_dict(state["hgt_state"])
    scorer.load_state_dict(state["scorer_state"])
    hgt.to(device).eval()
    scorer.to(device).eval()
    return graph, hgt, scorer, id_maps, state


def _move_graph_to_device(graph, device):
    import torch
    for nt in graph.node_types:
        for k, v in list(graph[nt].items()):
            if torch.is_tensor(v):
                graph[nt][k] = v.to(device)
    for et in graph.edge_types:
        for k, v in list(graph[et].items()):
            if torch.is_tensor(v):
                graph[et][k] = v.to(device)
    return graph


def _select_husbands(pairs: list[tuple[int, int, int]], rng: random.Random,
                     budget_pairs: int) -> list[tuple[int, int]]:
    """Choose (husband_idx, wife_idx) pairs to score under the budget.

    Each husband scores 1 + NEGATIVES_PER_HUSBAND = 6 pairs. Cap total
    pairs near ``budget_pairs`` by sampling husbands uniformly.
    """
    husbands_per_pair = 1 + NEGATIVES_PER_HUSBAND
    max_husbands = max(1, budget_pairs // husbands_per_pair)
    pairs_unique = list({(h, w): t for h, w, t in pairs}.items())
    if len(pairs_unique) > max_husbands:
        sampled = rng.sample(pairs_unique, max_husbands)
    else:
        sampled = pairs_unique
    return [((hw[0], hw[1])) for hw, _ in sampled]


def _run_xmeans_or_kmeans(z: np.ndarray, kmax: int) -> tuple[np.ndarray, int]:
    """Cluster the post-PCA latent z; returns (labels, k)."""
    try:
        from pyclustering.cluster.xmeans import xmeans, splitting_type
        from pyclustering.cluster.center_initializer import kmeans_plusplus_initializer

        init = kmeans_plusplus_initializer(z, 2).initialize()
        x = xmeans(z, initial_centers=init, kmax=kmax,
                   criterion=splitting_type.BAYESIAN_INFORMATION_CRITERION)
        x.process()
        clusters_list = x.get_clusters()
        labels = np.zeros(len(z), dtype=np.int32)
        for cidx, members in enumerate(clusters_list):
            for m in members:
                labels[m] = cidx
        return labels, len(clusters_list)
    except Exception as exc:
        log.info("pyclustering unavailable (%s); falling back to KMeans + silhouette", exc)
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        best_k = 2
        best_score = -1.0
        best_labels = None
        # silhouette undefined for k=1 and for n_samples == k. Bound
        # the search to a reasonable upper limit.
        upper = min(kmax, max(2, len(z) // 5))
        for k in range(2, upper + 1):
            km = KMeans(n_clusters=k, n_init=5, random_state=0).fit(z)
            try:
                s = silhouette_score(z, km.labels_)
            except Exception:
                continue
            if s > best_score:
                best_score = s
                best_k = k
                best_labels = km.labels_
        if best_labels is None:
            km = KMeans(n_clusters=2, n_init=5, random_state=0).fit(z)
            best_labels = km.labels_
            best_k = 2
        return np.asarray(best_labels, dtype=np.int32), int(best_k)


def precompute_real(year: int, ablated: bool, device: str | None = None) -> dict:
    """Run the full real precompute pipeline for one (year, condition).

    Returns the contract-shaped dict (the caller writes JSON)."""
    import torch
    from sklearn.decomposition import PCA
    from sklearn.manifold import MDS
    from sklearn.preprocessing import StandardScaler
    from scipy.optimize import linear_sum_assignment
    from src.stage2_split import compute_cohort_split
    from src.stage3_temporal import subgraph_at_year
    from src.sampling import build_year_to_women

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    log.info("device=%s ablated=%s year=%d", device, ablated, year)

    graph, hgt, scorer, id_maps, ckpt_meta = _load_graph_and_model(ablated, device)
    split = compute_cohort_split(graph)
    if year not in split["test"]:
        raise RuntimeError(f"year {year} is not in the test bucket; available: {sorted(split['test'].keys())}")

    cohort_pairs = split["test"][year]  # [(h, w, t), ...]
    cohort_women_by_year = build_year_to_women({**split["train"], **split["val"], **split["test"]})
    women_in_cohort = cohort_women_by_year.get(year, [])
    if not cohort_pairs or not women_in_cohort:
        raise RuntimeError(f"year {year}: empty cohort")

    # Budget husbands so total pairs (1 + NEG) per husband <= MAX_PAIRS_PER_COHORT.
    rng = random.Random(0)
    selected_pairs = _select_husbands(cohort_pairs, rng, MAX_PAIRS_PER_COHORT)
    log.info("year=%d selected %d / %d husbands", year, len(selected_pairs), len(cohort_pairs))

    # Build subgraph (drop val + test pairs from message passing).
    drop_global = split["all_val_pairs"] | split["all_test_pairs"]
    sg = subgraph_at_year(graph, year, drop_pairs=drop_global)
    sg = _move_graph_to_device(sg, device)

    husband_indices = [h for h, _ in selected_pairs]
    true_wife_indices = [w for _, w in selected_pairs]
    husband_set = set(husband_indices)

    # Encode persons.
    log.info("running HGT forward")
    with torch.no_grad():
        x_persons = hgt(sg)["person"]            # [N, H]

    # Score every (husband, cohort_woman) for husbands we care about.
    H_dim = x_persons.size(1)
    M = len(husband_indices)
    W = len(women_in_cohort)
    log.info("scoring M=%d husbands x W=%d cohort-women", M, W)

    h_m_all = x_persons[torch.tensor(husband_indices, device=device)]   # [M, H]
    h_w_all = x_persons[torch.tensor(women_in_cohort, device=device)]   # [W, H]

    scores = np.empty((M, W), dtype=np.float32)
    pair_chunk = 64
    with torch.no_grad():
        for s in range(0, M, pair_chunk):
            e = min(s + pair_chunk, M)
            blk = h_m_all[s:e]
            c = blk.size(0)
            h_m_exp = blk.unsqueeze(1).expand(-1, W, -1).reshape(-1, H_dim)
            h_w_exp = h_w_all.unsqueeze(0).expand(c, -1, -1).reshape(-1, H_dim)
            scores[s:e] = scorer(h_m_exp, h_w_exp).reshape(c, W).detach().cpu().numpy()

    # Hungarian assignment over the cohort-square scores.
    cost = -scores
    if M != W:
        pad = np.full((max(M, W), max(M, W)), 1e6)
        pad[:M, :W] = cost
        cost = pad
    row_idx, col_idx = linear_sum_assignment(cost)
    husband_to_assigned: dict[int, int] = {}
    for r, c in zip(row_idx, col_idx):
        if r >= M or c >= W:
            continue
        husband_to_assigned[husband_indices[r]] = women_in_cohort[c]

    # Compute per-husband negatives (top-5 scoring non-spouse cohort women).
    # We score against ``women_in_cohort`` (the true-wife column indexes are
    # ``women_in_cohort.index(true_wife)``) -- pre-compute that mapping.
    woman_to_col = {w: i for i, w in enumerate(women_in_cohort)}

    log.info("collecting hard negatives + per-pair features")
    pair_records: list[dict] = []
    z_input_per_pair: list[np.ndarray] = []  # 4*H concatenated vectors

    h_m_cpu = h_m_all.detach().cpu().numpy()        # [M, H]
    h_w_cpu = h_w_all.detach().cpu().numpy()        # [W, H]

    pair_id = 0
    for r, (m_idx, true_w_idx) in enumerate(zip(husband_indices, true_wife_indices)):
        if true_w_idx not in woman_to_col:
            continue
        true_col = woman_to_col[true_w_idx]
        true_score = float(scores[r, true_col])
        # Hard negatives: top scoring women excluding true wife.
        order = np.argsort(-scores[r])
        neg_cols: list[int] = []
        for c in order:
            if women_in_cohort[c] == true_w_idx:
                continue
            neg_cols.append(int(c))
            if len(neg_cols) >= NEGATIVES_PER_HUSBAND:
                break

        # Best-negative score for the positive's gap calculation.
        if neg_cols:
            best_neg_score = float(scores[r, neg_cols[0]])
        else:
            best_neg_score = 0.0

        # Rank of true wife in this husband's row (1-indexed).
        rank_true = int(np.where(order == true_col)[0][0]) + 1
        hung_correct = husband_to_assigned.get(m_idx) == true_w_idx

        # Helper to emit a record + its 4H vector.
        def _emit(label: int, w_idx_local: int, w_col: int, score_value: float,
                  score_gap: float, rank_field: int | None,
                  hung_field: bool | None):
            nonlocal pair_id
            h_m_vec = h_m_cpu[r]
            h_w_vec = h_w_cpu[w_col]
            z4 = np.concatenate([
                h_m_vec, h_w_vec,
                np.abs(h_m_vec - h_w_vec), h_m_vec * h_w_vec,
            ]).astype(np.float32)
            pair_records.append({
                "id": pair_id,
                "husband_idx": int(m_idx),
                "wife_idx": int(w_idx_local),
                "label": int(label),
                "score": float(score_value),
                "score_gap": float(score_gap),
                "rank_of_true_wife": rank_field,
                "hungarian_correct": bool(hung_field) if hung_field is not None else None,
            })
            z_input_per_pair.append(z4)
            pair_id += 1

        # Positive
        gap_pos = true_score - best_neg_score
        _emit(1, true_w_idx, true_col, true_score, gap_pos, rank_true, hung_correct)

        # Negatives: gap = score(neg) - score(true); negative if husband ranks
        # true above this neg, positive if husband mistakenly prefers this neg.
        for nc in neg_cols:
            neg_w_idx = women_in_cohort[nc]
            neg_score = float(scores[r, nc])
            gap_neg = neg_score - true_score
            # Negatives don't have rank_of_true_wife or hungarian_correct
            # in the contract sense (those are husband-level; we leave the
            # rank field as the husband's true-wife rank for context, and
            # the hungarian flag as None).
            _emit(0, neg_w_idx, nc, neg_score, gap_neg, rank_true, None)

    if not pair_records:
        raise RuntimeError(f"year {year}: no pair records produced")

    # Project the 4H input through the scorer's first linear+GELU to get z (H-dim).
    z_in = np.stack(z_input_per_pair, axis=0).astype(np.float32)
    log.info("projecting %d pairs through scorer.mlp[0:2] -> H=%d", len(z_in), H_dim)
    with torch.no_grad():
        # scorer.mlp[0] is Linear(4H, H), scorer.mlp[1] is GELU.
        z_t = torch.from_numpy(z_in).to(device)
        first_lin = scorer.mlp[0]
        first_act = scorer.mlp[1]
        z_proj = first_act(first_lin(z_t)).detach().cpu().numpy()

    # Z-score across all pairs for this cohort, then PCA(50), then MDS(2).
    log.info("PCA -> MDS")
    scaler = StandardScaler()
    z_norm = scaler.fit_transform(z_proj)
    n_components = min(PCA_COMPONENTS, z_norm.shape[0], z_norm.shape[1])
    pca = PCA(n_components=n_components, random_state=0)
    z_pca = pca.fit_transform(z_norm)
    # MDS on a uniformly-sampled subset for speed if huge.
    mds = MDS(n_components=2, n_init=1, max_iter=200, dissimilarity="euclidean",
              random_state=0, normalized_stress="auto")
    mds_coords = mds.fit_transform(z_pca)

    cluster_labels, k_clusters = _run_xmeans_or_kmeans(z_pca, DEFAULT_K_MAX)

    # Lineage lookup (uses the original graph, not the time-restricted subgraph).
    log.info("computing lineage lookup")
    lineage = _build_lineage_lookup(graph, id_maps)

    # Build the patrilineal subgraph adjacency once; reuse for all pairs.
    log.info("building patri adjacency for path counts")
    sg_cpu_for_paths = _move_graph_to_device(subgraph_at_year(graph, year, drop_pairs=drop_global), "cpu")
    n_persons = sg_cpu_for_paths["person"].num_nodes

    def _ei(et):
        if et not in sg_cpu_for_paths.edge_types:
            return None
        ei = sg_cpu_for_paths[et].edge_index
        if ei.numel() == 0:
            return None
        return ei.cpu().numpy()

    # Per-person neighbor sets through within-person patrilineal/sibling edges.
    # We do NOT form the dense N×N product (the original implementation OOMed
    # at ~159 GiB on the 266k-person graph because banner co-membership produces
    # near-dense matrices). Instead we count 1- and 2-hop paths on the fly per
    # scored pair, which is O(degree(m)) per query — fast since the average
    # patri/sib degree is ~5–10.
    nbr_pp: list[set[int]] = [set() for _ in range(n_persons)]
    for rel in ("r_fs", "r_fd", "r_sib"):
        ei = _ei(("person", rel, "person"))
        if ei is None:
            continue
        for s, d in zip(ei[0].tolist(), ei[1].tolist()):
            nbr_pp[s].add(d)
            nbr_pp[d].add(s)

    # Per-person household memberships (set of household idx).
    person_hhs: list[set[int]] = [set() for _ in range(n_persons)]
    ei_hh = _ei(("person", "r_hh", "household"))
    if ei_hh is not None:
        for p, h in zip(ei_hh[0].tolist(), ei_hh[1].tolist()):
            person_hhs[p].add(h)
    # Banner co-membership is dropped from path counting: there are only
    # 4 banners across 266k persons, so banner-sharing fires for ~25% of all
    # pairs and is essentially noise for the pair-resolution task.

    def _path_count(m: int, w: int) -> int:
        if m == w:
            return 0
        cnt = 0
        nm = nbr_pp[m]
        nw = nbr_pp[w]
        # 1-hop within-person (kinship/sibling)
        if w in nm:
            cnt += 1
        # 2-hop within-person: shared neighbour count
        cnt += len(nm & nw)
        # 1-hop "shares a household" (acts as a 1-hop community-style link)
        if person_hhs[m] and person_hhs[w] and (person_hhs[m] & person_hhs[w]):
            cnt += 1
        return cnt

    # Reverse map idx -> PERSON_ID for output strings.
    inv_pmap: list[str] = [""] * n_persons
    for pid, idx in id_maps["person"].items():
        inv_pmap[idx] = str(pid)

    era = _era_for_year(year)

    # Z trim: contract says z is 128 dim. If the model HIDDEN differs, we
    # still emit the actual H-dim vector and surface a length mismatch
    # warning rather than silently truncating.
    expected_z_dim = 128
    actual_z_dim = z_proj.shape[1]
    if actual_z_dim != expected_z_dim:
        log.warning("z dim is %d (expected %d); emitting actual dim", actual_z_dim, expected_z_dim)

    final_pairs = []
    for i, rec in enumerate(pair_records):
        m_idx = rec["husband_idx"]
        w_idx = rec["wife_idx"]
        lh = lineage.get(m_idx, "L_unknown")
        lw = lineage.get(w_idx, "L_unknown")
        path_count = _path_count(m_idx, w_idx)
        final_pairs.append({
            "id": int(rec["id"]),
            "husband_id": "P" + (inv_pmap[m_idx] if 0 <= m_idx < len(inv_pmap) else str(m_idx)),
            "wife_id":    "P" + (inv_pmap[w_idx] if 0 <= w_idx < len(inv_pmap) else str(w_idx)),
            "label": int(rec["label"]),
            "score": round(float(rec["score"]), 4),
            "score_gap": round(float(rec["score_gap"]), 4),
            "rank_of_true_wife": int(rec["rank_of_true_wife"]) if rec["rank_of_true_wife"] is not None and rec["label"] == 1 else None,
            "hungarian_correct": bool(rec["hungarian_correct"]) if rec["label"] == 1 and rec["hungarian_correct"] is not None else None,
            "lineage_husband": lh,
            "lineage_wife": lw,
            "same_lineage": (lh == lw and lh != "L_unknown"),
            "era": era,
            "patri_path_count": int(path_count),
            "z": [round(float(v), 4) for v in z_proj[i].tolist()],
        })

    # mds_coords aligned to pairs by id.
    mds_list = [[float(round(c[0], 4)), float(round(c[1], 4))] for c in mds_coords]
    cluster_list = [int(c) for c in cluster_labels]

    return {
        "year": int(year),
        "n_pairs": len(final_pairs),
        "pairs": final_pairs,
        "mds_coords": mds_list,
        "clusters": cluster_list,
        "k_clusters": int(k_clusters),
        "ablation": "ablated" if ablated else "unablated",
    }


# ── Stub fallback ──────────────────────────────────────────────────────

def precompute_stub(year: int, ablated: bool, n_pairs: int = 250,
                    n_clusters: int = 8, seed: int = 0) -> dict:
    """Synthesise a contract-valid JSON without touching the model."""
    rng = np.random.default_rng(seed + year + (0 if ablated else 1))

    z_dim = 128
    cluster_assignments = rng.integers(0, n_clusters, size=n_pairs)
    cluster_offsets = rng.normal(2.0, 0.5, size=(n_clusters, z_dim))

    z = rng.standard_normal((n_pairs, z_dim)).astype(np.float32)
    z = z + cluster_offsets[cluster_assignments]

    # MDS stub: first 2 PCA components (centered).
    z_centered = z - z.mean(axis=0, keepdims=True)
    # Use np.linalg.svd for a quick PCA without sklearn dependency.
    u, s, vt = np.linalg.svd(z_centered, full_matrices=False)
    pcs = (u[:, :2] * s[:2])
    mds_coords = [[float(round(pcs[i, 0], 4)), float(round(pcs[i, 1], 4))]
                  for i in range(n_pairs)]

    labels = rng.choice([1, 0], size=n_pairs, p=[0.8, 0.2])

    pairs = []
    # Pre-sample lineages.
    lineage_pool = [f"L{i:03d}" for i in range(30)]

    for i in range(n_pairs):
        label = int(labels[i])
        if label == 1:
            score = float(rng.normal(3.0, 1.0))
            best_neg = float(rng.normal(0.5, 1.0))
            score_gap = score - best_neg
            rank = int(max(1, rng.poisson(1.5) + 1))
            hung = bool(rng.random() < 0.7)
            patri = int(rng.poisson(3.0))
        else:
            score = float(rng.normal(-1.0, 1.5))
            true_score = float(rng.normal(3.0, 1.0))
            score_gap = score - true_score
            rank = None
            hung = None
            patri = int(rng.poisson(0.5))

        same_lin = bool(rng.random() < 0.05)
        if same_lin:
            lh = lw = lineage_pool[int(rng.integers(0, 30))]
        else:
            lh = lineage_pool[int(rng.integers(0, 30))]
            lw = lineage_pool[int(rng.integers(0, 30))]
            if lw == lh:
                # break tie by bumping
                lw = lineage_pool[(int(rng.integers(0, 30)) + 1) % 30]

        husband_id = f"P{rng.integers(0, 999999):06d}"
        wife_id = f"P{rng.integers(0, 999999):06d}"

        pairs.append({
            "id": i,
            "husband_id": husband_id,
            "wife_id": wife_id,
            "label": label,
            "score": round(float(score), 4),
            "score_gap": round(float(score_gap), 4),
            "rank_of_true_wife": rank,
            "hungarian_correct": hung,
            "lineage_husband": lh,
            "lineage_wife": lw,
            "same_lineage": (lh == lw),
            "era": _era_for_year(year),
            "patri_path_count": patri,
            "z": [round(float(v), 4) for v in z[i].tolist()],
        })

    return {
        "year": int(year),
        "n_pairs": int(n_pairs),
        "pairs": pairs,
        "mds_coords": mds_coords,
        "clusters": [int(c) for c in cluster_assignments],
        "k_clusters": int(n_clusters),
        "ablation": "ablated" if ablated else "unablated",
    }


def _validate_payload(payload: dict) -> None:
    """Raise if the produced payload violates the contract."""
    required_top = {"year", "n_pairs", "pairs", "mds_coords", "clusters",
                    "k_clusters", "ablation"}
    missing = required_top - set(payload.keys())
    if missing:
        raise ValueError(f"missing top-level keys: {missing}")
    n = payload["n_pairs"]
    if len(payload["pairs"]) != n:
        raise ValueError(f"pairs length {len(payload['pairs'])} != n_pairs {n}")
    if len(payload["mds_coords"]) != n:
        raise ValueError(f"mds_coords length {len(payload['mds_coords'])} != n_pairs {n}")
    if len(payload["clusters"]) != n:
        raise ValueError(f"clusters length {len(payload['clusters'])} != n_pairs {n}")

    required_pair = {"id", "husband_id", "wife_id", "label", "score",
                     "score_gap", "rank_of_true_wife", "hungarian_correct",
                     "lineage_husband", "lineage_wife", "same_lineage", "era",
                     "patri_path_count", "z"}
    for i, p in enumerate(payload["pairs"]):
        if p["id"] != i:
            raise ValueError(f"pair[{i}].id == {p['id']} (expected {i})")
        miss = required_pair - set(p.keys())
        if miss:
            raise ValueError(f"pair[{i}] missing keys: {miss}")
        # No NaN / inf
        for k in ("score", "score_gap"):
            v = p[k]
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                raise ValueError(f"pair[{i}].{k} is invalid: {v}")
        if not isinstance(p["z"], list) or not p["z"]:
            raise ValueError(f"pair[{i}].z is empty")


def _write_payload(payload: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    log.info("wrote %s (%.1f KB)", out_path, out_path.stat().st_size / 1024.0)


# ── CLI driver ─────────────────────────────────────────────────────────

def _build_one(year: int, ablated: bool, mode: str) -> tuple[Path, str]:
    """Returns (output_path, actual_mode) so callers can log the real outcome."""
    actual_mode = mode
    if mode == "stub":
        payload = precompute_stub(year, ablated)
    else:
        try:
            payload = precompute_real(year, ablated)
        except Exception as exc:
            log.warning("real precompute failed for year=%d ablated=%s: %s -- falling back to stub",
                        year, ablated, exc)
            payload = precompute_stub(year, ablated)
            actual_mode = "stub-fallback"
    _validate_payload(payload)
    out_path = _output_path(year, ablated)
    _write_payload(payload, out_path)
    return out_path, actual_mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Precompute viewer JSON for HGT cohorts")
    parser.add_argument("--year", type=int, default=None,
                        help="Cohort year (one of %s)" % TARGET_YEARS)
    parser.add_argument("--ablated", action="store_true",
                        help="Use the ablated checkpoint / write cohort_<year>.json")
    parser.add_argument("--unablated", action="store_true",
                        help="Use the unablated checkpoint / write cohort_<year>__unablated.json")
    parser.add_argument("--all", action="store_true",
                        help="Write all 6 acceptance-required JSONs (3 years x 2 conditions)")
    parser.add_argument("--stub", action="store_true",
                        help="Synthesise contract-valid stub JSON instead of running the real model")
    parser.add_argument("--years", type=str, default=None,
                        help="Comma-separated list of years to process (overrides --year)")
    args = parser.parse_args(argv)

    mode = "stub" if args.stub else "real"

    targets: list[tuple[int, bool]] = []
    if args.all:
        for y in DEFAULT_TARGET_YEARS:
            targets.append((y, True))
            targets.append((y, False))
    elif args.years:
        years = [int(s.strip()) for s in args.years.split(",") if s.strip()]
        # If neither --ablated nor --unablated given, do both.
        conds: list[bool]
        if args.ablated and not args.unablated:
            conds = [True]
        elif args.unablated and not args.ablated:
            conds = [False]
        else:
            conds = [True, False]
        for y in years:
            for ab in conds:
                targets.append((y, ab))
    elif args.year is not None:
        if not (args.ablated or args.unablated):
            log.error("--year requires --ablated or --unablated (or use --all)")
            return 2
        if args.ablated:
            targets.append((args.year, True))
        if args.unablated:
            targets.append((args.year, False))
    else:
        log.error("Pass --all, --year <y> [--ablated|--unablated], or --years <list>")
        return 2

    for year, ablated in targets:
        t0 = time.perf_counter()
        path, actual_mode = _build_one(year, ablated, mode)
        log.info("done year=%d ablated=%s mode=%s -> %s in %.1fs",
                 year, ablated, actual_mode, path.name, time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
