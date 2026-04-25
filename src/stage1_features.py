"""Stage 1: Feature engineering for node types.

Constructs per-node feature tensors following the plan §1.1–1.3:
  - PERSON: categorical embeddings + normalized continuous features
  - HOUSEHOLD: size, married couples, generations, head status, year
  - COMMUNITY: placeholder (population size)
  - BANNER: placeholder (one-hot or simple features)

Features are computed as snapshots at a given cutoff year.
"""

import logging
from collections import defaultdict

import numpy as np
import pandas as pd
import torch
from tqdm.auto import tqdm

from . import config

log = logging.getLogger(__name__)


# ── Categorical vocabulary builders ────────────────────────────────────

def build_vocab(series: pd.Series, max_size: int | None = None) -> dict:
    """Build value → int mapping from a pandas Series.
    Index 0 is reserved for unknown/missing.
    """
    counts = series.dropna().value_counts()
    if max_size is not None:
        counts = counts.head(max_size - 1)
    vocab = {"<UNK>": 0}
    for i, val in enumerate(
        tqdm(counts.index, desc="Building vocabulary", leave=False),
        start=1,
    ):
        vocab[val] = i
    return vocab


def encode_categorical(series: pd.Series, vocab: dict) -> torch.Tensor:
    """Encode a series using a vocabulary, returning LongTensor."""
    return torch.tensor(
        [vocab.get(v, 0) for v in series], dtype=torch.long
    )


# ── Person features ───────────────────────────────────────────────────

def build_person_features(
    df: pd.DataFrame,
    person_ids: list[str],
    cutoff_year: int = config.TEST_END_YEAR,
) -> dict:
    """Build person node features from the latest observation ≤ cutoff_year.

    Returns dict with:
      'continuous': FloatTensor [N, d_cont]   (z-score normalized)
      'sex': LongTensor [N]                   (0=unknown, 1=male, 2=female)
      'relationship': LongTensor [N]          (vocabulary-encoded)
      'occupational': FloatTensor [N, d_occ]  (binary flags)
      'birth_year': LongTensor [N]

    NOTE: MARITAL_STATUS is intentionally excluded — it is a posterior outcome
    that leaks the marriage label. See config.py for details.
    """
    pid_to_idx = {pid: i for i, pid in enumerate(person_ids)}
    N = len(person_ids)

    # Filter to observations up to cutoff and take the latest per person
    df_cut = df[df["YEAR"] <= cutoff_year].copy()
    df_latest = (
        df_cut.sort_values("YEAR")
        .groupby("PERSON_ID")
        .last()
        .reset_index()
    )

    # ── Load temporal indicator lookup (year → feature vector) ──
    from .temporal_indicators import build_temporal_indicator_table

    ti_table = build_temporal_indicator_table()
    ti_cols = config.TEMPORAL_INDICATOR_FEATURES
    ti_lookup: dict[int, list[float]] = {}
    for _, ti_row in ti_table.iterrows():
        ti_lookup[int(ti_row["YEAR"])] = [float(ti_row[c]) for c in ti_cols]

    # Person-level continuous features (exclude temporal indicators)
    person_cont_names = [
        c for c in config.CONTINUOUS_FEATURES
        if c not in config.TEMPORAL_INDICATOR_FEATURES
    ]
    ti_offset = len(person_cont_names)  # index where temporal cols start

    # ── Sex ──
    sex = torch.zeros(N, dtype=torch.long)
    # ── Continuous features ──
    cont_names = config.CONTINUOUS_FEATURES
    continuous = torch.zeros(N, len(cont_names), dtype=torch.float)
    # ── Occupational flags ──
    occ_names = config.OCCUPATIONAL_COLUMNS
    occupational = torch.zeros(N, len(occ_names), dtype=torch.float)
    # ── Categorical ──
    relationship_raw = ["<UNK>"] * N
    birth_years = torch.zeros(N, dtype=torch.long)

    for _, row in tqdm(
        df_latest.iterrows(),
        total=len(df_latest),
        desc="Building person features",
    ):
        pid = row["PERSON_ID"]
        if pid not in pid_to_idx:
            continue
        idx = pid_to_idx[pid]

        # Sex
        s = row.get("SEX")
        sex[idx] = int(s) if pd.notna(s) and int(s) in (1, 2) else 0

        # Person-level continuous features (indices 0..ti_offset-1)
        for j, col in enumerate(person_cont_names):
            val = row.get(col)
            continuous[idx, j] = float(val) if pd.notna(val) else 0.0

        # Temporal economic indicators (indices ti_offset..ti_offset+5)
        obs_year = row.get("YEAR")
        if pd.notna(obs_year):
            yr = int(obs_year)
            if yr in ti_lookup:
                for k, val in enumerate(ti_lookup[yr]):
                    continuous[idx, ti_offset + k] = val

        # Occupational (binary)
        for j, col in enumerate(occ_names):
            val = row.get(col)
            occupational[idx, j] = 1.0 if pd.notna(val) and float(val) > 0 else 0.0

        # Categorical
        rel = row.get("RELATIONSHIP")
        if pd.notna(rel):
            relationship_raw[idx] = str(rel)

        by = row.get("BIRTHYEAR")
        if pd.notna(by):
            birth_years[idx] = int(by)

    # Build vocabularies and encode
    rel_vocab = build_vocab(
        pd.Series(relationship_raw),
        max_size=config.CATEGORICAL_FEATURES["RELATIONSHIP"]["vocab_size"],
    )
    relationship = encode_categorical(pd.Series(relationship_raw), rel_vocab)

    # Z-score normalization on continuous features (plan §1.2)
    mask = continuous != 0  # non-missing
    for j in tqdm(
        range(continuous.size(1)),
        desc="Normalizing continuous features",
    ):
        col_vals = continuous[:, j]
        col_mask = mask[:, j]
        if col_mask.sum() > 1:
            mean = col_vals[col_mask].mean()
            std = col_vals[col_mask].std().clamp(min=1e-6)
            continuous[:, j] = torch.where(col_mask, (col_vals - mean) / std, col_vals)

    log.info("Person features: N=%d, cont=%d, occ=%d", N, len(cont_names), len(occ_names))

    return {
        "continuous": continuous,
        "sex": sex,
        "relationship": relationship,
        "occupational": occupational,
        "birth_year": birth_years,
        "vocabs": {"relationship": rel_vocab},
    }


