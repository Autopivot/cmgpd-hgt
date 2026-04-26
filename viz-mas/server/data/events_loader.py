"""DS0003 life-event + income loader for the V5 (Agent Arena) narrative agents.

DS0003 is the ICPSR 27063 supplement to CMGPD-LN. It records discrete vital
events (births, deaths, marriages, migrations, ...) and an estimated annual
income per person-year. The negotiation pipeline grounds each Qwen persona in
the candidate's real life history; this module serves the cleaned, label-
substituted rows.

Schema reality check
--------------------
DS0003 does **not** carry PERSON_ID or YEAR. It has 1,513,357 rows keyed by
``RECORD_NUMBER`` (zero-padded factor like ``"000000001"``) and the per-record
columns ``EVENT_1``, ``EVENT_2``, ``ESTIMATED_INCOME``. DS0001's cleaned
parquet has the same 1,513,357 rows with ``RECORD_NUMBER`` as a plain int
plus ``PERSON_ID`` / ``YEAR`` / ``BIRTHYEAR``. We join 1:1 on
``RECORD_NUMBER`` (after stripping DS0003's leading zeros) and persist the
joined frame as a parquet cache.

Loading strategy
----------------
On first call:
    1. If ``ds0003_joined.parquet`` exists, load it.
    2. Else build it: produce ``ds0003_raw_from_r.csv.gz`` via Rscript (or
       pyreadr fallback), read DS0001 columns, join, persist parquet.

The DataFrame is held in a module-level cache behind a thread lock (mirrors
``server/mas/profiles.py``). All public functions degrade gracefully to safe
empty values if the underlying data files are missing — the rest of the
pipeline must run in dev environments without DS0003.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────
# server/data/events_loader.py  →  parents[2] = viz-mas/, parents[3] = NEW/
_NEW_ROOT = Path(__file__).resolve().parents[3]

RDA_PATH = _NEW_ROOT / "data" / "raw" / "DS0003" / "27063-0003-Data.rda"
LABELS_PATH = _NEW_ROOT / "data" / "raw" / "DS0003" / "event_value_labels.json"
DS0001_PARQUET_PATH = _NEW_ROOT / "data" / "processed" / "hgt_pipeline" / "ds0001_clean.parquet"

CSV_CACHE_PATH = _NEW_ROOT / "data" / "processed" / "ds0003" / "ds0003_raw_from_r.csv.gz"
JOINED_PARQUET_PATH = _NEW_ROOT / "data" / "processed" / "ds0003" / "ds0003_joined.parquet"

R_EXPORT_SCRIPT_PATH = _NEW_ROOT / "scripts" / "export_ds0003_rda.R"
R_EXECUTABLE = os.environ.get("R_EXECUTABLE") or shutil.which("Rscript")

# Columns kept from DS0003 raw (R export already restricts to these four).
_DS0003_COLS = ["RECORD_NUMBER", "EVENT_1", "EVENT_2", "ESTIMATED_INCOME"]
# Columns pulled from DS0001 to attach person identity + observation year.
_DS0001_COLS = ["RECORD_NUMBER", "PERSON_ID", "YEAR", "BIRTHYEAR"]

# Income tertile boundaries. The raw distribution is ~98 % zeros, so tertiles
# of the full series collapse to 0/0; we compute thresholds over non-zero
# incomes only and treat zero as "low".
_LOW_Q, _HIGH_Q = 0.33, 0.66

# ── Module-level cache (thread-safe lazy load) ─────────────────────────
_lock = Lock()
_loaded = False
_df: Optional[pd.DataFrame] = None
_event_labels: dict[str, dict[int, str]] = {}
_missing_codes: dict[str, int] = {}
_income_low: float | None = None
_income_high: float | None = None


def _normalize_person_id(person_id: str) -> str:
    """Strip the leading 'P' that the rest of the codebase uses for display.

    DS0001 stores bare numeric PERSON_IDs; cohort JSONs prefix them with 'P'.
    """
    if person_id is None:
        return ""
    s = str(person_id).strip()
    return s[1:] if s.startswith("P") else s


def _load_labels() -> None:
    """Populate `_event_labels` and `_missing_codes` from event_value_labels.json."""
    global _event_labels, _missing_codes
    if not LABELS_PATH.exists():
        log.warning("DS0003 event_value_labels.json missing at %s; events will be unlabeled", LABELS_PATH)
        return
    try:
        with LABELS_PATH.open("r", encoding="utf-8") as f:
            blob = json.load(f)
    except Exception as exc:
        log.warning("Failed to parse %s (%s); events will be unlabeled", LABELS_PATH, exc)
        return

    for col in ("EVENT_1", "EVENT_2"):
        section = blob.get(col, {})
        labels = section.get("labels", {})
        decoded: dict[int, str] = {}
        for k, v in labels.items():
            try:
                decoded[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        _event_labels[col] = decoded
        try:
            _missing_codes[col] = int(section.get("missing_code", -99))
        except (TypeError, ValueError):
            _missing_codes[col] = -99


def _export_with_rscript() -> bool:
    """Run the R script to produce the gzip CSV cache. Returns True on success."""
    if R_EXECUTABLE is None:
        log.info("Rscript not on PATH; skipping R export step for DS0003")
        return False
    if not R_EXPORT_SCRIPT_PATH.exists():
        log.warning("DS0003 R export script not found: %s", R_EXPORT_SCRIPT_PATH)
        return False
    if not RDA_PATH.exists():
        log.warning("DS0003 .rda not found at %s", RDA_PATH)
        return False
    CSV_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cmd = [R_EXECUTABLE, str(R_EXPORT_SCRIPT_PATH), str(RDA_PATH), str(CSV_CACHE_PATH)]
    log.info("Exporting DS0003 to CSV cache via Rscript: %s", " ".join(cmd))
    t0 = time.perf_counter()
    try:
        completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        log.warning("Rscript export failed: %s", exc)
        return False
    if completed.stdout.strip():
        log.info("R export output:\n%s", completed.stdout.strip())
    if completed.stderr.strip():
        log.info("R export stderr:\n%s", completed.stderr.strip())
    log.info("R export finished in %.1fs", time.perf_counter() - t0)
    return True


def _read_with_pyreadr() -> Optional[pd.DataFrame]:
    """pyreadr fallback — reads the .rda directly. Returns DataFrame or None."""
    try:
        import pyreadr
    except ImportError:
        log.warning("pyreadr not installed; cannot fall back to direct .rda read")
        return None
    if not RDA_PATH.exists():
        log.warning("DS0003 .rda not found at %s", RDA_PATH)
        return None
    log.info("Falling back to pyreadr for %s", RDA_PATH)
    try:
        result = pyreadr.read_r(str(RDA_PATH))
    except Exception as exc:
        log.warning("pyreadr failed to read %s: %s", RDA_PATH, exc)
        return None
    key = next(iter(result.keys()))
    df = result[key]
    missing = [c for c in _DS0003_COLS if c not in df.columns]
    if missing:
        log.warning("pyreadr DS0003 frame missing columns %s", missing)
        return None
    # RECORD_NUMBER is a categorical with zero-padded labels; pd.to_numeric
    # parses "000000001" -> 1 directly. EVENT_1/2 are labelled categoricals
    # like "(1) Death" — extract the leading code so the result matches the
    # R-CSV schema.
    out = pd.DataFrame({
        "RECORD_NUMBER": pd.to_numeric(df["RECORD_NUMBER"].astype(str), errors="coerce").astype("Int64"),
        "ESTIMATED_INCOME": pd.to_numeric(df["ESTIMATED_INCOME"], errors="coerce"),
    })
    for col in ("EVENT_1", "EVENT_2"):
        codes = df[col].astype(str).str.extract(r"^\(([0-9-]+)\)", expand=False)
        out[col] = pd.to_numeric(codes, errors="coerce").fillna(-99).astype("int64")
    return out[_DS0003_COLS]


def _read_ds0003_raw() -> Optional[pd.DataFrame]:
    """Get the cleaned DS0003 frame (RECORD_NUMBER int + events + income)."""
    if not CSV_CACHE_PATH.exists():
        _export_with_rscript()

    if CSV_CACHE_PATH.exists():
        log.info("Loading DS0003 raw CSV cache from %s", CSV_CACHE_PATH)
        try:
            df = pd.read_csv(CSV_CACHE_PATH, compression="gzip", low_memory=False)
            return df[_DS0003_COLS].copy()
        except Exception as exc:
            log.warning("Failed to read DS0003 CSV cache (%s); falling back to pyreadr", exc)

    return _read_with_pyreadr()


def _read_ds0001_keys() -> Optional[pd.DataFrame]:
    """Read PERSON_ID / YEAR / BIRTHYEAR keyed by RECORD_NUMBER from DS0001."""
    if not DS0001_PARQUET_PATH.exists():
        log.warning("DS0001 parquet not found at %s; cannot join DS0003", DS0001_PARQUET_PATH)
        return None
    try:
        return pd.read_parquet(DS0001_PARQUET_PATH, columns=_DS0001_COLS)
    except Exception as exc:
        log.warning("Failed to read DS0001 parquet (%s)", exc)
        return None


def _build_joined_dataframe() -> Optional[pd.DataFrame]:
    """Build the DS0003-joined frame from raw sources and persist a parquet cache."""
    ds0003 = _read_ds0003_raw()
    if ds0003 is None:
        return None
    ds0001 = _read_ds0001_keys()
    if ds0001 is None:
        return None

    ds0003["RECORD_NUMBER"] = pd.to_numeric(ds0003["RECORD_NUMBER"], errors="coerce").astype("Int64")
    ds0001["RECORD_NUMBER"] = pd.to_numeric(ds0001["RECORD_NUMBER"], errors="coerce").astype("Int64")
    joined = ds0001.merge(ds0003, on="RECORD_NUMBER", how="inner")
    log.info(
        "DS0003 joined to DS0001 on RECORD_NUMBER: %d rows (DS0001=%d, DS0003=%d)",
        len(joined), len(ds0001), len(ds0003),
    )
    joined["PERSON_ID"] = joined["PERSON_ID"].astype(str).str.strip()
    joined["YEAR"] = pd.to_numeric(joined["YEAR"], errors="coerce").astype("Int64")
    joined["BIRTHYEAR"] = pd.to_numeric(joined["BIRTHYEAR"], errors="coerce")
    for col in ("EVENT_1", "EVENT_2"):
        joined[col] = pd.to_numeric(joined[col], errors="coerce").fillna(-99).astype("int64")
    joined["ESTIMATED_INCOME"] = pd.to_numeric(joined["ESTIMATED_INCOME"], errors="coerce")

    try:
        JOINED_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
        joined.to_parquet(JOINED_PARQUET_PATH, index=False)
        log.info("Wrote DS0003 joined parquet cache to %s", JOINED_PARQUET_PATH)
    except Exception as exc:
        log.warning("Could not write DS0003 joined parquet (%s); continuing without it", exc)

    return joined


def _load_dataframe() -> Optional[pd.DataFrame]:
    """Read the joined DS0003+DS0001 frame; build it if missing."""
    if JOINED_PARQUET_PATH.exists():
        log.info("Loading DS0003 joined frame from %s", JOINED_PARQUET_PATH)
        try:
            return pd.read_parquet(JOINED_PARQUET_PATH)
        except Exception as exc:
            log.warning("Failed to read joined parquet (%s); rebuilding", exc)
    return _build_joined_dataframe()


def _index_dataframe(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Sort by (PERSON_ID, YEAR) and set PERSON_ID as the index for fast .loc."""
    if df is None or len(df) == 0:
        return df
    df = df.sort_values(["PERSON_ID", "YEAR"], kind="mergesort")
    df = df.set_index("PERSON_ID", drop=False)
    df.index = df.index.astype(str)
    return df


