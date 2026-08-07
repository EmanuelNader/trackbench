#!/usr/bin/env python3
"""Generate a dense synthetic detection stream, run the tracker with --timing,
and print p50 / p99 wall-ms. Used for README reference numbers.

Does not claim MOT accuracy — association load only.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def write_dense_dets(path: Path, *, frames: int, n_dets: int, dt: float = 0.1) -> None:
    """n_dets moving objects on a grid; high enough score to birth."""
    with path.open("w", encoding="utf-8") as f:
        for frame in range(frames):
            t = frame * dt
            dets = []
            cols = int(math.ceil(math.sqrt(n_dets)))
            for i in range(n_dets):
                row, col = divmod(i, cols)
                x = -20.0 + col * 2.5 + 0.4 * frame * 0.1
                y = -15.0 + row * 2.5
                dets.append(
                    {
                        "id": f"d{frame}_{i}",
                        "cls": "car",
                        "x": x,
                        "y": y,
                        "z": 0.0,
                        "l": 4.5,
                        "w": 1.8,
                        "h": 1.5,
                        "yaw": 0.0,
                        "score": 0.9,
                        "vx": 4.0,
                        "vy": 0.0,
                    }
                )
            f.write(
                json.dumps(
                    {"scene_id": "latency_bench", "frame": frame, "t": t, "dets": dets},
                    separators=(",", ":"),
                )
                + "\n"
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--dets-per-frame", type=int, default=40)
    ap.add_argument(
        "--tracker",
        default="core/build/trackbench_run",
        help="path to trackbench_run",
    )
    ap.add_argument("--config", default="core/config/default.json")
    ap.add_argument("--json-out", default="", help="optional path to copy timing.json")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    tracker = (root / args.tracker).resolve()
    config = (root / args.config).resolve()
    if not tracker.is_file():
        print(f"missing tracker binary: {tracker} (run make core)", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="trackbench_bench_") as td:
        td_path = Path(td)
        dets = td_path / "detections.jsonl"
        tracks = td_path / "tracks.jsonl"
        timing = td_path / "timing.json"
        write_dense_dets(dets, frames=args.frames, n_dets=args.dets_per_frame)
        subprocess.run(
            [
                str(tracker),
                "--dets",
                str(dets),
                "--config",
                str(config),
                "--out",
                str(tracks),
                "--timing",
                str(timing),
            ],
            check=True,
        )
        payload = json.loads(timing.read_text(encoding="utf-8"))
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )

    ms = sorted(float(x) for x in payload["ms_per_frame"])
    report = {
        "hardware": {
            "machine": platform.machine(),
            "processor": platform.processor() or platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "workload": {
            "frames": args.frames,
            "dets_per_frame": args.dets_per_frame,
            "note": "synthetic dense association load; not a MOT accuracy bench",
        },
        "timing_ms": {
            "total_ms": payload["total_ms"],
            "mean": statistics.fmean(ms) if ms else None,
            "p50": percentile(ms, 50),
            "p95": percentile(ms, 95),
            "p99": percentile(ms, 99),
            "max": max(ms) if ms else None,
        },
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
