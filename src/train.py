"""Training loop for the HGT marriage-edge predictor.

Per-epoch:
  shuffle training years; for each batch of BATCH_YEARS:
    for each year t:
      build subgraph_at_year(t, drop_pairs = train[t] ∪ all_val ∪ all_test)
      encode persons → score positives + within-cohort negatives → BCE loss
  validate (recall@1 with Hungarian) and checkpoint best model
"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from tqdm.auto import tqdm

from . import config
from .model import build_model
from .sampling import build_year_to_women, iter_training_batches
from .stage0_data import load_graph
from .stage2_split import ablate_maternal_edges, compute_cohort_split
from .stage3_temporal import subgraph_at_year

log = logging.getLogger(__name__)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _move_graph_to_device(graph, device):
    """Move all tensors in a HeteroData to a device."""
    for nt in graph.node_types:
        for k, v in list(graph[nt].items()):
            if torch.is_tensor(v):
                graph[nt][k] = v.to(device)
    for et in graph.edge_types:
        for k, v in list(graph[et].items()):
            if torch.is_tensor(v):
                graph[et][k] = v.to(device)
    return graph


def _score_pairs_chunked(
    scorer, h_m: torch.Tensor, h_w: torch.Tensor, chunk: int = 64,
) -> np.ndarray:
    """Score every (m, w) pair without materializing the full M*W*4H tensor.

    Iterates over men in chunks of `chunk`. For chunk=64 and W=2000 the peak
    intermediate is 64 * 2000 * 4 * HIDDEN floats ≈ 256 MB at HIDDEN=128 —
    well within budget on a 24 GB GPU even with the encoder still resident.
    """
    M, H = h_m.size(0), h_m.size(1)
    W = h_w.size(0)
    out = np.empty((M, W), dtype=np.float32)
    for s in range(0, M, chunk):
        e = min(s + chunk, M)
        h_m_blk = h_m[s:e]                                       # [c, H]
        c = h_m_blk.size(0)
        h_m_exp = h_m_blk.unsqueeze(1).expand(-1, W, -1).reshape(-1, H)
        h_w_exp = h_w.unsqueeze(0).expand(c, -1, -1).reshape(-1, H)
        logits = scorer(h_m_exp, h_w_exp).reshape(c, W)
        out[s:e] = logits.detach().cpu().numpy()
    return out


def _val_recall_at_1(
    hgt,
    scorer,
    val_pairs_by_year: dict,
    cohort_women_by_year: dict,
    base_graph,
    drop_pairs_global: set,
    device,
    pair_chunk: int = 64,
) -> tuple[float, int]:
    """Per-cohort Hungarian matching → recall@1 averaged over years."""
    from scipy.optimize import linear_sum_assignment

    hgt.eval()
    scorer.eval()
    if device == "cuda":
        torch.cuda.empty_cache()
    correct = 0
    total = 0
    with torch.no_grad():
        for t, pairs in val_pairs_by_year.items():
            women = cohort_women_by_year.get(t, [])
            men = [h for h, _, _ in pairs]
            true_w_for_man = {h: w for h, w, _ in pairs}
            if not men or not women:
                continue
            sg = subgraph_at_year(base_graph, t, drop_pairs=drop_pairs_global)
            sg = _move_graph_to_device(sg, device)
            h = hgt(sg)["person"]
            men_t = torch.tensor(men, device=device)
            women_t = torch.tensor(women, device=device)
            h_m = h[men_t]                         # [M, H]
            h_w = h[women_t]                       # [W, H]

            scores = _score_pairs_chunked(scorer, h_m, h_w, chunk=pair_chunk)
            del h, h_m, h_w, men_t, women_t
            if device == "cuda":
                torch.cuda.empty_cache()

            M, W = scores.shape
            cost = -scores
            if M != W:
                pad = np.full((max(M, W), max(M, W)), 1e6)
                pad[:M, :W] = cost
                cost = pad
            row_idx, col_idx = linear_sum_assignment(cost)
            for r, c in zip(row_idx, col_idx):
                if r >= M or c >= W:
                    continue
                if true_w_for_man.get(men[r]) == women[c]:
                    correct += 1
                total += 1
    if total == 0:
        return 0.0, 0
    return correct / total, total


def train(
    epochs: int = config.EPOCHS,
    lr: float = config.LR,
    weight_decay: float = config.WEIGHT_DECAY,
    batch_years: int = config.BATCH_YEARS,
    neg_per_pos: int = config.NEG_PER_POS,
    seed: int = config.SEED,
    device: str | None = None,
    smoke: bool = False,
    ablate: bool = True,
) -> Path:
    """Train and return path to best checkpoint.

    `ablate=True`  → train with r_ms/r_md zeroed (matches patrilineal-fracture
                     inference scenario). Saves to config.CKPT_ABLATED.
    `ablate=False` → train on the full graph (upper-bound model that has access
                     to maternal edges). Saves to config.CKPT_UNABLATED.

    The two checkpoints are NOT interchangeable: an ablated-trained model has
    untrained projections for r_ms/r_md, and reattaching those edges at
    inference produces noise rather than signal.
    """
    _set_seed(seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    log.info("device=%s  ablate=%s", device, ablate)

    log.info("loading graph from %s", config.GRAPH_CACHE_PATH)
    graph, _id_maps = load_graph()
    if ablate:
        ablate_maternal_edges(graph)
    else:
        log.info("training on UNABLATED graph: r_ms + r_md edges retained")
    split = compute_cohort_split(graph)

    train_by_year = split["train"]
    val_by_year = split["val"]
    all_val = split["all_val_pairs"]
    all_test = split["all_test_pairs"]
    cohort_women = build_year_to_women({**train_by_year, **val_by_year, **split["test"]})

    if smoke:
        # Restrict to a tight window to make the first run cheap.
        # Years must land in the right buckets per compute_cohort_split:
        # train ≤ TRAIN_END_YEAR (1855); val starts at 1856. 1852 was a bug
        # — it falls in the train bucket, leaving val_by_year empty and the
        # best-checkpoint selector inert.
        train_by_year = {y: p for y, p in train_by_year.items() if 1849 <= y <= 1851}
        val_by_year = {y: p for y, p in val_by_year.items() if y in (1856, 1857)}
        epochs = 2

    hgt, scorer = build_model(graph)
    hgt.to(device)
    scorer.to(device)
    params = list(hgt.parameters()) + list(scorer.parameters())
    log.info("params: %.2fM", sum(p.numel() for p in params) / 1e6)

    optim = AdamW(params, lr=lr, weight_decay=weight_decay)
    sched = CosineAnnealingLR(optim, T_max=max(epochs, 1))
    bce = nn.BCEWithLogitsLoss()
    # AMP/autocast disabled: pyg_lib.segment_matmul (used inside HGTConv) does
    # not accept mixed input dtypes, so wrapping the forward in autocast errors.

    config.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    best_path = config.CKPT_ABLATED if ablate else config.CKPT_UNABLATED
    best_recall = -1.0

    rng = random.Random(seed)

    for epoch in range(epochs):
        hgt.train()
        scorer.train()
        t0 = time.perf_counter()
        losses = []
        for chunk_years, examples in tqdm(
            list(iter_training_batches(
                train_by_year, cohort_women,
                batch_years=batch_years, neg_per_pos=neg_per_pos, rng=rng,
            )),
            desc=f"epoch {epoch + 1}/{epochs}",
        ):
            optim.zero_grad(set_to_none=True)
            year_loss = 0.0
            for t in chunk_years:
                year_examples = [e for e in examples if e[0] == t]
                if not year_examples:
                    continue
                drop = set(((h, w) for h, w, _ in train_by_year.get(t, []))) | all_val | all_test
                sg = subgraph_at_year(graph, t, drop_pairs=drop)
                sg = _move_graph_to_device(sg, device)

                x = hgt(sg)["person"]
                m_idx = torch.tensor([m for _, m, _, _ in year_examples], device=device)
                w_idx = torch.tensor([w for _, _, w, _ in year_examples], device=device)
                labels = torch.tensor(
                    [float(lbl) for *_, lbl in year_examples], device=device
                )
                logits = scorer(x[m_idx], x[w_idx])
                loss = bce(logits, labels)
                loss.backward()
                year_loss += loss.item()
            torch.nn.utils.clip_grad_norm_(params, config.GRAD_CLIP)
            optim.step()
            losses.append(year_loss)
        sched.step()

        # Free training-step intermediates before the heavier full-cohort
        # validation forward — otherwise the allocator's reserved (but
        # unallocated) blocks fragment the workspace and trigger OOM on
        # larger validation cohorts.
        if device == "cuda":
            torch.cuda.empty_cache()

        mean_loss = float(np.mean(losses)) if losses else float("nan")
        recall, n_val = _val_recall_at_1(
            hgt, scorer, val_by_year, cohort_women, graph,
            drop_pairs_global=all_val | all_test, device=device,
        )
        elapsed = time.perf_counter() - t0
        log.info(
            "epoch %d  loss=%.4f  val_recall@1=%.3f (n=%d)  %.1fs",
            epoch + 1, mean_loss, recall, n_val, elapsed,
        )

        if recall > best_recall:
            best_recall = recall
            torch.save(
                {
                    "hgt_state": hgt.state_dict(),
                    "scorer_state": scorer.state_dict(),
                    "val_recall@1": recall,
                    "epoch": epoch + 1,
                    "ablate": ablate,
                    "config_snapshot": {
                        "HIDDEN": config.HIDDEN, "NUM_LAYERS": config.NUM_LAYERS,
                        "HEADS": config.HEADS, "DROPOUT": config.DROPOUT,
                        "LR": config.LR, "WEIGHT_DECAY": config.WEIGHT_DECAY,
                        "NEG_PER_POS": config.NEG_PER_POS, "SEED": config.SEED,
                    },
                },
                str(best_path),
            )
            log.info("  saved checkpoint → %s (recall@1=%.3f)", best_path, recall)

    summary = {
        "best_val_recall@1": best_recall,
        "epochs_trained": epochs,
        "device": device,
    }
    log.info("training done: %s", json.dumps(summary))
    return best_path
