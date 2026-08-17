#!/usr/bin/env python3
"""Export tracker output to nuScenes tracking challenge CSV format.

The nuScenes tracking challenge expects a flat CSV with columns:
  track_id, sample_token, translation_x/y/z, size_l/w/h,
  rotation_w/x/y/z, velocity_x/y, name, score, n_points, instance_token

This script reads the tracker's JSONL output and converts it to the
challenge format. The only non-standard field is ``sample_token``: our
JSONL files use integer frame indices instead of nuScenes UUIDs, so we
emit ``{scene_id}_f{frame:03d}`` as a placeholder. To produce real
sample_tokens, re-run ingest with the sample token persisted per frame.

Usage:
  python3 scripts/export_challenge.py --scene scene-0655
  python3 scripts/export_challenge.py --all
  python3 scripts/export_challenge.py --tracks-dir data/tracks --out challenge.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZED = REPO_ROOT / "data" / "normalized"
DEFAULT_TRACKS = REPO_ROOT / "data" / "tracks"

TRACKING_CLASSES = frozenset(
    {"bicycle", "bus", "car", "motorcycle", "pedestrian", "trailer", "truck"}
)

# Default box sizes per class (l, w, h) from nuScenes stats, used when the
# tracker output doesn't include l/w/h (older binary runs).
DEFAULT_BOX_SIZE: dict[str, tuple[float, float, float]] = {
    "bicycle": (1.7, 0.6, 1.7),
    "bus": (11.3, 2.9, 3.5),
    "car": (4.5, 1.9, 1.7),
    "motorcycle": (2.1, 0.8, 1.5),
    "pedestrian": (0.6, 0.6, 1.7),
    "trailer": (10.0, 2.5, 3.3),
    "truck": (7.0, 2.5, 3.0),
}

CHALLENGE_COLUMNS = [
    "track_id",
    "sample_token",
    "translation_x",
    "translation_y",
    "translation_z",
    "size_l",
    "size_w",
    "size_h",
    "rotation_w",
    "rotation_x",
    "rotation_y",
    "rotation_z",
    "velocity_x",
    "velocity_y",
    "name",
    "score",
    "n_points",
    "instance_token",
]


def yaw_to_quat(yaw: float) -> tuple[float, float, float, float]:
    """Convert yaw (radians, ego frame) to quaternion (w, x, y, z)."""
    return (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def export_scene(
    scene_id: str,
    tracks_dir: Path,
    normalized_dir: Path,
    writer: csv.writer,
) -> int:
    """Write one scene's tracks to the CSV writer. Returns row count."""
    tracks_path = tracks_dir / f"{scene_id}.jsonl"
    if not tracks_path.is_file():
        # Fall back to normalized dir (in-place tracks).
        tracks_path = normalized_dir / scene_id / "tracks.jsonl"
    if not tracks_path.is_file():
        print(f"  SKIP {scene_id}: no tracks found", file=sys.stderr)
        return 0

    frames = load_jsonl(tracks_path)
    n_rows = 0
    for frame_data in frames:
        frame = int(frame_data["frame"])
        sample_token = f"{scene_id}_f{frame:03d}"
        for track in frame_data.get("tracks", []):
            cls = str(track.get("cls", "car"))
            if cls not in TRACKING_CLASSES:
                continue
            qw, qx, qy, qz = yaw_to_quat(float(track.get("yaw", 0.0)))
            # Use track's l/w/h if present; fall back to class defaults.
            tl = float(track.get("l", 0))
            tw = float(track.get("w", 0))
            th = float(track.get("h", 0))
            if tl == 0 and tw == 0 and th == 0:
                tl, tw, th = DEFAULT_BOX_SIZE.get(cls, (4.5, 1.9, 1.7))
            writer.writerow([
                int(track["id"]),
                sample_token,
                f"{float(track.get('x', 0)):.4f}",
                f"{float(track.get('y', 0)):.4f}",
                f"{float(track.get('z', 0)):.4f}",
                f"{tl:.4f}",
                f"{tw:.4f}",
                f"{th:.4f}",
                f"{qw:.6f}",
                f"{qx:.6f}",
                f"{qy:.6f}",
                f"{qz:.6f}",
                f"{float(track.get('vx', 0)):.4f}",
                f"{float(track.get('vy', 0)):.4f}",
                cls,
                f"{float(track.get('score', 1.0)):.4f}",
                0,  # n_points: not available without lidar points
                f"inst_{scene_id}_{track['id']}",
            ])
            n_rows += 1
    return n_rows


def scene_ids(normalized_dir: Path) -> list[str]:
    return sorted(
        p.name
        for p in normalized_dir.iterdir()
        if p.is_dir() and (p / "detections.jsonl").is_file()
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/export_challenge.py",
        description="Export tracker output to nuScenes tracking challenge CSV.",
    )
    p.add_argument(
        "--scene",
        action="append",
        metavar="SCENE",
        help="scene name(s) to export (repeatable; default: all)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="export all normalized scenes",
    )
    p.add_argument(
        "--tracks-dir",
        type=Path,
        default=DEFAULT_TRACKS,
        help="tracks directory (default: %(default)s)",
    )
    p.add_argument(
        "--normalized-dir",
        type=Path,
        default=DEFAULT_NORMALIZED,
        help="normalized scenes directory (default: %(default)s)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output CSV path (default: stdout)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    scenes: list[str] = []
    if args.all:
        scenes = scene_ids(args.normalized_dir)
    elif args.scene:
        scenes = args.scene
    else:
        scenes = scene_ids(args.normalized_dir)

    if not scenes:
        print("no scenes to export", file=sys.stderr)
        return 1

    out_file = open(args.out, "w", newline="") if args.out else sys.stdout
    writer = csv.writer(out_file)
    writer.writerow(CHALLENGE_COLUMNS)

    total = 0
    for scene_id in scenes:
        n = export_scene(scene_id, args.tracks_dir, args.normalized_dir, writer)
        total += n
        print(f"  {scene_id}: {n} rows")

    if args.out:
        out_file.close()
        print(f"wrote {args.out} ({total} rows, {len(scenes)} scenes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
