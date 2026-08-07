"""Build a committed demo bundle for the M4 triage UI fixture mode.

Reads the synthetic fixture GT + golden tracks, applies intentional degradations
so failure mining produces a non-empty set of events/clusters, then writes:

- ``data/fixtures/synthetic_scene_001/tracks_demo.jsonl``
- ``data/fixtures/synthetic_scene_001/demo_bundle.json``

Usage:
    python -m eval.write_demo_run
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from eval.cluster import cluster_failures
from eval.failure_miner import load_scene_meta, mine_failures
from eval.metrics import evaluate_scene, load_jsonl

SCENE_ID = "synthetic_scene_001"
RUN_KEY = "demo-synthetic-v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / SCENE_ID


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            f.write("\n")


def degrade_tracks(base: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Introduce ID switch, track drop, and a far-range ghost for the demo."""
    out: list[dict[str, Any]] = []
    for row in base:
        frame = int(row["frame"])
        cloned = copy.deepcopy(row)
        tracks: list[dict[str, Any]] = list(cloned.get("tracks") or [])

        # ID switch at the crossing: swap track ids from frame 10 onward.
        if frame >= 10:
            for tr in tracks:
                tid = int(tr["id"])
                if tid == 1:
                    tr["id"] = 2
                elif tid == 2:
                    tr["id"] = 1

        # Drop coverage of the (post-swap) track on car-a for frames 14–15.
        # After the swap, car-a (left→right, +y) is tracked by id 2.
        if frame in {14, 15}:
            tracks = [tr for tr in tracks if int(tr["id"]) != 2]

        # Far-range ghost confirmed track with no GT.
        if 6 <= frame <= 12:
            tracks.append(
                {
                    "id": 99,
                    "cls": "car",
                    "x": 42.0,
                    "y": 1.5,
                    "yaw": 0.0,
                    "vx": 0.0,
                    "vy": 0.0,
                    "state": "confirmed",
                    "age": frame - 5,
                    "cov_trace": 8.0,
                }
            )

        cloned["tracks"] = tracks
        out.append(cloned)
    return out


def build_bundle(
    fixture_dir: Path,
    *,
    dist_threshold: float = 2.0,
) -> dict[str, Any]:
    meta_path = fixture_dir / "scene_meta.json"
    gt_path = fixture_dir / "gt.jsonl"
    base_tracks_path = fixture_dir / "tracks_expected.jsonl"
    if not base_tracks_path.is_file():
        raise FileNotFoundError(f"missing golden tracks: {base_tracks_path}")

    scene_meta = load_scene_meta(meta_path)
    gt_frames = load_jsonl(gt_path)
    base_tracks = load_jsonl(base_tracks_path)
    demo_tracks = degrade_tracks(base_tracks)

    tracks_demo_path = fixture_dir / "tracks_demo.jsonl"
    _write_jsonl(tracks_demo_path, demo_tracks)

    metrics, frame_matches = evaluate_scene(
        gt_frames, demo_tracks, dist_threshold=dist_threshold
    )
    failures = mine_failures(
        gt_frames,
        demo_tracks,
        frame_matches,
        scene_id=SCENE_ID,
        scene_meta=scene_meta,
        dist_threshold=dist_threshold,
    )
    clusters = cluster_failures(failures)
    metrics_dict = metrics.to_dict()

    num_frames = int(scene_meta.get("n_frames") or len(gt_frames))
    weather = scene_meta.get("weather")
    time_of_day = scene_meta.get("timeOfDay") or scene_meta.get("time_of_day")

    return {
        "version": 1,
        "scene": {
            "id": SCENE_ID,
            "name": str(scene_meta.get("scene_name") or SCENE_ID),
            "numFrames": num_frames,
            "weather": weather,
            "timeOfDay": time_of_day,
            "description": scene_meta.get("description"),
        },
        "run": {
            "runKey": RUN_KEY,
            "commitSha": "demo",
            "configJson": {
                "source": "fixture",
                "tracks": "tracks_demo.jsonl",
                "dist_threshold": dist_threshold,
            },
            "notes": "Synthetic demo run for M4 triage UI (intentionally degraded tracks).",
        },
        "metrics": metrics_dict,
        "sceneMetrics": {SCENE_ID: metrics_dict},
        "failures": failures,
        "clusters": clusters,
        "tracksFile": "tracks_demo.jsonl",
        "gtFile": "gt.jsonl",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Write demo_bundle.json for fixture mode")
    p.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="path to synthetic_scene_001 fixture directory",
    )
    p.add_argument(
        "--dist-threshold",
        type=float,
        default=2.0,
        help="2D center-distance match threshold in meters",
    )
    args = p.parse_args(argv)

    fixture_dir = args.fixture_dir.resolve()
    bundle = build_bundle(fixture_dir, dist_threshold=args.dist_threshold)
    out_path = fixture_dir / "demo_bundle.json"
    out_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "out": str(out_path),
                "tracks": str(fixture_dir / "tracks_demo.jsonl"),
                "n_failures": len(bundle["failures"]),
                "n_clusters": len(bundle["clusters"]),
                "metrics": bundle["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
