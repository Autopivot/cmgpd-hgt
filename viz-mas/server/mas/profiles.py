"""Person-profile lookup for the LLM agent prompts.

Reads CMGPD-LN's cleaned DS0001 parquet for the per-person attributes (sex,
birth year, geographic region, household, village) and — when available —
joins DS0003's BANNER column (real Eight Banner affiliation, 1-8) keyed by
RECORD_NUMBER. Profiles are cached {PERSON_ID → dict} on first access.

The two location-ish fields are NOT the same thing:
    region_id  ∈ {1..4} — DS0001 REGION code (geographic district in Liaoning)
    banner_id  ∈ {1..8} — DS0003 BANNER code (Qing Eight Banners affiliation)
Both are surfaced separately, with English labels, so the persona prompt and
the V4 popup don't conflate "South Liaoning" with "Plain Blue Banner".
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CLEAN_PARQUET = ROOT.parent / "data" / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"
DS0003_JOINED_PARQUET = ROOT.parent / "data" / "processed" / "ds0003" / "ds0003_joined.parquet"

# DS0001 REGION codes (geographic district within Liaoning).
_REGION_LABELS: dict[int, str] = {
    1: "North Liaoning",
    2: "Central Liaoning",
    3: "South Central Liaoning",
    4: "South Liaoning",
}

# DS0003 BANNER codes (Qing Eight Banners affiliation, factor levels 1..8).
_BANNER_LABELS: dict[int, str] = {
    1: "Solid Yellow",
    2: "Bordered Yellow",
    3: "Solid White",
    4: "Bordered White",
    5: "Solid Blue",
    6: "Bordered Blue",
    7: "Solid Red",
    8: "Bordered Red",
}

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

        # ── Optional DS0003 BANNER enrichment ──
        # Take each person's modal (most-frequent) non-missing BANNER value.
        # Vectorised via value_counts → drop_duplicates(keep="first") so the
        # 1.5M-row groupby doesn't run a Python lambda per group on cold start.
        banner_by_person: dict[str, int] = {}
        if DS0003_JOINED_PARQUET.exists():
            try:
                banner_df = pd.read_parquet(
                    DS0003_JOINED_PARQUET, columns=["PERSON_ID", "BANNER"]
                )
                banner_df = banner_df.dropna(subset=["BANNER"])
                if not banner_df.empty:
                    banner_df["PERSON_ID"] = banner_df["PERSON_ID"].astype(str).str.replace(r"\.0+$", "", regex=True)
                    banner_df["BANNER"] = banner_df["BANNER"].astype(int)
                    counts = (banner_df.value_counts(["PERSON_ID", "BANNER"])
                                       .reset_index(name="_n")
                                       .sort_values(["PERSON_ID", "_n"], ascending=[True, False])
                                       .drop_duplicates("PERSON_ID", keep="first"))
                    banner_by_person = dict(zip(counts["PERSON_ID"], counts["BANNER"].astype(int)))
                    log.info("DS0003 banner enrichment ready for %d persons", len(banner_by_person))
            except Exception as exc:
                log.warning("Failed to load DS0003 banner enrichment (%s); banner_id will be None", exc)

        # CMGPD-LN: SEX 1=Female, 2=Male.
        for pid, group in df.groupby("PERSON_ID"):
            row = group.iloc[0]   # first observation; most attributes are stable per person
            try:
                pid_str = str(pid)
                region_id = int(row["REGION"]) if pd_notna(row.get("REGION")) else None
                banner_id = banner_by_person.get(pid_str)
                _cache[pid_str] = {
                    "id": pid_str,
                    "sex": "M" if int(row.get("SEX") or 0) == 2 else
                           "F" if int(row.get("SEX") or 0) == 1 else "?",
                    "birth_year": int(row["BIRTHYEAR"]) if pd_notna(row.get("BIRTHYEAR")) else None,
                    "banner_id": banner_id,
                    "banner_label": _BANNER_LABELS.get(banner_id) if banner_id is not None else None,
                    "region_id": region_id,
                    "region_label": _REGION_LABELS.get(region_id) if region_id is not None else None,
                    "community_id": int(row["UNIQUE_VILLAGE_ID"]) if pd_notna(row.get("UNIQUE_VILLAGE_ID")) else None,
                    "household_id": str(row["HOUSEHOLD_ID"]) if pd_notna(row.get("HOUSEHOLD_ID")) else None,
                }
            except Exception:
                continue
        _loaded = True
        log.info("profile cache populated: %d persons (with banner: %d)",
                 len(_cache), sum(1 for p in _cache.values() if p["banner_id"] is not None))


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
            "banner_id": None, "banner_label": None,
            "region_id": None, "region_label": None,
            "community_id": None, "household_id": None}