def _compute_income_quantiles(df: Optional[pd.DataFrame]) -> tuple[float | None, float | None]:
    """Tertile boundaries over **non-zero** ESTIMATED_INCOME.

    The full distribution is ~98 % zeros, so quantiles of the raw series
    collapse to 0/0. We compute thresholds over positive incomes only;
    `_income_level` then routes income == 0 (and anything <= q33) to "low".
    """
    if df is None or "ESTIMATED_INCOME" not in df.columns:
        return None, None
    series = df["ESTIMATED_INCOME"].dropna()
    nonzero = series[series > 0]
    if nonzero.empty:
        return None, None
    try:
        return float(nonzero.quantile(_LOW_Q)), float(nonzero.quantile(_HIGH_Q))
    except Exception as exc:
        log.warning("Failed to compute DS0003 income quantiles (%s)", exc)
        return None, None


def _ensure_loaded() -> None:
    """Lazy-load the DataFrame, labels, and quantile thresholds. Idempotent."""
    global _loaded, _df, _income_low, _income_high
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _load_labels()
        df = _load_dataframe()
        _df = _index_dataframe(df)
        _income_low, _income_high = _compute_income_quantiles(_df)
        _loaded = True
        n = 0 if _df is None else len(_df)
        log.info("DS0003 events_loader cache populated: %d rows", n)


