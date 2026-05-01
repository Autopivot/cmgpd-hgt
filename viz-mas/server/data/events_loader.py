"""DS0003 life-event + income loader for the V5 (Agent Arena) narrative agents.

DS0003 is the ICPSR 27063 supplement to CMGPD-LN that records discrete vital
events (births, deaths, marriages, migrations, ...) and an estimated annual
income per person-year. The negotiation pipeline grounds each Qwen persona in
the candidate's real life history; this module serves the cleaned, label-
substituted rows.

Loading strategy mirrors `src/stage0_data.py`:
    parquet cache → CSV cache → Rscript export → pyreadr fallback
On first call the resulting DataFrame is held in a module-level cache behind
a thread lock (mirrors `server/mas/profiles.py`). All public functions
degrade gracefully to safe empty values if the underlying data files are
missing — the rest of the pipeline must run in dev environments without
DS0003.
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
CSV_CACHE_PATH = _NEW_ROOT / "data" / "processed" / "ds0003" / "ds0003_raw_from_r.csv.gz"
PARQUET_CACHE_PATH = _NEW_ROOT / "data" / "processed" / "ds0003" / "ds0003_joined.parquet"
R_EXPORT_SCRIPT_PATH = _NEW_ROOT / "scripts" / "export_ds0003_rda.R"
R_EXECUTABLE = os.environ.get("R_EXECUTABLE") or shutil.which("Rscript")

# Columns kept from the raw DS0003 frame.
_KEEP_COLS = ["PERSON_ID", "YEAR", "EVENT_1", "EVENT_2", "ESTIMATED_INCOME"]

# Income bucket boundaries.
_LOW_Q, _HIGH_Q = 0.33, 0.66

# ── Module-level cache (thread-safe lazy load) ─────────────────────────
_lock = Lock()
_loaded = False
_df = None                          # pandas.DataFrame keyed by PERSON_ID (object), indexed for fast lookup
_event_labels: dict[str, dict[int, str]] = {}   # {"EVENT_1": {1: "Death", ...}, "EVENT_2": {...}}
_missing_codes: dict[str, int] = {}             # {"EVENT_1": -99, "EVENT_2": -99}
_income_low: float | None = None
_income_high: float | None = None


def _normalize_person_id(person_id: str) -> str:
    """Strip the leading 'P' that the rest of the codebase uses for display.

    DS0003 stores bare numeric PERSON_IDs; cohort JSONs prefix them with 'P'.
    """
    return person_id[1:] if person_id.startswith("P") else person_id


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
        # Keys are strings in JSON; convert to int for the in-memory map.
        decoded: dict[int, str] = {}
        for k, v in labels.items():
            try:
                decoded[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        _event_labels[col] = decoded
        # Per the JSON schema, missing_code is the integer used for "no event".
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


def _read_with_pyreadr():
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
    keep = [c for c in _KEEP_COLS if c in df.columns]
    return df[keep].copy()


def _load_dataframe():
    """Read DS0003 into a pandas DataFrame; return None if everything fails."""
    if PARQUET_CACHE_PATH.exists():
        log.info("Loading DS0003 from parquet cache %s", PARQUET_CACHE_PATH)
        try:
            return pd.read_parquet(PARQUET_CACHE_PATH)
        except Exception as exc:
            log.warning("Failed to read parquet cache (%s); regenerating", exc)

    if not CSV_CACHE_PATH.exists():
        _export_with_rscript()

    if CSV_CACHE_PATH.exists():
        log.info("Loading DS0003 raw CSV cache from %s", CSV_CACHE_PATH)
        try:
            df = pd.read_csv(CSV_CACHE_PATH, compression="gzip", low_memory=False)
        except Exception as exc:
            log.warning("Failed to read DS0003 CSV cache (%s)", exc)
            df = None
    else:
        df = None

    if df is None:
        df = _read_with_pyreadr()

    if df is None:
        log.warning("DS0003 unavailable: events_loader will return empty results")
        return None

    # Coerce expected dtypes; events / income are numeric, PERSON_ID is string.
    keep = [c for c in _KEEP_COLS if c in df.columns]
    df = df[keep].copy()
    df["PERSON_ID"] = df["PERSON_ID"].astype(str).str.strip().str.replace(r"\.0+$", "", regex=True)
    for col in ("YEAR", "EVENT_1", "EVENT_2", "ESTIMATED_INCOME"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Persist parquet for fast subsequent loads.
    try:
        PARQUET_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(PARQUET_CACHE_PATH, index=False)
        log.info("Wrote DS0003 parquet cache to %s", PARQUET_CACHE_PATH)
    except Exception as exc:
        log.warning("Could not write DS0003 parquet cache (%s); continuing without it", exc)

    return df


def _index_dataframe(df):
    """Sort by (PERSON_ID, YEAR) and set PERSON_ID as the index for fast .loc."""
    if df is None or len(df) == 0:
        return df
    df = df.sort_values(["PERSON_ID", "YEAR"], kind="mergesort")
    df = df.set_index("PERSON_ID", drop=False)
    df.index = df.index.astype(str)
    return df


def _compute_income_quantiles(df) -> tuple[float | None, float | None]:
    """Global 33rd/66th percentiles of non-null *positive* ESTIMATED_INCOME.

    DS0003 income is ≈98% zero — the historical convention is to record
    "no taxable income" as 0, not as missing. Including those zeros made
    both quantiles collapse to 0.0 and `_income_level` degenerated to a
    binary (every zero → 'low', every positive → 'high'), with 'mid'
    impossible. We now compute the cut-points over positive incomes only;
    zeros stay 'low' (their natural floor) and the positive distribution
    is partitioned into mid + high in 33%/33% slices.
    """
    if df is None or "ESTIMATED_INCOME" not in df.columns:
        return None, None
    series = df["ESTIMATED_INCOME"].dropna()
    if series.empty:
        return None, None
    pos = series[series > 0]
    if pos.empty:
        return None, None
    try:
        unique_pos = sorted(pos.unique())
        if len(unique_pos) < 2:
            v = float(unique_pos[0])
            return v, v + 1e-6
        # 33/66 quantiles fail catastrophically when the positive
        # distribution is dominated by a single value (DS0003 has 73% of
        # positives at 24.0). Fall back to median + 75th percentile so
        # 'mid' = positive-up-to-median, 'high' = above.
        low_cut = float(unique_pos[0])
        if low_cut > 0:
            low_cut = min(low_cut, float(pos.quantile(_LOW_Q)))
        high_cut = float(pos.quantile(_HIGH_Q))
        if high_cut <= low_cut:
            high_cut = float(pos.quantile(0.85))
        if high_cut <= low_cut:
            high_cut = float(unique_pos[-1])
        return low_cut, high_cut
    except Exception as exc:
        log.warning("Failed to compute DS0003 income quantiles (%s)", exc)
        return None, None


def _income_level_for(value: float) -> str:
    """Bucket ``value`` into 'low' (zero / very small), 'mid', 'high'.

    Fallback when quantiles couldn't be computed: return 'low' for zero,
    'mid' otherwise. Previously the no-quantile fallback returned 'mid'
    unconditionally, which mislabelled every all-zero income trajectory
    as 'mid' the moment ESTIMATED_INCOME column was empty or quantile
    computation failed.
    """
    if value is None:
        return "low"
    if value <= 0:
        return "low"
    if _income_low is None or _income_high is None:
        return "mid"
    if value < _income_low:
        return "low"
    if value > _income_high:
        return "high"
    return "mid"


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
    """Bucket a single income value into 'low' | 'mid' | 'high'.

    See `_compute_income_quantiles` for the cut-points (defined over
    positive incomes only so zero rows stay 'low' rather than collapsing
    every non-zero to 'high').
    """
    return _income_level_for(value)


def _person_rows(person_id: str, start_year: int, end_year: int):
    """Return the slice of rows for `person_id` within the year window, or None."""
    _ensure_loaded()
    if _df is None or len(_df) == 0:
        return None
    raw = _normalize_person_id(person_id)
    if raw not in _df.index:
        return None
    sub = _df.loc[[raw]]   # always returns a DataFrame even for single match
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
    """Return the earliest YEAR where EVENT_1 or EVENT_2 decodes to 'Birth'.

    Returns None if the person is not in DS0003 or has no Birth event.
    """
    _ensure_loaded()
    if _df is None or len(_df) == 0:
        return None
    raw = _normalize_person_id(person_id)
    if raw not in _df.index:
        return None
    # _index_dataframe sorts by (PERSON_ID, YEAR) ascending, so the first
    # Birth row encountered is the earliest.
    for _, row in _df.loc[[raw]].iterrows():
        if _decode_event("EVENT_1", row.get("EVENT_1")) != "Birth" and \
           _decode_event("EVENT_2", row.get("EVENT_2")) != "Birth":
            continue
        try:
            return int(row["YEAR"])
        except (KeyError, TypeError, ValueError):
            continue
    return None