# ── Household features ────────────────────────────────────────────────

def build_household_features(
    df: pd.DataFrame,
    household_ids: list[str],
    cutoff_year: int = config.TEST_END_YEAR,
) -> torch.Tensor:
    """Build household node features.

    Returns FloatTensor [N_hh, 5]:
      [household_size, num_married_couples, num_generations,
       head_has_position, last_observation_year_normalized]
    """
    hid_to_idx = {hid: i for i, hid in enumerate(household_ids)}
    N = len(household_ids)
    features = torch.zeros(N, 5, dtype=torch.float)

    df_cut = df[df["YEAR"] <= cutoff_year].copy()

    # Aggregate per household at their latest year
    for hid, group in tqdm(
        df_cut.groupby("HOUSEHOLD_ID"),
        total=df_cut["HOUSEHOLD_ID"].nunique(),
        desc="Building household features",
    ):
        if hid not in hid_to_idx:
            continue
        idx = hid_to_idx[hid]
        latest_year = group["YEAR"].max()
        snapshot = group[group["YEAR"] == latest_year]

        features[idx, 0] = len(snapshot)  # household size
        # Married individuals
        married = snapshot["MARITAL_STATUS"].dropna().apply(lambda x: int(x) == 2).sum()
        features[idx, 1] = married / 2  # approximate couples
        # Generations
        gens = snapshot["GENERATION"].dropna().nunique()
        features[idx, 2] = gens
        # Head has position
        head_rows = snapshot[snapshot["RELATIONSHIP"].astype(str).str.contains("head|Head", na=False)]
        if len(head_rows) > 0:
            pos = head_rows["POSITION"].fillna(0).max()
            features[idx, 3] = 1.0 if pos > 0 else 0.0
        # Year (normalized)
        features[idx, 4] = (latest_year - config.MIN_YEAR) / (config.TEST_END_YEAR - config.MIN_YEAR)

    log.info("Household features: N=%d", N)
    return features