def _income_level(value: float) -> str:
    """Bucket a single income value into 'low' | 'mid' | 'high'."""
    if _income_low is None or _income_high is None:
        return "mid"
    if value <= _income_low:
        return "low"
    if value >= _income_high:
        return "high"
    return "mid"


def _person_rows(person_id: str, start_year: int, end_year: int) -> Optional[pd.DataFrame]:
    """Return the slice of rows for `person_id` within the year window, or None."""
    _ensure_loaded()
    if _df is None or len(_df) == 0:
        return None
    raw = _normalize_person_id(person_id)
    if raw not in _df.index:
        return None
    sub = _df.loc[[raw]]
    if "YEAR" in sub.columns:
        sub = sub[(sub["YEAR"] >= start_year) & (sub["YEAR"] <= end_year)]
    if sub.empty:
        return None
    return sub


def _decode_event(col: str, raw_value) -> Optional[str]:
    """Look up the English label for an EVENT_1/EVENT_2 cell. Returns None for missing."""
    if raw_value is None or pd.isna(raw_value):
        return None
    try:
        code = int(raw_value)
    except (TypeError, ValueError):
        return None
    if code == _missing_codes.get(col, -99):
        return None
    return _event_labels.get(col, {}).get(code)


# ── Public API ─────────────────────────────────────────────────────────
def load_events(person_id: str, start_year: int, end_year: int) -> list[dict]:
    """Return per-year life events with English labels.

    Each entry is ``{"year": int, "event_1": str|None, "event_2": str|None}``.
    Sorted by year ascending. Empty list if the person is not in DS0003 or
    has no events in [start_year, end_year]. Never raises.
    """
    sub = _person_rows(person_id, start_year, end_year)
    if sub is None:
        return []
    out: list[dict] = []
    for _, row in sub.iterrows():
        e1 = _decode_event("EVENT_1", row.get("EVENT_1"))
        e2 = _decode_event("EVENT_2", row.get("EVENT_2"))
        if e1 is None and e2 is None:
            continue
        try:
            year = int(row["YEAR"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"year": year, "event_1": e1, "event_2": e2})
    out.sort(key=lambda r: r["year"])
    return out


