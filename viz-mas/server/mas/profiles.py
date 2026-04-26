"""Person-profile lookup for the LLM agent prompts.

Loads the cleaned CMGPD-LN parquet on first access (~5 s) and caches
{PERSON_ID → profile dict} in memory. PERSON_ID strings appear in the
cohort JSONs as "Pxxx" (we strip the leading P here).
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CLEAN_PARQUET = ROOT.parent / "data" / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"

_lock = Lock()
_cache: dict[str, dict] = {}
_loaded = False


def _load():
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        log.info("loading person profiles from %s", CLEAN_PARQUET)
        try:
            import pandas as pd
            df = pd.read_parquet(CLEAN_PARQUET, columns=[
                "PERSON_ID", "SEX", "BIRTHYEAR", "REGION",
                "UNIQUE_VILLAGE_ID", "HOUSEHOLD_ID", "MARITAL_STATUS",
            ])
        except Exception as e:
            log.warning("Failed to load profile parquet (%s); profiles will be empty", e)
            _loaded = True
            return
        # CMGPD-LN: SEX 1=Female, 2=Male.
        for pid, group in df.groupby("PERSON_ID"):
            row = group.iloc[0]   # first observation; sex/banner usually constant
            try:
                _cache[str(pid)] = {
                    "id": str(pid),
                    "sex": "M" if int(row.get("SEX") or 0) == 2 else
                           "F" if int(row.get("SEX") or 0) == 1 else "?",
                    "birth_year": int(row["BIRTHYEAR"]) if pd_notna(row.get("BIRTHYEAR")) else None,
                    "banner_id": int(row["REGION"]) if pd_notna(row.get("REGION")) else None,
                    "community_id": int(row["UNIQUE_VILLAGE_ID"]) if pd_notna(row.get("UNIQUE_VILLAGE_ID")) else None,
                    "household_id": str(row["HOUSEHOLD_ID"]) if pd_notna(row.get("HOUSEHOLD_ID")) else None,
                }
            except Exception:
                continue
        _loaded = True
        log.info("profile cache populated: %d persons", len(_cache))


def pd_notna(v) -> bool:
    try:
        import pandas as pd
        return bool(pd.notna(v))
    except Exception:
        return v is not None


def get_profile(person_id: str) -> dict:
    """Return a profile dict; falls back to a minimal {id, sex='?'} record."""
    _load()
    # Cohort JSONs prefix with "P"; the parquet stores raw PERSON_ID.
    raw = person_id[1:] if person_id.startswith("P") else person_id
    p = _cache.get(raw)
    if p:
        return {**p, "id": person_id}      # echo the displayed "P..." form
    return {"id": person_id, "sex": "?", "birth_year": None,
            "banner_id": None, "community_id": None, "household_id": None}