# ── Community / Banner features ────────────────────────────────────────

def build_community_features(
    df: pd.DataFrame,
    community_ids: list[str],
) -> torch.Tensor:
    """Community features: [population_size_normalized]."""
    cid_to_idx = {cid: i for i, cid in enumerate(community_ids)}
    N = len(community_ids)
    features = torch.zeros(N, 1, dtype=torch.float)

    pop = df.groupby("UNIQUE_VILLAGE_ID")["PERSON_ID"].nunique()
    max_pop = pop.max() if len(pop) > 0 else 1

    for vid, count in tqdm(pop.items(), desc="Building community features"):
        vid_str = str(int(vid))
        if vid_str in cid_to_idx:
            features[cid_to_idx[vid_str], 0] = count / max_pop

    log.info("Community features: N=%d", N)
    return features


def build_banner_features(banner_ids: list[str]) -> torch.Tensor:
    """Banner features: one-hot encoding."""
    N = len(banner_ids)
    features = torch.eye(N, dtype=torch.float)
    log.info("Banner features: N=%d (one-hot)", N)
    return features


# ── Assemble all features into HeteroData ─────────────────────────────

def attach_features(data, df: pd.DataFrame, id_maps: dict, cutoff_year: int = config.TEST_END_YEAR):
    """Compute and attach all node features to the HeteroData object.

    Modifies data in-place. Returns the person feature dict (for vocabs).
    """
    person_ids = sorted(id_maps["person"], key=id_maps["person"].get)
    household_ids = sorted(id_maps["household"], key=id_maps["household"].get)
    community_ids = sorted(id_maps["community"], key=id_maps["community"].get)
    banner_ids = sorted(id_maps["banner"], key=id_maps["banner"].get)

    log.info("Building person features (cutoff=%d) …", cutoff_year)
    pf = build_person_features(df, person_ids, cutoff_year)

    # Concatenate all person features into a single tensor
    # sex one-hot (3 classes), relationship embed handled at model level.
    # Here we store raw indices + continuous.
    data["person"].x_continuous = pf["continuous"]
    data["person"].x_sex = pf["sex"]
    data["person"].x_relationship = pf["relationship"]
    data["person"].x_occupational = pf["occupational"]
    data["person"].birth_year = pf["birth_year"]

    log.info("Building household features …")
    data["household"].x = build_household_features(df, household_ids, cutoff_year)

    log.info("Building community features …")
    data["community"].x = build_community_features(df, community_ids)

    log.info("Building banner features …")
    data["banner"].x = build_banner_features(banner_ids)

    # ── Lookup tensors for HybridDecoder (Phase 1) ─────────────────────
    N_person = len(person_ids)
    community_id = torch.full((N_person,), -1, dtype=torch.long)
    banner_id = torch.full((N_person,), -1, dtype=torch.long)

    df_cut = df[df["YEAR"] <= cutoff_year].copy()
    df_latest = df_cut.sort_values("YEAR").groupby("PERSON_ID").last().reset_index()

    for _, row in tqdm(df_latest.iterrows(), total=len(df_latest),
                       desc="Building lookup tensors"):
        pid = row["PERSON_ID"]
        if pid not in id_maps["person"]:
            continue
        idx = id_maps["person"][pid]

        vid = row.get("UNIQUE_VILLAGE_ID")
        if pd.notna(vid):
            vid_str = str(int(vid))
            if vid_str in id_maps["community"]:
                community_id[idx] = id_maps["community"][vid_str]

        reg = row.get("REGION")
        if pd.notna(reg):
            reg_str = str(int(reg))
            if reg_str in id_maps["banner"]:
                banner_id[idx] = id_maps["banner"][reg_str]

    data["person"].community_id = community_id
    data["person"].banner_id = banner_id
    log.info("Lookup tensors: community_id coverage %.1f%%, banner_id coverage %.1f%%",
             100 * (community_id >= 0).float().mean().item(),
             100 * (banner_id >= 0).float().mean().item())

    log.info("All features attached.")
    return pf
