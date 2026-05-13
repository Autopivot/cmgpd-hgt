"""Test bootstrap: ensure `server.*` is importable when pytest is invoked from
either the repo root or the `viz-mas/` directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

_VIZ_MAS_ROOT = Path(__file__).resolve().parents[2]
if str(_VIZ_MAS_ROOT) not in sys.path:
    sys.path.insert(0, str(_VIZ_MAS_ROOT))
