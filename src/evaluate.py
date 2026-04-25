"""Evaluation harness: pair-level + Hungarian-decoded metrics + sanity passes.

Given a trained checkpoint, computes:
  1. Pair-level: ROC-AUC, PR-AUC, log-loss on (positive, within-cohort negative) pairs.
  2. Per-cohort Hungarian matching: recall@1 (matched), recall@5 (per-man top-k),
     top-1 unconstrained accuracy.
  3. Diagnostic breakdowns: by cohort year, by family-tree size, by feature
     completeness, by banner.
  4. Sanity passes:
     a. predict the training cohort itself      (overfitting check)
     b. predict on the unablated graph          (upper bound; quantifies r_ms+r_md value)
     c. predict on the ablated graph            (main number)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from tqdm.auto import tqdm

from . import config
from .model import build_model
from .sampling import build_year_to_women, sample_negatives
from .stage0_data import load_graph
from .stage2_split import ablate_maternal_edges, compute_cohort_split
from .stage3_temporal import subgraph_at_year
from .train import _move_graph_to_device

log = logging.getLogger(__name__)


def _load_checkpoint(graph, ckpt_path: Path, device: str):
    state = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    hgt, scorer = build_model(graph)
    hgt.load_state_dict(state["hgt_state"])
    scorer.load_state_dict(state["scorer_state"])
    hgt.to(device).eval()
    scorer.to(device).eval()
    return hgt, scorer


def _score_cohort(
    hgt, scorer, sg, men: list[int], women: list[int], device,
    pair_chunk: int = 64,
) -> np.ndarray:
    """Encode the subgraph and score every (m, w) pair, chunking over men so
    the M*W*4*H intermediate doesn't OOM on large cohorts."""
    sg = _move_graph_to_device(sg, device)
    with torch.no_grad():
        x = hgt(sg)["person"]
        h_m = x[torch.tensor(men, device=device)]
        h_w = x[torch.tensor(women, device=device)]
        M, W = h_m.size(0), h_w.size(0)
        H = x.size(1)
        out = np.empty((M, W), dtype=np.float32)
        for s in range(0, M, pair_chunk):
            e = min(s + pair_chunk, M)
            h_m_blk = h_m[s:e]
            c = h_m_blk.size(0)
            h_m_exp = h_m_blk.unsqueeze(1).expand(-1, W, -1).reshape(-1, H)
            h_w_exp = h_w.unsqueeze(0).expand(c, -1, -1).reshape(-1, H)
            out[s:e] = scorer(h_m_exp, h_w_exp).reshape(c, W).detach().cpu().numpy()
    if device == "cuda":
        torch.cuda.empty_cache()
    return out


def _hungarian_recall(scores: np.ndarray, men: list[int], women: list[int],
                      true_w_for_man: dict[int, int]) -> tuple[int, int]:
    M, W = scores.shape
    cost = -scores
    if M != W:
        pad = np.full((max(M, W), max(M, W)), 1e6)
        pad[:M, :W] = cost
        cost = pad
    row_idx, col_idx = linear_sum_assignment(cost)
    correct = 0
    total = 0
    for r, c in zip(row_idx, col_idx):
        if r >= M or c >= W:
            continue
        if true_w_for_man.get(men[r]) == women[c]:
            correct += 1
        total += 1
    return correct, total


def _topk_recall(scores: np.ndarray, men: list[int], women: list[int],
                 true_w_for_man: dict[int, int], k: int) -> tuple[int, int]:
    correct = 0
    total = 0
    for r in range(scores.shape[0]):
        m = men[r]
        if m not in true_w_for_man:
            continue
        true_w = true_w_for_man[m]
        if true_w not in women:
            continue
        topk = np.argsort(-scores[r])[:k]
        if women.index(true_w) in topk.tolist():
            correct += 1
        total += 1
    return correct, total


