"""Properly compare an ablated-trained model against an unablated-trained model.

Workflow (after both trainings have completed):

    python -m src.main --stage train               # produces best_ablated.pt
    python -m src.main --stage train --no-ablate   # produces best_unablated.pt
    python -m src.main --stage eval                # runs/<ts>_ablated/metrics.json
    python -m src.main --stage eval --no-ablate    # runs/<ts>_unablated/metrics.json
    python scripts/compare_ablation.py             # this script

Reads the most recent `metrics.json` from each mode in `runs/` and computes
the delta in test Hungarian recall@1 (and other metrics). Writes a
`comparison.json` and a small markdown summary alongside.

This is the diagnostic the previous broken `ablation_delta_recall@1` was
TRYING to be — but failed because it evaluated a single ablated-trained
model on both graph variants. An ablated-trained model has untrained
projections for r_ms/r_md, so reattaching those edges at inference is
noise rather than signal.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402


def _latest(suffix: str) -> Path | None:
    candidates = sorted(config.RUNS_DIR.glob(f"*_{suffix}"))
    if not candidates:
        return None
    # Pick the one with metrics.json
    for p in reversed(candidates):
        if (p / "metrics.json").exists():
            return p / "metrics.json"
    return None


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _delta(a: dict, b: dict, key: str) -> float:
    return float(b.get(key, 0.0)) - float(a.get(key, 0.0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablated",   type=Path, default=None,
                    help="metrics.json from --no-ablate=False run (default: latest)")
    ap.add_argument("--unablated", type=Path, default=None,
                    help="metrics.json from --no-ablate run (default: latest)")
    ap.add_argument("--out", type=Path, default=None,
                    help="output dir for comparison.json/.md (default: runs/<ts>_compare)")
    args = ap.parse_args()

    abl_path = args.ablated   or _latest("ablated")
    una_path = args.unablated or _latest("unablated")
    if abl_path is None:
        sys.exit("no ablated metrics found; run `python -m src.main --stage eval`")
    if una_path is None:
        sys.exit("no unablated metrics found; run `python -m src.main --stage eval --no-ablate`")
    print(f"ablated:   {abl_path}")
    print(f"unablated: {una_path}")

    abl = _load(abl_path)
    una = _load(una_path)

    if abl.get("ablate") is not True:
        print(f"WARNING: --ablated file has ablate={abl.get('ablate')}, expected True")
    if una.get("ablate") is not False:
        print(f"WARNING: --unablated file has ablate={una.get('ablate')}, expected False")

    abl_test = abl["test"]["summary"]
    una_test = una["test"]["summary"]

    metrics = ["hungarian_recall@1", "top1_recall_unconstrained",
               "top5_recall_unconstrained", "roc_auc", "pr_auc", "log_loss"]
    deltas = {m: _delta(abl_test, una_test, m) for m in metrics}

    comparison = {
        "ablated_metrics_path": str(abl_path),
        "unablated_metrics_path": str(una_path),
        "ablated_test": abl_test,
        "unablated_test": una_test,
        "delta_unablated_minus_ablated": deltas,
        "interpretation": (
            "Positive deltas on recall/AUC/PR (and negative on log_loss) indicate "
            "the unablated-trained model — which has access to maternal edges — "
            "outperforms the ablated-trained model. Magnitude quantifies the "
            "value of maternal-lineage signal for marriage prediction."
        ),
    }

    out_dir = args.out or (
        config.RUNS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_compare"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(comparison, indent=2, default=str))

    md = [
        "# Ablation comparison",
        "",
        f"- Ablated metrics:    `{abl_path}`",
        f"- Unablated metrics:  `{una_path}`",
        "",
        "| Metric | Ablated (no maternal edges) | Unablated (full graph) | Δ (un − abl) |",
        "|---|---:|---:|---:|",
    ]
    for m in metrics:
        sign = "↓ better" if m == "log_loss" else "↑ better"
        md.append(f"| {m} ({sign}) | {abl_test.get(m, float('nan')):.4f} | "
                  f"{una_test.get(m, float('nan')):.4f} | {deltas[m]:+.4f} |")
    (out_dir / "comparison.md").write_text("\n".join(md) + "\n")

    print()
    print("=" * 60)
    print(f"  PROPER ablation delta (test Hungarian recall@1):")
    print(f"  ablated   = {abl_test['hungarian_recall@1']:.4f}")
    print(f"  unablated = {una_test['hungarian_recall@1']:.4f}")
    print(f"  delta     = {deltas['hungarian_recall@1']:+.4f}")
    print("=" * 60)
    print(f"\nwrote {out_dir / 'comparison.json'}")
    print(f"wrote {out_dir / 'comparison.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