def load_income(person_id: str, start_year: int, end_year: int) -> list[dict]:
    """Return per-year ``ESTIMATED_INCOME`` plus a precomputed bucket level.

    Each entry is ``{"year": int, "income": float, "level": "low"|"mid"|"high"}``.
    Sorted by year ascending. Empty list if the person is not in DS0003 or
    has no non-null income rows in the window.
    """
    sub = _person_rows(person_id, start_year, end_year)
    if sub is None or "ESTIMATED_INCOME" not in sub.columns:
        return []
    out: list[dict] = []
    for _, row in sub.iterrows():
        value = row.get("ESTIMATED_INCOME")
        if value is None or pd.isna(value):
            continue
        try:
            year = int(row["YEAR"])
            income = float(value)
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"year": year, "income": income, "level": _income_level(income)})
    out.sort(key=lambda r: r["year"])
    return out


def get_birth_year(person_id: str) -> int | None:
    """Return the BIRTHYEAR for this PERSON_ID, or None if unknown.

    BIRTHYEAR is sourced from DS0001 (it is constant across that person's
    rows), so we just take the first non-null value.
    """
    _ensure_loaded()
    if _df is None or len(_df) == 0:
        return None
    raw = _normalize_person_id(person_id)
    if raw not in _df.index:
        return None
    rows = _df.loc[[raw]]
    if "BIRTHYEAR" not in rows.columns:
        return None
    series = rows["BIRTHYEAR"].dropna()
    if series.empty:
        return None
    try:
        return int(series.iloc[0])
    except (TypeError, ValueError):
        return None