def _evaluate_cohorts(
    hgt, scorer, base_graph, pairs_by_year: dict, cohort_women_by_year: dict,
    drop_pairs_global: set, device: str, label: str,
) -> dict:
    """Run per-cohort Hungarian + top-k + pair-level metrics."""
    pair_scores = []
    pair_labels = []
    h_correct = 0
    h_total = 0
    top1_correct = 0
    top1_total = 0
    top5_correct = 0
    top5_total = 0
    per_cohort = []
    rng = np.random.default_rng(config.SEED)

    for t, pairs in tqdm(pairs_by_year.items(), desc=f"eval[{label}]"):
        women = cohort_women_by_year.get(t, [])
        men = [h for h, _, _ in pairs]
        true_w_for_man = {h: w for h, w, _ in pairs}
        if not men or not women:
            continue
        sg = subgraph_at_year(base_graph, t, drop_pairs=drop_pairs_global)
        scores = _score_cohort(hgt, scorer, sg, men, women, device)

        # Pair-level: positive scores + neg_per_pos negatives per man (within-cohort)
        for r, m in enumerate(men):
            true_w = true_w_for_man[m]
            if true_w not in women:
                continue
            pos_idx = women.index(true_w)
            pair_scores.append(float(scores[r, pos_idx]))
            pair_labels.append(1)
            for neg_w in sample_negatives(t, true_w, women, k=config.NEG_PER_POS):
                pair_scores.append(float(scores[r, women.index(neg_w)]))
                pair_labels.append(0)

        h_c, h_t = _hungarian_recall(scores, men, women, true_w_for_man)
        h_correct += h_c
        h_total += h_t

        t1c, t1t = _topk_recall(scores, men, women, true_w_for_man, k=1)
        top1_correct += t1c
        top1_total += t1t
        t5c, t5t = _topk_recall(scores, men, women, true_w_for_man, k=5)
        top5_correct += t5c
        top5_total += t5t

        per_cohort.append({
            "year": int(t),
            "n_men": len(men),
            "n_women": len(women),
            "hungarian_recall@1": h_c / h_t if h_t else 0.0,
            "top1_recall": t1c / t1t if t1t else 0.0,
            "top5_recall": t5c / t5t if t5t else 0.0,
        })

    metrics: dict = {
        "label": label,
        "n_pairs_scored": len(pair_scores),
        "hungarian_recall@1": h_correct / h_total if h_total else 0.0,
        "top1_recall_unconstrained": top1_correct / top1_total if top1_total else 0.0,
        "top5_recall_unconstrained": top5_correct / top5_total if top5_total else 0.0,
    }
    if pair_scores and len(set(pair_labels)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(pair_labels, pair_scores))
        metrics["pr_auc"] = float(average_precision_score(pair_labels, pair_scores))
        # Sigmoid for log-loss
        prob = 1.0 / (1.0 + np.exp(-np.array(pair_scores)))
        prob = np.clip(prob, 1e-7, 1 - 1e-7)
        metrics["log_loss"] = float(log_loss(pair_labels, prob))
    return {"summary": metrics, "per_cohort": per_cohort}


def evaluate(
    ckpt_path: Path | None = None,
    device: str | None = None,
    smoke: bool = False,
    ablate: bool = True,
) -> Path:
    """Evaluate a single trained model on the graph distribution that matches
    its training condition.

    `ablate=True`  → load CKPT_ABLATED and run on the ablated graph (r_ms,
                     r_md zeroed). This is the primary patrilineal-fracture
                     scenario.
    `ablate=False` → load CKPT_UNABLATED and run on the full graph. The
                     upper-bound model that is allowed to use maternal edges.

    Comparing two metrics.json files produced by the two modes gives the
    PROPER ablation delta (gap between two correctly-trained models),
    unlike the previous behaviour which evaluated the same model on two
    graph variants — the latter is meaningless because the ablated model's
    r_ms/r_md projections are at random init.
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if ckpt_path is None:
        ckpt_path = config.CKPT_ABLATED if ablate else config.CKPT_UNABLATED
    log.info("loading graph + checkpoint (ablate=%s) ckpt=%s", ablate, ckpt_path)

    graph, _ = load_graph()
    if ablate:
        ablate_maternal_edges(graph)
    else:
        log.info("evaluating on UNABLATED graph: r_ms + r_md edges retained")

    split = compute_cohort_split(graph)
    train_by_year = split["train"]
    val_by_year = split["val"]
    test_by_year = split["test"]
    if smoke:
        train_by_year = {y: p for y, p in train_by_year.items() if 1849 <= y <= 1851}
        val_by_year = {y: p for y, p in val_by_year.items() if y == 1852}
        test_by_year = {y: p for y, p in test_by_year.items() if y in (1853, 1854)}
    cohort_women = build_year_to_women({**train_by_year, **val_by_year, **test_by_year})

    hgt, scorer = _load_checkpoint(graph, ckpt_path, device)

    drop_global = split["all_val_pairs"] | split["all_test_pairs"]

    log.info("== sanity: predict on training cohort ==")
    sanity_train = _evaluate_cohorts(
        hgt, scorer, graph, train_by_year, cohort_women,
        drop_pairs_global=drop_global, device=device, label="train",
    )

    log.info("== main: predict on test cohorts ==")
    test_metrics = _evaluate_cohorts(
        hgt, scorer, graph, test_by_year, cohort_women,
        drop_pairs_global=drop_global, device=device, label="test",
    )

    out = {
        "checkpoint": str(ckpt_path),
        "device": device,
        "smoke": smoke,
        "ablate": ablate,
        "sanity_train": sanity_train,
        "test": test_metrics,
    }

    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "ablated" if ablate else "unablated"
    run_dir = config.RUNS_DIR / f"{stamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))

    # Per-cohort CSV
    rows = []
    for label, block in [("train", sanity_train), ("test", test_metrics)]:
        for r in block["per_cohort"]:
            r2 = dict(r)
            r2["pass"] = label
            r2["ablate"] = ablate
            rows.append(r2)
    pd.DataFrame(rows).to_csv(run_dir / "per_cohort.csv", index=False)

    log.info("metrics written → %s", out_path)
    log.info(
        "summary: ablate=%s  test_recall@1=%.3f  test_roc_auc=%.3f",
        ablate,
        test_metrics["summary"]["hungarian_recall@1"],
        test_metrics["summary"].get("roc_auc", float("nan")),
    )
    return out_path
