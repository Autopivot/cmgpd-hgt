"""Stage 0: Load CMGPD-LN .rda data and construct temporal heterogeneous graph.

Transforms the person-year panel into a PyG HeteroData object with:
  Node types: person, household, community, banner
  Edge types: r_hw, r_fs, r_ms, r_sib, r_hh, r_hc, r_cb
"""

import logging
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch_geometric.data import HeteroData
from tqdm.auto import tqdm

from . import config

log = logging.getLogger(__name__)

try:
    import pyreadr
except ImportError:
    pyreadr = None


def _normalize_id_series(series: pd.Series) -> pd.Series:
    """Normalize numeric-like IDs so PERSON_ID and spouse IDs share the same format."""
    normalized = series.astype(str).str.strip()
    normalized = normalized.str.replace(r"\.0+$", "", regex=True)
    normalized = normalized.replace({"nan": np.nan, "None": np.nan, "": np.nan, "<NA>": np.nan})
    return normalized


def _normalize_graph_input_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all identifier columns again before graph construction.

    This protects stage0 when the input DataFrame comes from an older cached parquet/csv
    that may have preserved IDs such as '12345.0'.
    """
    df = df.copy()
    id_cols = [
        "PERSON_ID",
        "MOTHER_ID",
        "FATHER_ID",
        "GRANDFATHER_ID",
        "WIFE_1_ID",
        "WIFE_2_ID",
        "HUSBAND_ID",
        "HOUSEHOLD_ID",
    ]
    for col in id_cols:
        if col in df.columns:
            df[col] = _normalize_id_series(df[col])
    return df


def _find_rscript() -> str | None:
    """Locate Rscript: prefer config.R_EXECUTABLE (env var or PATH), else None."""
    return config.R_EXECUTABLE


def _load_csv_cache(path: Path) -> pd.DataFrame:
    t0 = time.perf_counter()
    log.info("Loading raw CSV cache from %s", path)
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    log.info(
        "Loaded %d rows and %d columns from CSV cache in %.1fs",
        len(df),
        len(df.columns),
        time.perf_counter() - t0,
    )
    return df


def _export_rda_to_csv_with_r(input_path: Path, output_path: Path) -> None:
    rscript = _find_rscript()
    if rscript is None:
        raise RuntimeError("Rscript was not found on PATH and no fallback path was available.")
    if not config.R_EXPORT_SCRIPT_PATH.exists():
        raise RuntimeError(f"R export script not found: {config.R_EXPORT_SCRIPT_PATH}")

    cmd = [
        rscript,
        str(config.R_EXPORT_SCRIPT_PATH),
        str(input_path),
        str(output_path),
    ]
    log.info("Exporting %s to CSV cache via Rscript", input_path)
    t0 = time.perf_counter()
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    if completed.stdout.strip():
        log.info("R export output:\n%s", completed.stdout.strip())
    if completed.stderr.strip():
        log.warning("R export stderr:\n%s", completed.stderr.strip())
    log.info("R export finished in %.1fs", time.perf_counter() - t0)


def load_rda(path: Path | None = None) -> pd.DataFrame:
    """Load the ICPSR .rda file and return a cleaned DataFrame."""
    path = path or config.RAW_DATA_PATH
    csv_cache = config.RAW_CSV_CACHE_PATH
    csv_cache.parent.mkdir(parents=True, exist_ok=True)

    if csv_cache.exists():
        return _load_csv_cache(csv_cache)

    try:
        _export_rda_to_csv_with_r(path, csv_cache)
        return _load_csv_cache(csv_cache)
    except Exception as r_error:
        log.warning("R-based loader failed: %s", r_error)

    if pyreadr is None:
        raise RuntimeError(
            "Neither the R-based CSV export path nor pyreadr is available for loading the raw data."
        )

    log.info("Falling back to pyreadr for %s", path)
    t0 = time.perf_counter()
    result = pyreadr.read_r(str(path))
    key = next(iter(result.keys()))
    df = result[key]
    log.info(
        "Loaded %d rows and %d columns from key=%s in %.1fs",
        len(df),
        len(df.columns),
        key,
        time.perf_counter() - t0,
    )
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Decode R factors, replace ICPSR missing codes with NaN."""
    t0 = time.perf_counter()
    df = df.copy()

    for col in tqdm(df.columns, desc="Cleaning factor columns"):
        if hasattr(df[col], "cat"):
            df[col] = df[col].astype(str)

    missing_values = list(config.MISSING_CODES) + [str(code) for code in config.MISSING_CODES]
    df.replace(missing_values, np.nan, inplace=True)

    id_cols = [
        "PERSON_ID",
        "MOTHER_ID",
        "FATHER_ID",
        "GRANDFATHER_ID",
        "WIFE_1_ID",
        "WIFE_2_ID",
        "HUSBAND_ID",
        "HOUSEHOLD_ID",
    ]
    for col in tqdm(id_cols, desc="Normalizing ID columns"):
        if col in df.columns:
            df[col] = _normalize_id_series(df[col])

    numeric_cols = (
        [
            "YEAR",
            "SEX",
            "AGE_IN_SUI",
            "BIRTHYEAR",
            "MARITAL_STATUS",
            "GENERATION",
            "REGION",
            "DISTRICT",
            "UNIQUE_VILLAGE_ID",
        ]
        + config.CONTINUOUS_FEATURES
        + config.OCCUPATIONAL_COLUMNS
        + [
            "FATHER_ID_IMPUTED",
            "PRESENT",
            "DIED",
            "MARRIED_OUT",
            "REMARRIED_OUT",
            "NEXT_MARRY",
        ]
    )
    for col in tqdm(numeric_cols, desc="Coercing numeric columns"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    log.info("Cleaning complete. Shape=%s. Took %.1fs", df.shape, time.perf_counter() - t0)
    return df


def build_id_maps(df: pd.DataFrame) -> dict:
    """Build contiguous integer ID maps for each node type."""
    persons = sorted(df["PERSON_ID"].dropna().unique())
    households = sorted(df["HOUSEHOLD_ID"].dropna().unique())
    communities = sorted(df["UNIQUE_VILLAGE_ID"].dropna().unique().astype(int).astype(str))
    banners = sorted(df["REGION"].dropna().unique().astype(int).astype(str))

    maps = {
        "person": {pid: i for i, pid in enumerate(persons)},
        "household": {hid: i for i, hid in enumerate(households)},
        "community": {cid: i for i, cid in enumerate(communities)},
        "banner": {bid: i for i, bid in enumerate(banners)},
    }
    for key, value in maps.items():
        log.info("  %s: %d unique IDs", key, len(value))
    return maps


def _empty_edge_dict() -> dict:
    return {
        "edge_index": torch.zeros((2, 0), dtype=torch.long),
        "edge_time": torch.zeros((0,), dtype=torch.long),
    }


def build_marriage_edges(df: pd.DataFrame, id_map: dict) -> dict:
    """Detect marriage edges from status transitions and first observations."""
    pmap = id_map["person"]
    if not pmap:
        return _empty_edge_dict()

    df_sorted = df.sort_values(["PERSON_ID", "YEAR"]).copy()
    cols = ["PERSON_ID", "YEAR", "MARITAL_STATUS", "SEX", "WIFE_1_ID", "HUSBAND_ID"]
    marriage_df = df_sorted[cols].copy()
    marriage_df["prev_status"] = marriage_df.groupby("PERSON_ID")["MARITAL_STATUS"].shift()
    marriage_df["prev_year"] = marriage_df.groupby("PERSON_ID")["YEAR"].shift()

    # CMGPD SEX coding: 1 = Female, 2 = Male
    # Method 1: MARITAL_STATUS transitions (catches females coded as status→2)
    transition_mask = (
        marriage_df["prev_status"].notna()
        & marriage_df["MARITAL_STATUS"].notna()
        & marriage_df["SEX"].notna()
        & (marriage_df["MARITAL_STATUS"].astype("Int64") == 2)
        & (marriage_df["prev_status"].astype("Int64") != 2)
    )
    transition_rows = marriage_df.loc[transition_mask].copy()
    log.info("  marriage transition rows: %d", len(transition_rows))
    if not transition_rows.empty:
        sex_int = transition_rows["SEX"].astype(int)
        transition_rows["spouse_id"] = np.where(
            sex_int == 2,            # male (SEX=2) → WIFE_1_ID
            transition_rows["WIFE_1_ID"],
            transition_rows["HUSBAND_ID"],  # female (SEX=1) → HUSBAND_ID
        )
        transition_rows["marriage_year"] = (
            transition_rows["prev_year"].astype(np.int64) + transition_rows["YEAR"].astype(np.int64)
        ) // 2

    # Method 2: Already married at first observation (catches females with MARITAL_STATUS==2)
    first_obs = df_sorted.drop_duplicates("PERSON_ID", keep="first")[cols].copy()
    first_mask = (
        first_obs["MARITAL_STATUS"].notna()
        & first_obs["SEX"].notna()
        & (first_obs["MARITAL_STATUS"].astype("Int64") == 2)
    )
    first_rows = first_obs.loc[first_mask].copy()
    log.info("  first-observation married rows: %d", len(first_rows))
    if not first_rows.empty:
        first_sex = first_rows["SEX"].astype(int)
        first_rows["spouse_id"] = np.where(
            first_sex == 2,              # male (SEX=2) → WIFE_1_ID
            first_rows["WIFE_1_ID"],
            first_rows["HUSBAND_ID"],   # female (SEX=1) → HUSBAND_ID
        )
        first_rows["marriage_year"] = first_rows["YEAR"].astype(np.int64)

    # Method 3: Direct WIFE_1_ID presence for males (catches males whose MARITAL_STATUS != 2)
    male_spouse_df = (
        df_sorted[df_sorted["SEX"] == 2][["PERSON_ID", "YEAR", "WIFE_1_ID"]]
        .dropna(subset=["WIFE_1_ID"])
        .drop_duplicates("PERSON_ID", keep="first")
        .copy()
    )
    male_spouse_df["spouse_id"] = male_spouse_df["WIFE_1_ID"]
    male_spouse_df["SEX"] = 2
    male_spouse_df["marriage_year"] = male_spouse_df["YEAR"].astype(np.int64)
    log.info("  direct WIFE_1_ID rows (males): %d", len(male_spouse_df))

    candidates = pd.concat(
        [
            transition_rows[["PERSON_ID", "SEX", "spouse_id", "marriage_year"]],
            first_rows[["PERSON_ID", "SEX", "spouse_id", "marriage_year"]],
            male_spouse_df[["PERSON_ID", "SEX", "spouse_id", "marriage_year"]],
        ],
        ignore_index=True,
    )
    if candidates.empty:
        log.info("  r_hw edges: 0 marriages detected")
        return _empty_edge_dict()

    log.info("  marriage candidates before ID filtering: %d", len(candidates))
    candidates = candidates[
        candidates["PERSON_ID"].isin(pmap)
        & candidates["spouse_id"].notna()
        & candidates["spouse_id"].isin(pmap)
    ].copy()
    log.info("  marriage candidates after ID filtering: %d", len(candidates))
    if candidates.empty:
        log.info("  r_hw edges: 0 marriages detected")
        return _empty_edge_dict()

    candidates["pid_str"] = candidates["PERSON_ID"].astype(str)
    candidates["spouse_str"] = candidates["spouse_id"].astype(str)
    candidates["pair_key"] = np.where(
        candidates["pid_str"] <= candidates["spouse_str"],
        candidates["pid_str"] + "|" + candidates["spouse_str"],
        candidates["spouse_str"] + "|" + candidates["pid_str"],
    )
    candidates = candidates.sort_values("marriage_year").drop_duplicates("pair_key", keep="first")

    # Canonical direction for r_hw: src = husband (SEX=2), dst = wife (SEX=1)
    sex_int = candidates["SEX"].astype(int)
    candidates["src_id"] = np.where(sex_int == 2, candidates["PERSON_ID"], candidates["spouse_id"])
    candidates["dst_id"] = np.where(sex_int == 2, candidates["spouse_id"], candidates["PERSON_ID"])

    src = candidates["src_id"].map(pmap).astype(np.int64).to_numpy()
    dst = candidates["dst_id"].map(pmap).astype(np.int64).to_numpy()
    edge_time = candidates["marriage_year"].astype(np.int64).to_numpy()

    log.info("  r_hw edges: %d marriages detected", len(src))
    return {
        "edge_index": torch.tensor(np.vstack([src, dst]), dtype=torch.long),
        "edge_time": torch.tensor(edge_time, dtype=torch.long),
    }


def build_kinship_edges(df: pd.DataFrame, id_map: dict) -> dict:
    """Build parent→child and sibling edges, split by child SEX.

    CMGPD SEX coding: 1 = Female, 2 = Male.

    Returns:
      r_fs : father → son       (paternal, kept at inference)
      r_fd : father → daughter  (paternal, kept at inference)
      r_ms : mother → son       (maternal, ablated at inference)
      r_md : mother → daughter  (maternal, ablated at inference)
      r_sib: bidirectional siblings linked by shared father
    """
    pmap = id_map["person"]
    empty_keys = ["r_fs", "r_fd", "r_ms", "r_md", "r_sib"]
    if not pmap:
        return {k: _empty_edge_dict() for k in empty_keys}

    df_sorted = df.sort_values(["PERSON_ID", "YEAR"]).copy()
    person_sex = df_sorted.groupby("PERSON_ID")["SEX"].first()
    df_sorted["person_sex"] = df_sorted["PERSON_ID"].map(person_sex)
    # Deprioritize records where a female (SEX=1) is married (MARITAL_STATUS=2):
    # in those records FATHER_ID/MOTHER_ID refer to in-laws, not biological parents.
    df_sorted["parent_priority"] = np.where(
        (df_sorted["person_sex"] == 1) & (df_sorted["MARITAL_STATUS"].fillna(0).astype(int) == 2),
        1,
        0,
    )

    ref_rows = (
        df_sorted.sort_values(["PERSON_ID", "parent_priority", "YEAR"])
        .drop_duplicates("PERSON_ID", keep="first")
        .copy()
    )
    ref_rows = ref_rows[ref_rows["PERSON_ID"].isin(pmap)]

    birth_year = (
        df_sorted.dropna(subset=["BIRTHYEAR"])
        .drop_duplicates("PERSON_ID", keep="first")[["PERSON_ID", "BIRTHYEAR"]]
        .copy()
    )
    birth_year["BIRTHYEAR"] = birth_year["BIRTHYEAR"].astype(np.int64)
    birth_year_map = birth_year.set_index("PERSON_ID")["BIRTHYEAR"]

    # Helper: build {son, daughter} parent→child edge dicts from a parent column.
    def _split_parent_edges(parent_col: str) -> tuple[dict, dict, int]:
        sub = ref_rows[["PERSON_ID", parent_col, "person_sex"]].dropna(subset=[parent_col]).copy()
        sub[parent_col] = sub[parent_col].astype(str)
        sub = sub[sub[parent_col].isin(pmap)]
        n_unknown_sex = int(sub["person_sex"].isna().sum() + ((sub["person_sex"] != 1) & (sub["person_sex"] != 2)).sum())
        sub = sub[sub["person_sex"].isin([1, 2])]
        sub["birth_year"] = sub["PERSON_ID"].map(birth_year_map).fillna(config.MIN_YEAR).astype(np.int64)

        son = sub[sub["person_sex"] == 2]
        dau = sub[sub["person_sex"] == 1]

        def _to_edges(group: pd.DataFrame) -> dict:
            if group.empty:
                return _empty_edge_dict()
            src = group[parent_col].map(pmap).astype(np.int64).to_numpy()
            dst = group["PERSON_ID"].map(pmap).astype(np.int64).to_numpy()
            t = group["birth_year"].astype(np.int64).to_numpy()
            return {
                "edge_index": torch.tensor(np.vstack([src, dst]), dtype=torch.long),
                "edge_time": torch.tensor(t, dtype=torch.long),
            }

        return _to_edges(son), _to_edges(dau), n_unknown_sex

    fs_edges, fd_edges, n_drop_father = _split_parent_edges("FATHER_ID")
    ms_edges, md_edges, n_drop_mother = _split_parent_edges("MOTHER_ID")
    if n_drop_father or n_drop_mother:
        log.warning(
            "  dropped kinship edges with unknown child SEX: father=%d, mother=%d",
            n_drop_father, n_drop_mother,
        )

    # Sibling edges: pairs of children sharing a FATHER_ID. Use the full father
    # table (not gender-split) so brothers and sisters are linked.
    father_df = ref_rows[["PERSON_ID", "FATHER_ID"]].dropna().copy()
    father_df["FATHER_ID"] = father_df["FATHER_ID"].astype(str)
    father_df = father_df[father_df["FATHER_ID"].isin(pmap)]

    father_to_children: dict[str, list] = {}
    for father, group in tqdm(
        father_df.groupby("FATHER_ID"),
        total=father_df["FATHER_ID"].nunique(),
        desc="Grouping siblings by father",
    ):
        father_to_children[father] = group["PERSON_ID"].tolist()

    sib_src, sib_dst, sib_time = [], [], []
    for _, children in tqdm(father_to_children.items(), desc="Building sibling edges"):
        if len(children) < 2:
            continue
        for i in range(len(children)):
            c1 = children[i]
            for j in range(i + 1, len(children)):
                c2 = children[j]
                edge_year = max(
                    int(birth_year_map.get(c1, config.MIN_YEAR)),
                    int(birth_year_map.get(c2, config.MIN_YEAR)),
                )
                sib_src.extend([pmap[c1], pmap[c2]])
                sib_dst.extend([pmap[c2], pmap[c1]])
                sib_time.extend([edge_year, edge_year])

    sib_dict = (
        {
            "edge_index": torch.tensor([sib_src, sib_dst], dtype=torch.long),
            "edge_time": torch.tensor(sib_time, dtype=torch.long),
        }
        if sib_src
        else _empty_edge_dict()
    )

    log.info("  r_fs edges: %d", fs_edges["edge_index"].size(1))
    log.info("  r_fd edges: %d", fd_edges["edge_index"].size(1))
    log.info("  r_ms edges: %d", ms_edges["edge_index"].size(1))
    log.info("  r_md edges: %d", md_edges["edge_index"].size(1))
    log.info("  r_sib edges: %d", sib_dict["edge_index"].size(1))

    return {
        "r_fs": fs_edges,
        "r_fd": fd_edges,
        "r_ms": ms_edges,
        "r_md": md_edges,
        "r_sib": sib_dict,
    }


def build_membership_edges(df: pd.DataFrame, id_map: dict) -> dict:
    """Build person-household, household-community, and person-banner edges."""
    pmap = id_map["person"]
    hmap = id_map["household"]
    cmap = id_map["community"]
    bmap = id_map["banner"]

    hh_df = df[["PERSON_ID", "HOUSEHOLD_ID", "YEAR"]].dropna().copy()
    hh_df = hh_df[hh_df["PERSON_ID"].isin(pmap) & hh_df["HOUSEHOLD_ID"].isin(hmap)]
    hh_src = hh_df["PERSON_ID"].map(pmap).astype(np.int64).to_numpy()
    hh_dst = hh_df["HOUSEHOLD_ID"].map(hmap).astype(np.int64).to_numpy()
    hh_time = hh_df["YEAR"].astype(np.int64).to_numpy()

    hc_df = df[["HOUSEHOLD_ID", "UNIQUE_VILLAGE_ID"]].dropna().copy()
    hc_df["community_id"] = hc_df["UNIQUE_VILLAGE_ID"].astype(int).astype(str)
    hc_df = hc_df[hc_df["HOUSEHOLD_ID"].isin(hmap) & hc_df["community_id"].isin(cmap)]
    hc_df = hc_df.drop_duplicates("HOUSEHOLD_ID", keep="first")
    hc_src = hc_df["HOUSEHOLD_ID"].map(hmap).astype(np.int64).to_numpy()
    hc_dst = hc_df["community_id"].map(cmap).astype(np.int64).to_numpy()

    cb_df = (
        df.sort_values(["PERSON_ID", "YEAR"])
        .drop_duplicates("PERSON_ID", keep="first")[["PERSON_ID", "REGION"]]
        .dropna()
        .copy()
    )
    cb_df["banner_id"] = cb_df["REGION"].astype(int).astype(str)
    cb_df = cb_df[cb_df["PERSON_ID"].isin(pmap) & cb_df["banner_id"].isin(bmap)]
    cb_src = cb_df["PERSON_ID"].map(pmap).astype(np.int64).to_numpy()
    cb_dst = cb_df["banner_id"].map(bmap).astype(np.int64).to_numpy()

    log.info("  r_hh edges: %d", len(hh_src))
    log.info("  r_hc edges: %d", len(hc_src))
    log.info("  r_cb edges: %d", len(cb_src))

    return {
        "r_hh": {
            "edge_index": torch.tensor(np.vstack([hh_src, hh_dst]), dtype=torch.long)
            if len(hh_src)
            else torch.zeros((2, 0), dtype=torch.long),
            "edge_time": torch.tensor(hh_time, dtype=torch.long),
        },
        "r_hc": {
            "edge_index": torch.tensor(np.vstack([hc_src, hc_dst]), dtype=torch.long)
            if len(hc_src)
            else torch.zeros((2, 0), dtype=torch.long),
            "edge_time": torch.zeros(len(hc_src), dtype=torch.long),
        },
        "r_cb": {
            "edge_index": torch.tensor(np.vstack([cb_src, cb_dst]), dtype=torch.long)
            if len(cb_src)
            else torch.zeros((2, 0), dtype=torch.long),
            "edge_time": torch.zeros(len(cb_src), dtype=torch.long),
        },
    }


def build_graph(df: pd.DataFrame | None = None) -> tuple[HeteroData, dict, pd.DataFrame]:
    """Build the full temporal heterogeneous graph."""
    if df is None:
        df = clean_dataframe(load_rda())
    else:
        df = _normalize_graph_input_ids(df)

    t0 = time.perf_counter()
    log.info("Building ID maps")
    id_maps = build_id_maps(df)

    data = HeteroData()
    data["person"].num_nodes = len(id_maps["person"])
    data["household"].num_nodes = len(id_maps["household"])
    data["community"].num_nodes = len(id_maps["community"])
    data["banner"].num_nodes = len(id_maps["banner"])

    log.info("Building marriage edges")
    hw = build_marriage_edges(df, id_maps)
    data["person", "r_hw", "person"].edge_index = hw["edge_index"]
    data["person", "r_hw", "person"].edge_time = hw["edge_time"]

    log.info("Building kinship edges")
    kinship = build_kinship_edges(df, id_maps)
    for rel in ("r_fs", "r_fd", "r_ms", "r_md", "r_sib"):
        data["person", rel, "person"].edge_index = kinship[rel]["edge_index"]
        data["person", rel, "person"].edge_time = kinship[rel]["edge_time"]

    log.info("Building membership edges")
    membership = build_membership_edges(df, id_maps)
    data["person", "r_hh", "household"].edge_index = membership["r_hh"]["edge_index"]
    data["person", "r_hh", "household"].edge_time = membership["r_hh"]["edge_time"]
    data["household", "r_hc", "community"].edge_index = membership["r_hc"]["edge_index"]
    data["household", "r_hc", "community"].edge_time = membership["r_hc"]["edge_time"]
    data["person", "r_cb", "banner"].edge_index = membership["r_cb"]["edge_index"]
    data["person", "r_cb", "banner"].edge_time = membership["r_cb"]["edge_time"]

    log.info("Graph construction complete in %.1fs", time.perf_counter() - t0)
    log.info("  Nodes: %s", {k: data[k].num_nodes for k in config.NODE_TYPES})
    for et in config.EDGE_TYPES:
        edge_store = data[et]
        count = edge_store.edge_index.size(1) if edge_store.edge_index.numel() else 0
        log.info("  %s: %d edges", et[1], count)

    return data, id_maps, df


def save_graph(data: HeteroData, id_maps: dict, path: Path | None = None):
    """Persist HeteroData and ID maps to disk."""
    path = path or config.GRAPH_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Saving graph to %s", path)
    torch.save({"data": data, "id_maps": id_maps}, str(path))
    log.info("Graph saved to %s", path)


def load_graph(path: Path | None = None) -> tuple[HeteroData, dict]:
    """Load cached graph."""
    path = path or config.GRAPH_CACHE_PATH
    checkpoint = torch.load(str(path), weights_only=False)
    return checkpoint["data"], checkpoint["id_maps"]
