"""Within-cohort negative sampling.

For a man marrying in year t, draw k random women who also married in year t
and are not his actual wife. Cross-year negatives are too easy and would
inflate metrics; same-year sampling matches the bipartite-matching deployment.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Iterable

from . import config

PairList = list[tuple[int, int, int]]  # (h, w, year)


def build_year_to_women(pairs_by_year: dict[int, PairList]) -> dict[int, list[int]]:
    """Map year -> list of distinct wife indices observed in that cohort.

    Returns set semantics (deduped, first-seen order preserved) so downstream
    `women.index(w)` calls are unambiguous and the encoder doesn't waste
    compute on duplicate columns.
    """
    out: dict[int, list[int]] = defaultdict(list)
    for y, plist in pairs_by_year.items():
        for _, w, _ in plist:
            out[y].append(w)
    return {y: list(dict.fromkeys(ws)) for y, ws in out.items()}


def sample_negatives(
    year: int,
    true_wife: int,
    cohort_women: list[int],
    k: int = config.NEG_PER_POS,
    rng: random.Random | None = None,
) -> list[int]:
    """Sample `k` distinct non-spouse women from this year's cohort.

    Falls back to sampling-with-replacement when the cohort is too small.
    Returns `[]` when no valid candidate exists (i.e. cohort is just the true
    wife) — the previous behaviour `[true_wife] * k` corrupted training (BCE
    pushes σ(z)→1/(k+1) on the true positive) and biased eval AUC/log-loss.
    Both call sites tolerate an empty list.
    """
    rng = rng or random
    candidates = [w for w in cohort_women if w != true_wife]
    if not candidates:
        return []
    if len(candidates) >= k:
        return rng.sample(candidates, k)
    return [rng.choice(candidates) for _ in range(k)]


def iter_training_batches(
    train_pairs_by_year: dict[int, PairList],
    cohort_women_by_year: dict[int, list[int]],
    batch_years: int = config.BATCH_YEARS,
    neg_per_pos: int = config.NEG_PER_POS,
    rng: random.Random | None = None,
) -> Iterable[tuple[list[int], list[tuple[int, int, int, int]]]]:
    """Yield (year_batch, examples).

    examples is a list of (year, m, w, label) — labels: 1 for positive, 0 for negative.
    """
    rng = rng or random.Random(config.SEED)
    years = list(train_pairs_by_year.keys())
    rng.shuffle(years)

    for i in range(0, len(years), batch_years):
        chunk = years[i : i + batch_years]
        examples: list[tuple[int, int, int, int]] = []
        for y in chunk:
            cohort = cohort_women_by_year.get(y, [])
            for h, w, _ in train_pairs_by_year[y]:
                examples.append((y, h, w, 1))
                for neg_w in sample_negatives(y, w, cohort, k=neg_per_pos, rng=rng):
                    examples.append((y, h, neg_w, 0))
        if examples:
            yield chunk, examples
