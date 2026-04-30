"""GET /api/macro/{year} — grain-price + disaster-count macro context.

Loaded once at import. Disasters.parquet is sparse (event-years only),
so missing rows are zero-filled; grain prices are forward/back-filled.
If parquets are missing the router still mounts and routes return 503.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

# NEW/ on sys.path so `src.config` resolves regardless of launch cwd.
_NEW_ROOT = Path(__file__).resolve().parents[3]
if str(_NEW_ROOT) not in sys.path:
    sys.path.insert(0, str(_NEW_ROOT))

logger = logging.getLogger(__name__)

MIN_YEAR = 1749
MAX_YEAR = 1909

router = APIRouter(prefix="/api")


def _load_macro_table() -> pd.DataFrame | None:
    try:
        from src.config import DISASTER_PARQUET_PATH, GRAIN_PARQUET_PATH
    except Exception as exc:  # pragma: no cover
        logger.warning("macro_endpoint: cannot import src.config (%s)", exc)
        return None

    grain_path = Path(GRAIN_PARQUET_PATH)
    disaster_path = Path(DISASTER_PARQUET_PATH)
    if not grain_path.exists() or not disaster_path.exists():
        logger.warning(
            "macro_endpoint: parquet missing (grain=%s, disaster=%s) — /api/macro will 503",
            grain_path.exists(), disaster_path.exists(),
        )
        return None

    grain = pd.read_parquet(grain_path)[["YEAR", "grain_price"]]
    disaster = pd.read_parquet(disaster_path)[["YEAR", "disaster_count"]]

    years = pd.RangeIndex(MIN_YEAR, MAX_YEAR + 1, name="YEAR")
    df = pd.DataFrame(index=years)
    df = df.join(grain.set_index("YEAR"), how="left")
    df = df.join(disaster.set_index("YEAR"), how="left")
    df["disaster_count"] = df["disaster_count"].fillna(0).astype(int)
    df["grain_price"] = df["grain_price"].ffill().bfill().astype(float)
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
    sub["grain_price"] = sub["grain_price"].ffill().bfill().astype(float)

    return {
        "years": win_years,
        "grain_price": [float(v) for v in sub["grain_price"].tolist()],
        "disaster_count": [int(v) for v in sub["disaster_count"].tolist()],
    }
