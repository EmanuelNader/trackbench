"""Evaluate all normalized scenes against tracks and optionally persist one Run.

Usage:
    python -m eval.write_run --tracks-dir data/tracks --normalized-dir data/normalized --write-db

For each scene directory under ``normalized-dir``, loads GT from
``{normalized}/{scene}/gt.jsonl`` and tracks from ``{tracks-dir}/{scene}.jsonl``,
runs CLEAR MOT (+ optional mining), aggregates metrics, clusters failures
**globally**, and writes a single Postgres Run.

Also computes AMOTA/AMOTP (via eval.amota) and pooled p99 latency (from
timing.json files) and persists them as RunMetric entries so the Pareto chart
in the web UI can read them through the API.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from eval.cluster import cluster_failures
from eval.failure_miner import load_scene_meta, mine_failures
from eval.metrics import evaluate_scene, load_jsonl
from eval.run_eval import (
    DEFAULT_CONFIG,
    REPO_ROOT,
    _scene_fields,
    load_config_json,
    resolve_commit_sha,
)

DEFAULT_NORMALIZED = REPO_ROOT / "data" / "normalized"
DEFAULT_TRACKS = REPO_ROOT / "data" / "tracks"


def _nearest_rank_p99(values: list[float]) -> float | None:
    """Nearest-rank p99 over sorted values, or None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    k = math.ceil(0.99 * len(ordered))
    return ordered[k - 1]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.write_run",
        description="Aggregate multi-scene eval into one Postgres Run.",
    )
    p.add_argument(
        "--normalized-dir",
        type=Path,
        default=DEFAULT_NORMALIZED,
        help="directory of normalized scene folders (default: data/normalized)",
    )
    p.add_argument(
        "--tracks-dir",
        type=Path,
        default=DEFAULT_TRACKS,
        help="directory of per-scene tracks JSONL files named {scene}.jsonl",
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
        default=True,
        help="mine failures and cluster globally (default: on)",
    )
    p.add_argument(
        "--no-mine",
        action="store_false",
        dest="mine",
        help="skip failure mining (empty failures/clusters)",
    )
    p.add_argument(
        "--write-db",
        action="store_true",
        help=(
            "persist aggregated Run to Postgres; "
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


def list_scenes(normalized_dir: Path) -> list[str]:
    if not normalized_dir.is_dir():
        return []
    scenes = sorted(
        p.name for p in normalized_dir.iterdir() if p.is_dir() and (p / "gt.jsonl").is_file()
    )
    return scenes


def aggregate_run_metrics(scene_metrics: dict[str, dict[str, float]]) -> dict[str, float]:
    """Sum counts; recompute MOTA; weighted-mean MOTP by match count (gt - fn).

    Also aggregates per-class IDS, FN, and GT counts into
    ``per_class_{metric}_{cls}`` keys.
    """
    fp = fn = ids = frag = gt_count = 0.0
    motp_weight = 0.0
    motp_acc = 0.0
    # Per-class accumulators.
    pc_ids: dict[str, float] = {}
    pc_fn: dict[str, float] = {}
    pc_gt: dict[str, float] = {}
    for m in scene_metrics.values():
        fp += float(m.get("fp", 0))
        fn += float(m.get("fn", 0))
        ids += float(m.get("ids", 0))
        frag += float(m.get("frag", 0))
        gt = float(m.get("gt_count", 0))
        gt_count += gt
        matches = max(gt - float(m.get("fn", 0)), 0.0)
        if matches > 0 and "motp" in m:
            motp_weight += matches
            motp_acc += float(m["motp"]) * matches
        # Per-class breakdown (from evaluate_scene's per_class dict).
        per_class = m.get("per_class")
        if isinstance(per_class, dict):
            for cls, counts in per_class.items():
                if isinstance(counts, dict):
                    pc_ids[cls] = pc_ids.get(cls, 0.0) + float(counts.get("ids", 0))
                    pc_fn[cls] = pc_fn.get(cls, 0.0) + float(counts.get("fn", 0))
                    pc_gt[cls] = pc_gt.get(cls, 0.0) + float(counts.get("gt_count", 0))
    denom = max(gt_count, 1.0)
    mota = 1.0 - (fp + fn + ids) / denom
    out: dict[str, float] = {
        "mota": mota,
        "ids": ids,
        "frag": frag,
        "fp": fp,
        "fn": fn,
        "gt_count": gt_count,
    }
    if motp_weight > 0:
        out["motp"] = motp_acc / motp_weight
    # Persist per-class breakdowns as flat keys.
    for cls in sorted(set(pc_gt) | set(pc_ids) | set(pc_fn)):
        out[f"ids_{cls}"] = pc_ids.get(cls, 0.0)
        out[f"fn_{cls}"] = pc_fn.get(cls, 0.0)
        out[f"gt_count_{cls}"] = pc_gt.get(cls, 0.0)
    return out


def evaluate_scenes(
    *,
    normalized_dir: Path,
    tracks_dir: Path,
    dist_threshold: float,
    mine: bool,
) -> tuple[
    dict[str, dict[str, float]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Return (scene_metrics, scene_infos, failures, clusters)."""
    scenes = list_scenes(normalized_dir)
    if not scenes:
        raise FileNotFoundError(f"no scenes with gt.jsonl under {normalized_dir}")

    scene_metrics: dict[str, dict[str, float]] = {}
    scene_infos: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []

    for scene_id in scenes:
        scene_dir = normalized_dir / scene_id
        gt_path = scene_dir / "gt.jsonl"
        tracks_path = tracks_dir / f"{scene_id}.jsonl"
        # Fall back to tracks inside the scene dir (fixture / scene-dir layout).
        if not tracks_path.is_file():
            alt = scene_dir / "tracks.jsonl"
            tracks_path = alt if alt.is_file() else tracks_path
        if not tracks_path.is_file():
            print(f"skip {scene_id}: tracks not found at {tracks_dir / (scene_id + '.jsonl')}", file=sys.stderr)
            continue

        meta = load_scene_meta(scene_dir / "scene_meta.json")
        gt_frames = load_jsonl(gt_path)
        track_frames = load_jsonl(tracks_path)
        metrics, frame_matches = evaluate_scene(
            gt_frames, track_frames, dist_threshold=dist_threshold
        )
        mdict = {k: float(v) for k, v in metrics.to_dict().items()}
        scene_metrics[scene_id] = mdict
        name, num_frames, weather, tod = _scene_fields(scene_id, meta, len(gt_frames))
        scene_infos.append(
            {
                "id": scene_id,
                "name": name,
                "num_frames": num_frames,
                "weather": weather,
                "time_of_day": tod,
            }
        )
        if mine:
            failures = mine_failures(
                gt_frames,
                track_frames,
                frame_matches,
                scene_id=scene_id,
                scene_meta=meta,
                dist_threshold=dist_threshold,
            )
            all_failures.extend(failures)

    if not scene_metrics:
        raise FileNotFoundError(f"no evaluable scenes under {normalized_dir} with tracks in {tracks_dir}")

    clusters = cluster_failures(all_failures) if all_failures else []
    return scene_metrics, scene_infos, all_failures, clusters


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    normalized_dir = args.normalized_dir.resolve()
    tracks_dir = args.tracks_dir.resolve()

    try:
        scene_metrics, scene_infos, failures, clusters = evaluate_scenes(
            normalized_dir=normalized_dir,
            tracks_dir=tracks_dir,
            dist_threshold=args.dist_threshold,
            mine=args.mine,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    run_metrics = aggregate_run_metrics(scene_metrics)

    # Compute AMOTA/AMOTP across all scenes.
    try:
        from eval.amota import compute_amota
        amota_input = []
        for scene_id in scenes:
            gt_path = normalized_dir / scene_id / "gt.jsonl"
            tracks_path = tracks_dir / f"{scene_id}.jsonl"
            if not tracks_path.is_file():
                alt = normalized_dir / scene_id / "tracks.jsonl"
                tracks_path = alt if alt.is_file() else tracks_path
            if not gt_path.is_file() or not tracks_path.is_file():
                continue
            gt_frames = load_jsonl(gt_path)
            track_frames = load_jsonl(tracks_path)
            amota_input.append((gt_frames, track_frames))
        if amota_input:
            amota_result = compute_amota(amota_input)
            run_metrics["amota"] = float(amota_result["all"]["amota"])
            run_metrics["amotp"] = float(amota_result["all"]["amotp"])
            # Persist per-class AMOTA/AMOTP.
            per_class = amota_result.get("per_class", {})
            for cls, vals in per_class.items():
                if isinstance(vals, dict):
                    if "amota" in vals and not (isinstance(vals["amota"], float) and __import__("math").isnan(vals["amota"])):
                        run_metrics[f"amota_{cls}"] = float(vals["amota"])
                    if "amotp" in vals and not (isinstance(vals["amotp"], float) and __import__("math").isnan(vals["amotp"])):
                        run_metrics[f"amotp_{cls}"] = float(vals["amotp"])
    except Exception:
        pass  # AMOTA not critical for write_run; skip on import/math errors

    # Compute pooled p99 latency from timing.json files.
    ms_frames: list[float] = []
    for scene_id in scenes:
        for candidate in [
            tracks_dir / f"{scene_id}_timing.json",
            normalized_dir / scene_id / "timing.json",
        ]:
            if candidate.is_file():
                try:
                    timing = json.loads(candidate.read_text(encoding="utf-8"))
                    ms_frames.extend(timing.get("ms_per_frame", []))
                except Exception:
                    pass
                break
    p99 = _nearest_rank_p99(ms_frames)
    if p99 is not None:
        run_metrics["p99_ms"] = p99

    commit_sha = resolve_commit_sha(args.commit_sha)
    config_json = load_config_json(args.config_json)
    config_for_key = {
        **config_json,
        "dist_threshold": args.dist_threshold,
        "scenes": sorted(scene_metrics.keys()),
        "tracks_dir": str(tracks_dir),
    }

    summary = {
        "commit_sha": commit_sha,
        "scenes": list(scene_metrics.keys()),
        "run_metrics": run_metrics,
        "scene_metrics": scene_metrics,
        "n_failures": len(failures),
        "n_clusters": len(clusters),
        "wrote_db": False,
        "run_id": None,
    }

    if args.write_db:
        try:
            from eval.db import connect, upsert_scene, write_run
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        primary_scene = scene_infos[0]["id"] if scene_infos else ""
        try:
            with connect() as conn:
                for info in scene_infos:
                    upsert_scene(
                        conn,
                        info["id"],
                        info["name"],
                        int(info["num_frames"]),
                        info.get("weather"),
                        info.get("time_of_day"),
                    )
                run_id = write_run(
                    conn,
                    commit_sha=commit_sha,
                    config_json=config_for_key,
                    notes=args.notes,
                    run_metrics=run_metrics,
                    scene_id=primary_scene,
                    scene_metrics=scene_metrics,
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

        summary["wrote_db"] = True
        summary["run_id"] = run_id

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
