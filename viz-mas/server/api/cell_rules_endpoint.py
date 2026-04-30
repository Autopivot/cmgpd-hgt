"""Per-hex-cell rule profile persistence + REST.

The user calibrates rule weights against the 1882 cohort (full GT) and binds
the aggregate to a hex cell. In 1885+ (no GT), V6 loads the matching cell's
profile and feeds it into V5's MAS round-1 prompts as a soft prior.

Schema:
    {
      "cell_id": 17, "year": 1882, "n_husbands": 5,
      "weights": {
         "paternal_lineage_proximity": 0.7,
         "shared_siblings": 0.3,
         "same_household_history": 0.5,
         "same_banner": 0.4
      },
      "motifs_enabled": {
         "M01_direct_sibling": true,
         "M02_shared_father_via_fs_fd": true,
         "CTX_same_banner": false
      },
      "updated_at": "2026-05-01T12:34:56Z"
    }
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "cell_rules.json"
_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

_ALLOWED_WEIGHT_KEYS = {
    "paternal_lineage_proximity",
    "shared_siblings",
    "same_household_history",
    "same_banner",
}

_lock = threading.Lock()
_cache: dict[str, dict] = {}


def _key(cell_id: int, year: int) -> str:
    return f"{int(year)}|{int(cell_id)}"


def _load() -> None:
    if not _STORE_PATH.exists():
        return
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cell_rules: failed to load %s (%s)", _STORE_PATH, exc)
        return
    if isinstance(raw, dict):
        _cache.update(raw)
    logger.info("cell_rules: loaded %d profiles from %s", len(_cache), _STORE_PATH)


def _atomic_write() -> None:
    tmp = _STORE_PATH.with_suffix(_STORE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(_cache, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, _STORE_PATH)


_load()


class _CellRules(BaseModel):
    cell_id: int
    year: int
    n_husbands: int = 1
    weights: dict[str, float] = Field(default_factory=dict)
    motifs_enabled: dict[str, bool] = Field(default_factory=dict)
    updated_at: Optional[str] = None

    @field_validator("weights")
    @classmethod
    def _filter_weight_keys(cls, v: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, val in v.items():
            if k not in _ALLOWED_WEIGHT_KEYS:
                logger.warning("cell_rules: dropping unknown weight key %r", k)
                continue
            try:
                out[k] = float(val)
            except (TypeError, ValueError):
                logger.warning("cell_rules: non-numeric weight %r=%r dropped", k, val)
        return out


@router.get("/cell-rules/{cell_id}")
def get_cell_rules(cell_id: int, year: int = Query(1882)) -> dict:
    rec = _cache.get(_key(cell_id, year))
    if rec is None:
        raise HTTPException(404, f"no rule profile for cell {cell_id} year {year}")
    return rec


@router.post("/cell-rules/{cell_id}")
def post_cell_rules(cell_id: int, body: _CellRules) -> dict:
    if body.cell_id != cell_id:
        raise HTTPException(400, f"path cell_id={cell_id} does not match body {body.cell_id}")
    rec = body.model_dump()
    rec["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        _cache[_key(cell_id, body.year)] = rec
        _atomic_write()
    return rec


@router.get("/cell-rules")
def list_cell_rules() -> dict:
    bound = [
        {"cell_id": rec.get("cell_id"), "year": rec.get("year"), "updated_at": rec.get("updated_at")}
        for rec in _cache.values()
    ]
    return {"bound": bound}


@router.delete("/cell-rules/{cell_id}")
def delete_cell_rules(cell_id: int, year: int = Query(1882)) -> dict:
    k = _key(cell_id, year)
    with _lock:
        rec = _cache.pop(k, None)
        if rec is not None:
            _atomic_write()
    if rec is None:
        raise HTTPException(404, f"no rule profile for cell {cell_id} year {year}")
    return {"deleted": rec}
