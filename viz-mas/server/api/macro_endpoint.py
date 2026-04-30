"""GET /api/macro/{year} — grain-price + disaster-count macro context.

Reads raw DS0009 (.rda) directly so the frontend gets the full LOW/HIGH grain
range — averaging all 12 columns (as the cached parquet did) flattened the
signal. Disasters still use the parquet cache (event-counts only, no shape).

Payload: {years, grain_price (mean of 12), grain_low (min of LOW_*), grain_high
(max of HIGH_*), disaster_count}. If sources are missing the router still
mounts and routes return 503.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

# NEW/ on sys.path so `src.config` resolves regardless of launch cwd.
_NEW_ROOT = Path(__file__).resolve().parents[3]
if str(_NEW_ROOT) not in sys.path:
    sys.path.insert(0, str(_NEW_ROOT))

logger = logging.getLogger(__name__)

MIN_YEAR = 1749
MAX_YEAR = 1909

# Raw DS0009 location — primary source per user direction.
RAW_DS0009 = Path("D:/projects/cmgpd-hgt/data/raw/DS0009/27063-0009-Data.rda")

LOW_COLS = ["LOW_RICE", "LOW_HUSKED_MILLET", "LOW_UNHUSKED_MILLET",
            "LOW_SORGHUM", "LOW_WHEAT", "LOW_SOY"]
HIGH_COLS = ["HIGH_RICE", "HIGH_HUSKED_MILLET", "HIGH_UNHUSKED_MILLET",
             "HIGH_SORGHUM", "HIGH_WHEAT", "HIGH_SOY"]

router = APIRouter(prefix="/api")


def _load_grain_from_rda() -> pd.DataFrame | None:
    if not RAW_DS0009.exists():
        logger.warning("macro_endpoint: raw DS0009 .rda not found at %s", RAW_DS0009)
        return None
    try:
        import pyreadr
    except ImportError:
        logger.warning("macro_endpoint: pyreadr not installed; falling back to parquet")
        return None
    res = pyreadr.read_r(str(RAW_DS0009))
    df = res[next(iter(res.keys()))].copy()
    for c in LOW_COLS + HIGH_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            df.loc[df[c] == -99.0, c] = np.nan
    df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["YEAR"]).copy()
    df["YEAR"] = df["YEAR"].astype(int)

    df["grain_low"] = df[[c for c in LOW_COLS if c in df.columns]].min(axis=1, skipna=True)
    df["grain_high"] = df[[c for c in HIGH_COLS if c in df.columns]].max(axis=1, skipna=True)
    all_cols = [c for c in LOW_COLS + HIGH_COLS if c in df.columns]
    df["grain_price"] = df[all_cols].mean(axis=1, skipna=True)
    return df[["YEAR", "grain_price", "grain_low", "grain_high"]].sort_values("YEAR")


def _load_grain_fallback_parquet() -> pd.DataFrame | None:
    try:
        from src.config import GRAIN_PARQUET_PATH
    except Exception as exc:
        logger.warning("macro_endpoint: cannot import src.config (%s)", exc)
        return None
    p = Path(GRAIN_PARQUET_PATH)
    if not p.exists():
        return None
    df = pd.read_parquet(p)[["YEAR", "grain_price"]].copy()
    df["grain_low"] = df["grain_price"]
    df["grain_high"] = df["grain_price"]
    return df


def _load_disasters() -> pd.DataFrame | None:
    try:
        from src.config import DISASTER_PARQUET_PATH
    except Exception:
        return None
    p = Path(DISASTER_PARQUET_PATH)
    if not p.exists():
        return None
    return pd.read_parquet(p)[["YEAR", "disaster_count"]]


def _load_macro_table() -> pd.DataFrame | None:
    grain = _load_grain_from_rda()
    if grain is None:
        grain = _load_grain_fallback_parquet()
    disaster = _load_disasters()
    if grain is None or disaster is None:
        logger.warning(
            "macro_endpoint: source missing (grain=%s, disaster=%s) — /api/macro will 503",
            grain is not None, disaster is not None,
        )
        return None

    years = pd.RangeIndex(MIN_YEAR, MAX_YEAR + 1, name="YEAR")
    df = pd.DataFrame(index=years)
    df = df.join(grain.set_index("YEAR"), how="left")
    df = df.join(disaster.set_index("YEAR"), how="left")
    df["disaster_count"] = df["disaster_count"].fillna(0).astype(int)
    for c in ("grain_price", "grain_low", "grain_high"):
        df[c] = df[c].ffill().bfill().astype(float)
    return df.reset_index()


_macro_df: pd.DataFrame | None = _load_macro_table()


@router.get("/macro/{year}")
def get_macro(year: int, window: int = Query(10, ge=1, le=50)) -> dict:
    if _macro_df is None:
        raise HTTPException(status_code=503, detail="macro tables not loaded")
    if year < MIN_YEAR or year > MAX_YEAR:
        raise HTTPException(
            status_code=404,
            detail=f"year {year} out of range [{MIN_YEAR}, {MAX_YEAR}]",
        )

    win_years = list(range(year - window + 1, year + 1))
    sub = _macro_df.set_index("YEAR").reindex(win_years)
    sub["disaster_count"] = sub["disaster_count"].fillna(0).astype(int)
    for c in ("grain_price", "grain_low", "grain_high"):
        sub[c] = sub[c].ffill().bfill().astype(float)

    return {
        "years": win_years,
        "grain_price": [float(v) for v in sub["grain_price"].tolist()],
        "grain_low": [float(v) for v in sub["grain_low"].tolist()],
        "grain_high": [float(v) for v in sub["grain_high"].tolist()],
        "disaster_count": [int(v) for v in sub["disaster_count"].tolist()],
    }
