#!/usr/bin/env python3
"""Full nuScenes val-split evaluation pipeline.

Single command to ingest, track, and evaluate all nuScenes val scenes.
Requires the v1.0-trainval nuScenes data and Megvii val detections.

Usage:
  python3 scripts/eval_val.py                          # full val pipeline
  python3 scripts/eval_val.py --limit 5                # ingest + track 5 scenes
  python3 scripts/eval_val.py --config baseline        # use baseline config
  python3 scripts/eval_val.py --jobs 8                 # 8 parallel tracker jobs
  python3 scripts/eval_val.py --skip-ingest            # skip ingest (scenes already in data/normalized/)
  python3 scripts/eval_val.py --eval-only              # skip ingest + track, only evaluate

Pipeline:
  1. Ingest: python -m ingest.nuscenes_ingest --version v1.0-trainval \
       --detections-json data/raw/detections/megvii_val.json
  2. Track: core/build/trackbench_run --dets ... --config ... --out ... --timing ...
  3. Evaluate: eval.metrics.evaluate_scene + eval.amota.compute_amota
  4. Aggregate: bench/val/summary.json + bench/val/SUMMARY.md

Output goes to bench/val/out/<label>/ (never into data/normalized/).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eval.metrics import evaluate_scene, load_jsonl  # noqa: E402
from eval.amota import compute_amota  # noqa: E402
from bench.ablation.summarize import cell_label, materialize_cells, load_references  # noqa: E402

MANIFEST = REPO_ROOT / "bench" / "ablation" / "manifest.toml"
NORMALIZED_ROOT = REPO_ROOT / "data" / "normalized"
DEFAULT_BIN = "core/build/trackbench_run"
DEFAULT_OUT = REPO_ROOT / "bench" / "val" / "out"
SUMMARY_JSON = REPO_ROOT / "bench" / "val" / "summary.json"
SUMMARY_MD = REPO_ROOT / "bench" / "val" / "SUMMARY.md"
SCHEMA = "trackbench/val-eval/v1"
DEFAULT_VERSION = "v1.0-trainval"
DEFAULT_DETECTIONS_JSON = "data/raw/detections/megvii_val.json"
DEFAULT_DATAROOT = "data/raw/nuscenes"


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def clean_nan(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, list):
        return [clean_nan(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    return value


def nearest_rank_p99(values):
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    k = math.ceil(0.99 * len(ordered))
    return ordered[k - 1]


def scene_ids() -> list[str]:
    return sorted(
        p.name
        for p in NORMALIZED_ROOT.iterdir()
        if p.is_dir() and (p / "detections.jsonl").is_file()
    )


def run_ingest(version: str, dataroot: str, detections_json: str, limit: int | None) -> None:
    cmd = [
        sys.executable, "-m", "ingest.nuscenes_ingest",
        "--version", version,
        "--dataroot", dataroot,
        "--detections-json", detections_json,
        "--force",
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    print(f"ingest: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def run_tracker_scene(
    binary: str, config_path: Path, scene: str, tracks_out: Path, timing_out: Path
) -> None:
    dets = NORMALIZED_ROOT / scene / "detections.jsonl"
    subprocess.run(
        [
            binary,
            "--dets", str(dets),
            "--config", str(config_path),
            "--out", str(tracks_out),
            "--timing", str(timing_out),
        ],
        check=True,
    )


def track_scene(args: tuple) -> dict:
    """Wrapper for ProcessPoolExecutor: track one scene, return status."""
    binary, config_path, scene, out_root, force = args
    tracks_out = out_root / f"{scene}.jsonl"
    timing_out = out_root / f"{scene}_timing.json"
    if not force and tracks_out.is_file() and timing_out.is_file():
        return {"scene": scene, "status": "skip"}
    try:
        run_tracker_scene(binary, config_path, scene, tracks_out, timing_out)
        return {"scene": scene, "status": "ok"}
    except subprocess.CalledProcessError as exc:
        return {"scene": scene, "status": "error", "error": str(exc)}


def compute_scene_metrics(scene: str) -> dict:
    """Compute MOTA/IDS/AMOTA for one scene."""
    gt_path = NORMALIZED_ROOT / scene / "gt.jsonl"
    tracks_path = NORMALIZED_ROOT / scene / "tracks.jsonl"
    if not gt_path.is_file() or not tracks_path.is_file():
        return {"scene": scene, "error": "missing gt or tracks"}
    gt = load_jsonl(gt_path)
    tracks = load_jsonl(tracks_path)
    metrics, _ = evaluate_scene(gt, tracks)
    return {
        "scene": scene,
        "mota": float(metrics.mota),
        "ids": int(metrics.ids),
        "fp": int(metrics.fp),
        "fn": int(metrics.fn),
        "frag": int(metrics.frag),
        "motp": float(metrics.motp),
    }


def render_summary_md(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# Full nuScenes val-split evaluation")
    lines.append("")
    lines.append(
        "Machine-generated by `scripts/eval_val.py`. Do not hand-edit; "
        "regenerate with `python3 scripts/eval_val.py`."
    )
    lines.append("")
    lines.append("## Per-scene metrics")
    lines.append("")
    lines.append("| scene | MOTA | IDS | FP | FN | FRAG | MOTP |")
    lines.append("|---|---|---|---|---|---|---|")
    scenes = payload.get("scenes", {})
    for scene in sorted(scenes):
        s = scenes[scene]
        if "error" in s:
            lines.append(f"| {scene} | — | — | — | — | — | — |")
        else:
            lines.append(
                f"| {scene} | {s['mota']:.4f} | {s['ids']} | {s['fp']} | "
                f"{s['fn']} | {s['frag']} | {s['motp']:.4f} |"
            )
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    t = payload.get("totals", {})
    lines.append(f"- **MOTA (sum):** {t.get('mota', 'n/a')}")
    lines.append(f"- **IDS:** {t.get('ids', 'n/a')}")
    lines.append(f"- **AMOTA:** {t.get('amota', 'n/a')}")
    lines.append(f"- **AMOTP:** {t.get('amotp', 'n/a')}")
    lines.append(f"- **p99 ms:** {t.get('p99_ms', 'n/a')}")
    lines.append(f"- **scenes:** {t.get('n_scenes', 'n/a')}")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- commit: `{payload['provenance']['commit']}`")
    lines.append(f"- config: `{payload['provenance']['config']}`")
    lines.append(f"- tracker binary: `{payload['provenance']['bin']}`")
    lines.append(f"- python: {payload['provenance']['python']}")
    lines.append(f"- ts: {payload['provenance']['ts']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/eval_val.py",
        description="Full nuScenes val-split evaluation pipeline.",
    )
    p.add_argument(
        "--config",
        default="post003",
        help="manifest reference name (default: %(default)s)",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="parallel tracker invocations (default: %(default)s)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="ingest + track only the first N scenes",
    )
    p.add_argument(
        "--skip-ingest",
        action="store_true",
        help="skip the ingest step (scenes already in data/normalized/)",
    )
    p.add_argument(
        "--eval-only",
        action="store_true",
        help="skip ingest + track, only evaluate existing tracks",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="re-run tracker even if tracks.jsonl exists",
    )
    p.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help="nuScenes version (default: %(default)s)",
    )
    p.add_argument(
        "--dataroot",
        default=DEFAULT_DATAROOT,
        help="nuScenes dataroot (default: %(default)s)",
    )
    p.add_argument(
        "--detections-json",
        default=DEFAULT_DETECTIONS_JSON,
        help="Megvii detections JSON (default: %(default)s)",
    )
    p.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="output root (default: %(default)s)",
    )
    p.add_argument(
        "--binary",
        default=DEFAULT_BIN,
        help="tracker binary (default: %(default)s)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    with open(MANIFEST, "rb") as f:
        manifest = tomllib.load(f)
    cells = materialize_cells(manifest)
    cells_by_label = {c["label"]: c for c in cells}
    refs = load_references(manifest)

    config_name = args.config
    if config_name in refs:
        label = cell_label(refs[config_name])
    elif config_name in cells_by_label:
        label = config_name
    else:
        raise SystemExit(f"error: unknown config {config_name!r}")

    if label not in cells_by_label:
        raise SystemExit(f"error: config {config_name!r} not in 24-cell grid")
    config = cells_by_label[label]["config"]

    bin_path = Path(args.binary)
    if not bin_path.is_absolute():
        bin_path = REPO_ROOT / bin_path
    if not bin_path.is_file():
        raise SystemExit(f"error: tracker binary missing: {bin_path}")

    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    # Write the config used for this run.
    config_path = out_root / "config.json"
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # --- Step 1: Ingest ---
    if not args.skip_ingest and not args.eval_only:
        dataroot = Path(args.dataroot)
        if not dataroot.is_absolute():
            dataroot = REPO_ROOT / dataroot
        det_json = Path(args.detections_json)
        if not det_json.is_absolute():
            det_json = REPO_ROOT / det_json
        if not dataroot.is_dir():
            raise SystemExit(
                f"error: nuScenes dataroot missing: {dataroot}\n"
                f"Download v1.0-trainval from https://www.nuscenes.org and "
                f"extract to {dataroot}"
            )
        if not det_json.is_file():
            raise SystemExit(
                f"error: detections JSON missing: {det_json}\n"
                f"Place megvii_val.json in data/raw/detections/"
            )
        run_ingest(args.version, str(dataroot), str(det_json), args.limit)

    scenes = scene_ids()
    if args.limit is not None:
        scenes = scenes[: args.limit]
    if not scenes:
        raise SystemExit("error: no normalized scenes found")

    print(f"scenes: {len(scenes)} | config: {config_name} ({label})")

    # --- Step 2: Track ---
    if not args.eval_only:
        print(f"tracking {len(scenes)} scenes (jobs={args.jobs}) ...")
        tasks = [
            (str(bin_path.resolve()), config_path, scene, out_root, args.force)
            for scene in scenes
        ]
        if args.jobs <= 1:
            results = [track_scene(t) for t in tasks]
        else:
            with ProcessPoolExecutor(max_workers=args.jobs) as pool:
                results = list(pool.map(track_scene, tasks))

        errors = [r for r in results if r["status"] == "error"]
        skips = sum(1 for r in results if r["status"] == "skip")
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"tracking done: {ok} ran, {skips} skipped, {len(errors)} errors")
        for err in errors:
            print(f"  ERROR {err['scene']}: {err['error']}", file=sys.stderr)
        if errors:
            return 1

    # --- Step 3: Evaluate ---
    print(f"evaluating {len(scenes)} scenes ...")
    per_scene: dict[str, dict] = {}
    amota_input: list = []
    for scene in scenes:
        gt_path = NORMALIZED_ROOT / scene / "gt.jsonl"
        tracks_path = out_root / f"{scene}.jsonl"
        if not gt_path.is_file() or not tracks_path.is_file():
            per_scene[scene] = {"error": "missing gt or tracks"}
            continue
        gt = load_jsonl(gt_path)
        tracks = load_jsonl(tracks_path)
        metrics, _ = evaluate_scene(gt, tracks)
        per_scene[scene] = {
            "mota": float(metrics.mota),
            "ids": int(metrics.ids),
            "fp": int(metrics.fp),
            "fn": int(metrics.fn),
            "frag": int(metrics.frag),
            "motp": float(metrics.motp),
        }
        amota_input.append((gt, tracks))

    amota = compute_amota(amota_input) if amota_input else {"all": {"amota": float("nan"), "amotp": float("nan")}}

    # --- Step 4: Timing ---
    ms: list[float] = []
    for scene in scenes:
        timing_path = out_root / f"{scene}_timing.json"
        if timing_path.is_file():
            timing = json.loads(timing_path.read_text(encoding="utf-8"))
            ms.extend(timing["ms_per_frame"])
    p99 = nearest_rank_p99(ms)

    # --- Step 5: Aggregate ---
    valid = [v for v in per_scene.values() if "error" not in v]
    total_mota = sum(v["mota"] for v in valid)
    total_ids = sum(v["ids"] for v in valid)

    payload = {
        "schema": SCHEMA,
        "config": config_name,
        "label": label,
        "scenes": per_scene,
        "totals": {
            "mota": total_mota,
            "ids": total_ids,
            "amota": float(amota["all"]["amota"]),
            "amotp": float(amota["all"]["amotp"]),
            "p99_ms": p99,
            "n_scenes": len(scenes),
            "n_evaluated": len(valid),
        },
        "provenance": {
            "commit": git_head(),
            "config": config_name,
            "bin": str(bin_path),
            "python": platform.python_version(),
            "version": args.version,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    }

    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(
        json.dumps(clean_nan(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    SUMMARY_MD.write_text(render_summary_md(payload), encoding="utf-8")
    print(f"wrote {SUMMARY_JSON.relative_to(REPO_ROOT)}")
    print(f"wrote {SUMMARY_MD.relative_to(REPO_ROOT)}")

    print(f"\n=== totals ({len(scenes)} scenes) ===")
    print(f"  MOTA:  {total_mota:.4f}")
    print(f"  IDS:   {total_ids}")
    print(f"  AMOTA: {amota['all']['amota']:.6f}")
    print(f"  AMOTP: {amota['all']['amotp']:.6f}")
    print(f"  p99:   {p99:.4f} ms" if p99 is not None else "  p99:   n/a")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
