"""Normalize nuScenes mini (+ Megvii detections) into TrackBench JSONL.

CLI::

    python -m ingest.nuscenes_ingest [--synthetic] ...

Synthetic mode (``--synthetic``, or automatic when dataroot / detections JSON
are missing) writes a tiny demo scene under
``data/normalized/synthetic_scene_001/`` so M0 can run without downloading the
~4 GB nuScenes mini set. A copy is also written to
``data/fixtures/synthetic_scene_001/`` for CI.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ingest.schema import FrameDetections, FrameGT, GTBox, Detection
from ingest.transforms import global_to_ego, nuscenes_size_to_lwh, quat_to_yaw

SYNTHETIC_SCENE_NAME = "synthetic_scene_001"
DEFAULT_DATAROOT = "./data/raw/nuscenes"
DEFAULT_OUT_ROOT = "./data/normalized"
DEFAULT_VERSION = "v1.0-mini"
DEFAULT_DETECTIONS_JSON = "./data/raw/detections/megvii_val.json"
FIXTURES_ROOT = Path("data/fixtures")

# nuScenes visibility level string → int 1–4 (0 = unknown / missing)
_VISIBILITY_LEVEL = {
    "v0-40": 1,
    "v40-60": 2,
    "v60-80": 3,
    "v80-100": 4,
}


def parse_scene_description(description: str) -> dict[str, str]:
    """Heuristic weather / timeOfDay from a nuScenes scene.description string."""
    desc = description or ""
    lower = desc.lower()

    if "rain" in lower:
        weather = "rain"
    elif "fog" in lower:
        weather = "fog"
    elif "snow" in lower:
        weather = "snow"
    else:
        weather = "clear"

    if "night" in lower:
        time_of_day = "night"
    elif "dusk" in lower or "evening" in lower or "sunset" in lower:
        time_of_day = "dusk"
    elif "dawn" in lower or "morning" in lower or "sunrise" in lower:
        time_of_day = "dawn"
    else:
        time_of_day = "day"

    return {
        "weather": weather,
        "timeOfDay": time_of_day,
        "description": desc,
    }


def _scene_outputs_exist(scene_dir: Path) -> bool:
    return (
        (scene_dir / "detections.jsonl").is_file()
        and (scene_dir / "gt.jsonl").is_file()
        and (scene_dir / "scene_meta.json").is_file()
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_scene_meta(scene_dir: Path, meta: Mapping[str, Any]) -> None:
    scene_dir.mkdir(parents=True, exist_ok=True)
    with (scene_dir / "scene_meta.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")


def write_synthetic_scene(
    out_root: Path,
    *,
    force: bool = False,
    also_fixtures: bool = True,
) -> Path:
    """Write a deterministic 20-frame scene with two cars crossing.

    Returns the normalized scene directory.
    """
    scene_dir = out_root / SYNTHETIC_SCENE_NAME
    if _scene_outputs_exist(scene_dir) and not force:
        print(f"skip existing synthetic scene: {scene_dir} (use --force to rewrite)")
        if also_fixtures:
            _copy_to_fixtures(scene_dir)
        return scene_dir

    n_frames = 20
    dt = 0.5  # seconds
    det_rows: list[FrameDetections] = []
    gt_rows: list[FrameGT] = []

    for frame in range(n_frames):
        t = frame * dt
        # Car A: moves +x (forward), starts left of ego
        ax = -10.0 + 1.0 * frame
        ay = 4.0
        # Car B: moves -x, starts ahead/right — paths cross in BEV
        bx = 10.0 - 1.0 * frame
        by = -3.0 + 0.35 * frame

        def _box(
            track_id: str,
            cls: str,
            x: float,
            y: float,
            yaw: float,
            score: float,
            visibility: int,
        ) -> GTBox:
            return {
                "cls": cls,
                "x": x,
                "y": y,
                "z": 0.0,
                "l": 4.5,
                "w": 1.8,
                "h": 1.6,
                "yaw": yaw,
                "score": score,
                "id": track_id,
                "visibility": visibility,
            }

        gt_a = _box("car-a", "car", ax, ay, 0.0, 1.0, 4)
        gt_b = _box("car-b", "car", bx, by, 3.141592653589793, 1.0, 4)

        # Detections ≈ GT with small deterministic offset / score
        det_a: Detection = {
            "cls": "car",
            "x": ax + 0.05,
            "y": ay - 0.02,
            "z": 0.0,
            "l": 4.5,
            "w": 1.8,
            "h": 1.6,
            "yaw": 0.0,
            "score": 0.91,
        }
        det_b: Detection = {
            "cls": "car",
            "x": bx - 0.03,
            "y": by + 0.04,
            "z": 0.0,
            "l": 4.5,
            "w": 1.8,
            "h": 1.6,
            "yaw": 3.141592653589793,
            "score": 0.88,
        }

        det_rows.append({"frame": frame, "t": t, "dets": [det_a, det_b]})
        gt_rows.append({"frame": frame, "t": t, "dets": [gt_a, gt_b]})

    meta = {
        "scene_name": SYNTHETIC_SCENE_NAME,
        "scene_token": "synthetic",
        "source": "synthetic",
        "n_frames": n_frames,
        "weather": "clear",
        "timeOfDay": "day",
        "description": "synthetic two-car crossing scene for M0 demo / CI",
    }

    _write_jsonl(scene_dir / "detections.jsonl", det_rows)
    _write_jsonl(scene_dir / "gt.jsonl", gt_rows)
    _write_scene_meta(scene_dir, meta)
    print(f"wrote synthetic scene → {scene_dir}")

    if also_fixtures:
        _copy_to_fixtures(scene_dir)

    return scene_dir


# Files produced by the tracker/eval golden path — never overwrite via ingest.
_PRESERVE_FIXTURE_NAMES = frozenset(
    {
        "tracks_expected.jsonl",
        "demo_bundle.json",
        "demo_run.json",
    }
)


def _copy_to_fixtures(scene_dir: Path) -> None:
    """Sync ingest outputs into data/fixtures/, preserving golden/demo artifacts."""
    dest = FIXTURES_ROOT / scene_dir.name
    preserved: dict[str, bytes] = {}
    if dest.exists():
        for name in _PRESERVE_FIXTURE_NAMES:
            p = dest / name
            if p.is_file():
                preserved[name] = p.read_bytes()
        shutil.rmtree(dest)
    shutil.copytree(scene_dir, dest)
    for name, data in preserved.items():
        (dest / name).write_bytes(data)
    print(f"copied fixture → {dest}")


def _visibility_int(nusc: Any, ann: Mapping[str, Any]) -> int:
    token = ann.get("visibility_token")
    if not token:
        return 0
    try:
        rec = nusc.get("visibility", token)
    except KeyError:
        return 0
    level = rec.get("level", "")
    return _VISIBILITY_LEVEL.get(level, 0)


def _category_to_cls(name: str) -> str:
    """Map nuScenes category / detection_name to a short cls string."""
    # e.g. "vehicle.car" → "car"; detection_name is already short
    if "." in name:
        return name.split(".")[-1]
    return name


def _load_detections_json(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict) and "results" in payload:
        return payload["results"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"unexpected detections JSON shape in {path}")


def _iter_scene_samples(nusc: Any, scene: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Keyframe samples for a scene, sorted by timestamp."""
    samples: list[dict[str, Any]] = []
    token = scene["first_sample_token"]
    while token:
        sample = nusc.get("sample", token)
        samples.append(sample)
        token = sample["next"]
    samples.sort(key=lambda s: s["timestamp"])
    return samples


