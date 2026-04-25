"""Annual macro covariates per YEAR.

Builds a YEAR-keyed table from DS0009 (grain prices) and DS0011 (natural
disasters), forward-filled to cover [config.MIN_YEAR, config.MAX_YEAR]:

    YEAR | grain_price_z | grain_price_yoy | era_id | disaster_flag

Cached as parquet at config.GRAIN_PARQUET_PATH and config.DISASTER_PARQUET_PATH.
"""
from __future__ import annotations

import bisect
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)

# Grain price columns in DS0009: 6 grains × {LOW, HIGH}.
_GRAIN_COLS = [
    "LOW_RICE", "LOW_HUSKED_MILLET", "LOW_UNHUSKED_MILLET",
    "LOW_SORGHUM", "LOW_WHEAT", "LOW_SOY",
    "HIGH_RICE", "HIGH_HUSKED_MILLET", "HIGH_UNHUSKED_MILLET",
    "HIGH_SORGHUM", "HIGH_WHEAT", "HIGH_SOY",
]


def _load_rda_via_pyreadr(path: Path) -> pd.DataFrame:
    """Load a small auxiliary .rda directly via pyreadr.

    DS0009 / DS0011 are tiny (≤200 rows) so we don't bother with the R-script
    cache path used for DS0001.
    """
    try:
        import pyreadr
    except ImportError as e:
        raise RuntimeError(
            f"pyreadr is required to load {path}. Install via `pip install pyreadr`."
        ) from e
    if not path.exists():
        raise FileNotFoundError(f"Macro source not found: {path}")
    result = pyreadr.read_r(str(path))
    key = next(iter(result.keys()))
    return result[key]


def _load_grain_prices() -> pd.DataFrame:
    """DS0009 → DataFrame[YEAR, grain_price].

    Replaces -99.00 (missing) with NaN, then averages all 12 grain price
    columns per row.
    """
    cache = config.GRAIN_PARQUET_PATH
    if cache.exists():
        return pd.read_parquet(cache)
    df = _load_rda_via_pyreadr(config.RAW_GRAIN_PATH)
    df = df.copy()
    for c in _GRAIN_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            df.loc[df[c] == -99.00, c] = np.nan
    df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["YEAR"]).copy()
    df["YEAR"] = df["YEAR"].astype(int)

    avail = [c for c in _GRAIN_COLS if c in df.columns]
    df["grain_price"] = df[avail].mean(axis=1, skipna=True)

    out = df[["YEAR", "grain_price"]].sort_values("YEAR").reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache, index=False)
    log.info("DS0009 grain prices: %d rows, year range [%d, %d]",
             len(out), out["YEAR"].min(), out["YEAR"].max())
    return out


def _load_disasters() -> pd.DataFrame:
    """DS0011 → DataFrame[YEAR, disaster_count].

    Each row is an event; aggregate to per-year counts.
    """
    cache = config.DISASTER_PARQUET_PATH
    if cache.exists():
        return pd.read_parquet(cache)
    df = _load_rda_via_pyreadr(config.RAW_DISASTER_PATH)
    df = df.copy()
    df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["YEAR"]).copy()
    df["YEAR"] = df["YEAR"].astype(int)
    counts = df.groupby("YEAR").size().rename("disaster_count").reset_index()
    cache.parent.mkdir(parents=True, exist_ok=True)
    counts.to_parquet(cache, index=False)
    log.info("DS0011 disasters: %d distinct years with events, year range [%d, %d]",
             len(counts), counts["YEAR"].min(), counts["YEAR"].max())
    return counts


def _era_id(year: int) -> int:
    starts = [s for _, s, _ in config.DYNASTY_BOUNDARIES]
    eid = bisect.bisect_right(starts, year) - 1
    return max(eid, 0)


def build_temporal_indicator_table(years: Iterable[int] | None = None) -> pd.DataFrame:
    """Return a year-indexed table of macro covariates.

    Columns:
      YEAR, grain_price_z, grain_price_yoy, era_id, disaster_flag

    Forward-fills missing years so every YEAR in [MIN_YEAR, MAX_YEAR] is covered.
    The optional `years` argument is ignored for content (the full range is
    always built); kept for API compatibility with callers that pass it.
    """
    grain = _load_grain_prices()
    disasters = _load_disasters()

    full = pd.DataFrame({"YEAR": np.arange(config.MIN_YEAR, config.MAX_YEAR + 1, dtype=np.int64)})
    full = full.merge(grain, on="YEAR", how="left")
    full = full.merge(disasters, on="YEAR", how="left")

    # Coverage logging
    n_grain = full["grain_price"].notna().sum()
    n_disaster = full["disaster_count"].notna().sum()
    log.info(
        "Macro coverage in [%d, %d]: grain %d/%d years, disaster %d/%d years",
        config.MIN_YEAR, config.MAX_YEAR, n_grain, len(full), n_disaster, len(full),
    )

    # Forward-fill grain price; remaining NaN at the head of the series gets the
    # mean (z-score later treats it as 0).
    full["grain_price"] = full["grain_price"].ffill().bfill()

    mean = full["grain_price"].mean()
    std = full["grain_price"].std() or 1.0
    full["grain_price_z"] = (full["grain_price"] - mean) / std
    full["grain_price_yoy"] = full["grain_price"].diff().fillna(0.0)

    full["disaster_flag"] = (full["disaster_count"].fillna(0) > 0).astype(int)
    full["era_id"] = full["YEAR"].apply(_era_id).astype(int)

    out = full[["YEAR", "grain_price_z", "grain_price_yoy", "era_id", "disaster_flag"]].copy()

    if years is not None:
        wanted = set(int(y) for y in years)
        out = out[out["YEAR"].isin(wanted)].reset_index(drop=True)

    return out
