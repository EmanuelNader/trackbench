"""CLI entry for offline CLEAR MOT evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.metrics import evaluate_scene, load_jsonl


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.run_eval",
        description="Run TrackBench CLEAR MOT evaluation on GT / tracks JSONL.",
    )
    p.add_argument(
        "--gt",
        type=Path,
        default=None,
        help="path to gt.jsonl",
    )
    p.add_argument(
        "--tracks",
        type=Path,
        default=None,
        help="path to tracks.jsonl",
    )
    p.add_argument(
        "--scene-dir",
        type=Path,
        default=None,
        help="normalized scene directory containing gt.jsonl / tracks.jsonl",
    )
    p.add_argument(
        "--dist-threshold",
        type=float,
        default=2.0,
        help="2D center-distance match threshold in meters (default: 2.0)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional path to write metrics JSON (also printed to stdout)",
    )
    return p


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.gt is not None and args.tracks is not None:
        return args.gt, args.tracks
    if args.scene_dir is not None:
        return args.scene_dir / "gt.jsonl", args.scene_dir / "tracks.jsonl"
    raise SystemExit("provide --gt and --tracks, or --scene-dir")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gt_path, tracks_path = _resolve_paths(args)

    if not gt_path.is_file():
        print(f"gt file not found: {gt_path}", file=sys.stderr)
        return 1
    if not tracks_path.is_file():
        print(f"tracks file not found: {tracks_path}", file=sys.stderr)
        return 1

    gt_frames = load_jsonl(gt_path)
    track_frames = load_jsonl(tracks_path)
    metrics, _frame_matches = evaluate_scene(
        gt_frames,
        track_frames,
        dist_threshold=args.dist_threshold,
    )
    payload = metrics.to_dict()

    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")

    # TODO(M2): write Run row to Postgres when the API/DB path is wired.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