def _ego_pose_for_sample(nusc: Any, sample: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    """Return (translation, rotation[w,x,y,z]) for the LIDAR_TOP ego pose."""
    sd_token = sample["data"]["LIDAR_TOP"]
    sd = nusc.get("sample_data", sd_token)
    pose = nusc.get("ego_pose", sd["ego_pose_token"])
    return list(pose["translation"]), list(pose["rotation"])


def ingest_scene(
    nusc: Any,
    scene: Mapping[str, Any],
    results: Mapping[str, list[dict[str, Any]]],
    out_root: Path,
    *,
    force: bool = False,
) -> Optional[Path]:
    """Ingest one nuScenes scene to normalized JSONL. Returns scene_dir or None if skipped."""
    scene_name = scene["name"]
    scene_dir = out_root / scene_name
    if _scene_outputs_exist(scene_dir) and not force:
        print(f"skip existing scene: {scene_name} (use --force to rewrite)")
        return scene_dir

    samples = _iter_scene_samples(nusc, scene)
    if not samples:
        print(f"warning: scene {scene_name} has no samples", file=sys.stderr)
        return None

    t0 = samples[0]["timestamp"] * 1e-6  # us → s
    det_rows: list[FrameDetections] = []
    gt_rows: list[FrameGT] = []

    for frame_idx, sample in enumerate(samples):
        t = sample["timestamp"] * 1e-6 - t0
        ego_t, ego_r = _ego_pose_for_sample(nusc, sample)

        # --- GT annotations (global → ego) ---
        gt_dets: list[GTBox] = []
        for ann_token in sample["anns"]:
            ann = nusc.get("sample_annotation", ann_token)
            yaw_g = quat_to_yaw(ann["rotation"])
            x, y, z, yaw = global_to_ego(
                ann["translation"], yaw_g, ego_t, ego_r
            )
            # ann size is [w, l, h]
            l, w, h = nuscenes_size_to_lwh(ann["size"])
            gt_dets.append(
                {
                    "cls": _category_to_cls(ann["category_name"]),
                    "x": x,
                    "y": y,
                    "z": z,
                    "l": l,
                    "w": w,
                    "h": h,
                    "yaw": yaw,
                    "score": 1.0,
                    "id": ann["instance_token"],
                    "visibility": _visibility_int(nusc, ann),
                }
            )

        # --- Detections from Megvii-style results ---
        frame_dets: list[Detection] = []
        for det in results.get(sample["token"], []):
            yaw_g = quat_to_yaw(det["rotation"])
            x, y, z, yaw = global_to_ego(
                det["translation"], yaw_g, ego_t, ego_r
            )
            l, w, h = nuscenes_size_to_lwh(det["size"])
            frame_dets.append(
                {
                    "cls": _category_to_cls(det.get("detection_name", "unknown")),
                    "x": x,
                    "y": y,
                    "z": z,
                    "l": l,
                    "w": w,
                    "h": h,
                    "yaw": yaw,
                    "score": float(det.get("detection_score", 0.0)),
                }
            )

        det_rows.append({"frame": frame_idx, "t": t, "dets": frame_dets})
        gt_rows.append({"frame": frame_idx, "t": t, "dets": gt_dets})

    parsed = parse_scene_description(scene.get("description", ""))
    meta = {
        "scene_name": scene_name,
        "scene_token": scene["token"],
        "source": "nuscenes",
        "n_frames": len(samples),
        "weather": parsed["weather"],
        "timeOfDay": parsed["timeOfDay"],
        "description": parsed["description"],
    }

    _write_jsonl(scene_dir / "detections.jsonl", det_rows)
    _write_jsonl(scene_dir / "gt.jsonl", gt_rows)
    _write_scene_meta(scene_dir, meta)
    print(f"wrote scene → {scene_dir} ({len(samples)} frames)")
    return scene_dir


def _dataroot_ready(dataroot: Path, version: str) -> bool:
    return dataroot.is_dir() and (dataroot / version).is_dir()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ingest.nuscenes_ingest",
        description=(
            "Normalize nuScenes keyframes (+ Megvii detections) into ego-frame "
            "JSONL under --out-root.\n\n"
            "SYNTHETIC / OFFLINE DEMO: pass --synthetic, OR omit real data. If "
            "dataroot or --detections-json is missing, this tool automatically "
            "writes a small synthetic scene to "
            f"{DEFAULT_OUT_ROOT}/{SYNTHETIC_SCENE_NAME}/ "
            "(and data/fixtures/) so M0 can demo without the ~4 GB download."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dataroot",
        default=os.environ.get("NUSCENES_DATAROOT", DEFAULT_DATAROOT),
        help=f"nuScenes dataroot (env NUSCENES_DATAROOT, default {DEFAULT_DATAROOT})",
    )
    p.add_argument(
        "--version",
        default=os.environ.get("NUSCENES_VERSION", DEFAULT_VERSION),
        help=f"nuScenes version string (default {DEFAULT_VERSION})",
    )
    p.add_argument(
        "--detections-json",
        default=os.environ.get("DETECTIONS_JSON", DEFAULT_DETECTIONS_JSON),
        help=(
            "Megvii-style detection results JSON "
            f"(env DETECTIONS_JSON, default {DEFAULT_DETECTIONS_JSON})"
        ),
    )
    p.add_argument(
        "--out-root",
        default=os.environ.get("NORMALIZED_ROOT", DEFAULT_OUT_ROOT),
        help=f"output root for per-scene folders (default {DEFAULT_OUT_ROOT})",
    )
    p.add_argument(
        "--scene",
        default=None,
        help="optional scene name or token; if omitted, process all (or --limit)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="process only the first N scenes",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="re-write outputs even if detections.jsonl / gt.jsonl already exist",
    )
    p.add_argument(
        "--synthetic",
        action="store_true",
        help=(
            "write the synthetic demo scene only (no nuScenes download). "
            "Also selected automatically when dataroot or detections JSON is missing."
        ),
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out_root = Path(args.out_root)
    dataroot = Path(args.dataroot)
    detections_json = Path(args.detections_json)

    use_synthetic = bool(args.synthetic)
    if not use_synthetic:
        if not _dataroot_ready(dataroot, args.version) or not detections_json.is_file():
            print(
                "dataroot and/or detections JSON missing — falling back to "
                f"synthetic scene ({SYNTHETIC_SCENE_NAME}). "
                "Pass --synthetic to silence this, or provide real data "
                "(see docs/data.md).",
                file=sys.stderr,
            )
            use_synthetic = True

    if use_synthetic:
        write_synthetic_scene(out_root, force=args.force, also_fixtures=True)
        return 0

    # Lazy import: synthetic / missing-data path must work without nuscenes-devkit.
    try:
        from nuscenes.nuscenes import NuScenes  # type: ignore
    except ImportError as exc:
        print(
            "nuscenes-devkit is required for real ingest but is not installed. "
            "Install requirements.txt, or re-run with --synthetic.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    print(f"loading NuScenes {args.version} from {dataroot} ...")
    nusc = NuScenes(version=args.version, dataroot=str(dataroot), verbose=True)
    results = _load_detections_json(detections_json)

    scenes = list(nusc.scene)
    if args.scene:
        key = args.scene
        scenes = [s for s in scenes if s["name"] == key or s["token"] == key]
        if not scenes:
            print(f"error: no scene matching {key!r}", file=sys.stderr)
            return 1

    if args.limit is not None:
        scenes = scenes[: max(0, args.limit)]

    if not scenes:
        print("error: no scenes to process", file=sys.stderr)
        return 1

    for scene in scenes:
        ingest_scene(nusc, scene, results, out_root, force=args.force)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
