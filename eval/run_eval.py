"""CLI entry for offline CLEAR MOT evaluation + optional failure mining."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.cluster import cluster_failures
from eval.failure_miner import load_scene_meta, mine_failures
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
        "--scene-meta",
        type=Path,
        default=None,
        help="optional path to scene_meta.json (weather / time_of_day)",
    )
    p.add_argument(
        "--scene-id",
        type=str,
        default="",
        help="scene identifier stamped onto mined failure events",
    )
    p.add_argument(
        "--dist-threshold",
        type=float,
        default=2.0,
        help="2D center-distance match threshold in meters (default: 2.0)",
    )
    p.add_argument(
        "--mine",
        action="store_true",
        help="mine failure events and print ranked rule clusters",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional path to write metrics JSON (also printed to stdout)",
    )
    return p


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    if args.gt is not None and args.tracks is not None:
        meta = args.scene_meta
        if meta is None and args.scene_dir is not None:
            candidate = args.scene_dir / "scene_meta.json"
            meta = candidate if candidate.is_file() else None
        return args.gt, args.tracks, meta
    if args.scene_dir is not None:
        meta = args.scene_meta
        if meta is None:
            candidate = args.scene_dir / "scene_meta.json"
            meta = candidate if candidate.is_file() else None
        return args.scene_dir / "gt.jsonl", args.scene_dir / "tracks.jsonl", meta
    raise SystemExit("provide --gt and --tracks, or --scene-dir")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gt_path, tracks_path, meta_path = _resolve_paths(args)

    if not gt_path.is_file():
        print(f"gt file not found: {gt_path}", file=sys.stderr)
        return 1
    if not tracks_path.is_file():
        print(f"tracks file not found: {tracks_path}", file=sys.stderr)
        return 1

    gt_frames = load_jsonl(gt_path)
    track_frames = load_jsonl(tracks_path)
    metrics, frame_matches = evaluate_scene(
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

    if args.mine:
        scene_meta = load_scene_meta(meta_path if meta_path is not None else args.scene_meta)
        scene_id = args.scene_id or (
            str(scene_meta.get("scene_name") or scene_meta.get("scene_token") or "")
        )
        failures = mine_failures(
            gt_frames,
            track_frames,
            frame_matches,
            scene_id=scene_id,
            scene_meta=scene_meta,
            dist_threshold=args.dist_threshold,
        )
        clusters = cluster_failures(failures)
        print(
            json.dumps(
                {
                    "n_failures": len(failures),
                    "failures": failures,
                    "clusters": clusters,
                },
                indent=2,
                sort_keys=True,
            )
        )

    # TODO(M2): write Run row to Postgres when the API/DB path is wired.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
