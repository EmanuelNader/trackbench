"""CLI entry for offline CLEAR MOT evaluation + optional failure mining."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from eval.cluster import cluster_failures
from eval.failure_miner import load_scene_meta, mine_failures
from eval.metrics import evaluate_scene, load_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "core" / "config" / "default.json"


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
    p.add_argument(
        "--write-db",
        action="store_true",
        help=(
            "persist Run + metrics (+ failures/clusters when --mine) to Postgres; "
            "requires pip install -r requirements-full.txt (psycopg)"
        ),
    )
    p.add_argument(
        "--commit-sha",
        type=str,
        default=None,
        help='git commit stamped on the Run (default: git --short HEAD, else env, else "unknown")',
    )
    p.add_argument(
        "--config-json",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"tracker config JSON path used for runKey hashing (default: {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "--notes",
        type=str,
        default=None,
        help="optional notes stored on the Run row",
    )
    p.add_argument(
        "--run-key",
        type=str,
        default=None,
        help="optional runKey override (default: sha256(commit + config))",
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


def resolve_commit_sha(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for env_key in ("COMMIT_SHA", "GITHUB_SHA", "GIT_COMMIT"):
        val = os.environ.get(env_key)
        if val:
            return val[:7] if env_key == "GITHUB_SHA" and len(val) >= 7 else val
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return "unknown"


def load_config_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.is_file():
        return {"_config_path": str(p), "_missing": True}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"_raw": data}


def _scene_fields(
    scene_id: str,
    scene_meta: dict[str, Any],
    n_frames: int,
) -> tuple[str, int, str | None, str | None]:
    name = str(scene_meta.get("scene_name") or scene_meta.get("name") or scene_id or "unknown")
    num_frames = int(scene_meta.get("n_frames") or scene_meta.get("numFrames") or n_frames)
    weather = scene_meta.get("weather")
    weather_s = str(weather) if weather is not None else None
    tod = scene_meta.get("timeOfDay") or scene_meta.get("time_of_day")
    tod_s = str(tod) if tod is not None else None
    return name, num_frames, weather_s, tod_s


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

    scene_meta = load_scene_meta(meta_path if meta_path is not None else args.scene_meta)
    scene_id = args.scene_id or (
        str(scene_meta.get("scene_name") or scene_meta.get("scene_token") or "")
    )

    failures: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    if args.mine:
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

    if args.write_db:
        try:
            from eval.db import connect, upsert_scene, write_run
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if not scene_id:
            print("--write-db requires a scene id (--scene-id or scene_meta)", file=sys.stderr)
            return 1

        commit_sha = resolve_commit_sha(args.commit_sha)
        config_json = load_config_json(args.config_json)
        # Stamp eval knobs so re-runs with different thresholds get distinct keys.
        config_for_key = {
            **config_json,
            "dist_threshold": args.dist_threshold,
            "scene_id": scene_id,
        }
        name, num_frames, weather, time_of_day = _scene_fields(
            scene_id, scene_meta, len(gt_frames)
        )

        try:
            with connect() as conn:
                upsert_scene(conn, scene_id, name, num_frames, weather, time_of_day)
                run_id = write_run(
                    conn,
                    commit_sha=commit_sha,
                    config_json=config_for_key,
                    notes=args.notes,
                    run_metrics={k: float(v) for k, v in payload.items()},
                    scene_id=scene_id,
                    scene_metrics={k: float(v) for k, v in payload.items()},
                    failures=failures,
                    clusters=clusters,
                    run_key=args.run_key,
                )
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"failed to write run to Postgres: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "commit_sha": commit_sha,
                    "scene_id": scene_id,
                    "n_failures": len(failures),
                    "n_clusters": len(clusters),
                    "wrote_db": True,
                },
                indent=2,
                sort_keys=True,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
