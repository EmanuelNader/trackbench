"""CI regression gate: compare current metrics to baselines/baseline.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from eval.metrics import evaluate_scene, load_jsonl


def load_baseline(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check_gate(
    current: dict[str, float],
    baseline: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Return (ok, messages). Fail on MOTA drop, IDS increase, optional p99."""
    bmetrics = baseline["metrics"]
    gates = baseline.get("gates", {})
    mota_max_drop = float(gates.get("mota_max_drop", 0.5))
    ids_max_increase = int(gates.get("ids_max_increase", 0))

    messages: list[str] = []
    ok = True

    delta_mota = float(current["mota"]) - float(bmetrics["mota"])
    messages.append(
        f"MOTA {current['mota']:.4f} (baseline {bmetrics['mota']:.4f}, "
        f"delta {delta_mota:+.4f})"
    )
    if delta_mota < -mota_max_drop:
        ok = False
        messages.append(
            f"FAIL: MOTA dropped by {-delta_mota:.4f} > allowed {mota_max_drop}"
        )

    delta_ids = int(current["ids"]) - int(bmetrics["ids"])
    messages.append(
        f"IDS {current['ids']} (baseline {bmetrics['ids']}, delta {delta_ids:+d})"
    )
    if delta_ids > ids_max_increase:
        ok = False
        messages.append(
            f"FAIL: IDS increased by {delta_ids} > allowed {ids_max_increase}"
        )

    # Latency gate only when both sides have p99.
    cur_p99 = current.get("latency_p99_ms")
    base_p99 = (baseline.get("latency") or {}).get("p99_ms")
    ratio = float(gates.get("p99_max_regression_ratio", 0.2))
    if cur_p99 is not None and base_p99 is not None and base_p99 > 0:
        reg = (float(cur_p99) - float(base_p99)) / float(base_p99)
        messages.append(
            f"p99 {cur_p99:.3f}ms (baseline {base_p99:.3f}ms, "
            f"regression {reg:+.1%})"
        )
        if reg > ratio:
            ok = False
            messages.append(
                f"FAIL: p99 latency regresses {reg:.1%} > allowed {ratio:.0%}"
            )

    return ok, messages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--baseline",
        type=Path,
        default=Path("baselines/baseline.json"),
    )
    p.add_argument("--gt", type=Path, default=None)
    p.add_argument("--tracks", type=Path, default=None)
    p.add_argument(
        "--timing",
        type=Path,
        default=None,
        help="Optional timing.json from trackbench_run",
    )
    args = p.parse_args(argv)

    baseline = load_baseline(args.baseline)
    gt_path = args.gt or Path(baseline["gt"])
    tracks_path = args.tracks or Path(baseline["tracks"])

    metrics, _ = evaluate_scene(load_jsonl(gt_path), load_jsonl(tracks_path))
    current = {
        "mota": metrics.mota,
        "motp": metrics.motp,
        "ids": float(metrics.ids),
        "fp": float(metrics.fp),
        "fn": float(metrics.fn),
        "frag": float(metrics.frag),
    }

    if args.timing and args.timing.is_file():
        timing = json.loads(args.timing.read_text(encoding="utf-8"))
        # Accept either {"frames":[{"ms":...}]} or {"p99_ms":...}
        if "p99_ms" in timing:
            current["latency_p99_ms"] = float(timing["p99_ms"])
        elif "frames" in timing:
            ms = sorted(float(f["ms"]) for f in timing["frames"] if "ms" in f)
            if ms:
                idx = min(len(ms) - 1, int(round(0.99 * (len(ms) - 1))))
                current["latency_p99_ms"] = ms[idx]

    ok, messages = check_gate(current, baseline)
    print(json.dumps({"ok": ok, "current": current, "messages": messages}, indent=2))
    for m in messages:
        print(m, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
