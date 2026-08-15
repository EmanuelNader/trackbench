#!/usr/bin/env python3
"""One-command Phase 4 ablation sweep runner.

Usage:
  python scripts/ablate.py
  python scripts/ablate.py --only baseline [--only gate1p5-vel4p0-iou0p0-birth0p5 ...]
  python scripts/ablate.py --manifest PATH [--force]
  python scripts/ablate.py --check-determinism baseline

Materializes the 24-cell grid from the manifest, runs each requested cell
through scripts/eval_all_scenes.sh into isolated bench/ablation/out/<label>/
directories, and aggregates the per-scene *_eval.json into a per-cell
summary.json. All CLEAR-MOT evaluation and failure mining stays in
eval_all_scenes.sh / eval.run_eval; this script only orchestrates and
aggregates.

The sweep overwrites data/normalized/<scene>/{tracks.jsonl,timing.json} per
cell. Those files (and the data/tracks/ artifacts) are snapshotted once before
the sweep and restored afterwards, so an interrupted or completed run leaves
the repo's existing artifacts untouched.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import itertools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "bench" / "ablation" / "manifest.toml"
OUT_ROOT = REPO_ROOT / "bench" / "ablation" / "out"
SNAPSHOT_ROOT = OUT_ROOT / ".snapshot"
DEFAULT_CONFIG = REPO_ROOT / "core" / "config" / "default.json"
RUNNER = REPO_ROOT / "scripts" / "eval_all_scenes.sh"
NORMALIZED_ROOT = "data/normalized"
TRACKER_BIN = "core/build/trackbench_run"
KNOBS = ["gate_m", "vel_cost_weight", "iou_weight", "min_birth_score"]
SUMMARY_FIELDS = ("ids", "mota", "fp", "fn", "frag", "motp", "n_failures")


def render_float(value: float) -> str:
    return str(float(value)).replace(".", "p")


def cell_label(knobs: dict) -> str:
    return (
        f"gate{render_float(knobs['gate_m'])}"
        f"-vel{render_float(knobs['vel_cost_weight'])}"
        f"-iou{render_float(knobs['iou_weight'])}"
        f"-birth{render_float(knobs['min_birth_score'])}"
    )


def materialize_cells(manifest: dict) -> list[dict]:
    defaults = dict(manifest["defaults"])
    levels = manifest["grid"]["levels"]
    expected_keys = set(json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8")))
    cells = []
    for combo in itertools.product(*(levels[k] for k in KNOBS)):
        overrides = dict(zip(KNOBS, combo))
        config = {**defaults, **overrides}
        if set(config) != expected_keys:
            raise RuntimeError(
                f"materialized config keys {sorted(config)} != default.json keys {sorted(expected_keys)}"
            )
        cells.append({"config": config, "knobs": overrides, "label": cell_label(overrides)})
    return cells


def load_references(manifest: dict) -> tuple[dict, dict]:
    refs = dict(manifest["reference"])
    aliases = dict(manifest.get("meta", {}).get("aliases") or {})
    if isinstance(refs.get("alias"), dict):
        aliases.update(refs.pop("alias"))
    return refs, aliases


def verify_references_materialized(refs: dict, cells_by_label: dict) -> None:
    for name, knobs in refs.items():
        if set(knobs) != set(KNOBS):
            raise RuntimeError(f"reference {name!r} must define exactly the four knobs")
        if cell_label(knobs) not in cells_by_label:
            raise RuntimeError(
                f"reference {name!r} ({cell_label(knobs)}) is not materialized in the 24-cell grid"
            )


def resolve_name(name: str, cells_by_label: dict, refs: dict, aliases: dict) -> str:
    if name in cells_by_label:
        return name
    target = aliases.get(name, name)
    if target in refs and cell_label(refs[target]) in cells_by_label:
        return cell_label(refs[target])
    known = sorted(cells_by_label) + sorted(refs) + sorted(aliases)
    raise SystemExit(
        f"error: unknown cell or reference: {name!r}\n"
        f"known cells / references / aliases:\n  " + "\n  ".join(known)
    )


def resolve_python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python3"
    if venv.is_file():
        return str(venv)
    return "python3"


def preflight(python: str) -> None:
    if not (REPO_ROOT / TRACKER_BIN).is_file():
        raise SystemExit(
            f"error: tracker binary missing: {TRACKER_BIN}\nbuild with: make core"
        )
    if not (REPO_ROOT / NORMALIZED_ROOT).is_dir():
        raise SystemExit(f"error: normalized root missing: {NORMALIZED_ROOT}")
    if not RUNNER.is_file():
        raise SystemExit(f"error: runner missing: {RUNNER.relative_to(REPO_ROOT)}")
    try:
        subprocess.run(
            [python, "-c", "import numpy"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"error: eval python {python!r} cannot import numpy "
            f"(install with: python -m pip install -r requirements.lock)\n{exc}"
        )


def snapshot_originals() -> int:
    if SNAPSHOT_ROOT.exists():
        shutil.rmtree(SNAPSHOT_ROOT)
    SNAPSHOT_ROOT.mkdir(parents=True)
    n = 0
    for scene_dir in (REPO_ROOT / NORMALIZED_ROOT).iterdir():
        if not scene_dir.is_dir():
            continue
        for name in ("tracks.jsonl", "timing.json"):
            src = scene_dir / name
            if src.is_file():
                dst = SNAPSHOT_ROOT / NORMALIZED_ROOT / scene_dir.name / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                n += 1
    tracks_dir = REPO_ROOT / "data" / "tracks"
    if tracks_dir.is_dir():
        for src in sorted(tracks_dir.iterdir()):
            if src.is_file():
                dst = SNAPSHOT_ROOT / "data" / "tracks" / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                n += 1
    print(f"snapshot: saved {n} files under {SNAPSHOT_ROOT.relative_to(REPO_ROOT)}")
    return n


def restore_originals() -> int:
    n = 0
    for src in sorted(SNAPSHOT_ROOT.rglob("*")):
        if src.is_file():
            dst = REPO_ROOT / src.relative_to(SNAPSHOT_ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    print(f"restore: put back {n} files from {SNAPSHOT_ROOT.relative_to(REPO_ROOT)}")
    return n


def run_cell(label: str, config: dict, python: str) -> None:
    cell_dir = OUT_ROOT / label
    cell_dir.mkdir(parents=True, exist_ok=True)
    config_path = cell_dir / "config.json"
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    env = dict(os.environ)
    env.update(
        {
            "CONFIG": f"bench/ablation/out/{label}/config.json",
            "TRACKS_OUT_ROOT": f"bench/ablation/out/{label}",
            "TRACKER_BIN": TRACKER_BIN,
            "NORMALIZED_ROOT": NORMALIZED_ROOT,
            "PYTHON": python,
        }
    )
    print(f"  -> {RUNNER.relative_to(REPO_ROOT)} --force")
    subprocess.run(
        ["bash", str(RUNNER), "--force"],
        check=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    for scene_dir in (REPO_ROOT / NORMALIZED_ROOT).iterdir():
        if not scene_dir.is_dir():
            continue
        timing = scene_dir / "timing.json"
        if timing.is_file():
            shutil.copy2(timing, cell_dir / f"{scene_dir.name}_timing.json")


def aggregate(label: str) -> dict:
    cell_dir = OUT_ROOT / label
    scenes = {}
    for eval_path in sorted(cell_dir.glob("*_eval.json")):
        data = json.loads(eval_path.read_text(encoding="utf-8"))
        scenes[data["scene"]] = {key: data[key] for key in SUMMARY_FIELDS}
    total_ids = sum(int(scene["ids"] or 0) for scene in scenes.values())
    total_mota = sum(float(scene["mota"] or 0.0) for scene in scenes.values())
    summary = {
        "scenes": dict(sorted(scenes.items())),
        "total_ids": total_ids,
        "total_mota": total_mota,
    }
    (cell_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"  summary: total_ids={total_ids} total_mota={total_mota:.4f} "
        f"({len(scenes)} scenes)"
    )
    return summary


def check_determinism(label: str, config: dict, python: str) -> bool:
    cell_dir = OUT_ROOT / label
    print(f"=== determinism check {label} (run 1/2) ===")
    run_cell(label, config, python)
    first = {p.name: p.read_bytes() for p in sorted(cell_dir.glob("*.jsonl"))}
    print(f"=== determinism check {label} (run 2/2, --force) ===")
    run_cell(label, config, python)
    second = {p.name: p.read_bytes() for p in sorted(cell_dir.glob("*.jsonl"))}
    scenes = sorted(set(first) | set(second))
    identical = set(first) == set(second) and all(first[n] == second[n] for n in first)
    result = {
        "cell": label,
        "identical": identical,
        "scenes": {
            s: {
                "bytes": len(first[s]),
                "sha256": hashlib.sha256(first[s]).hexdigest(),
            }
            for s in scenes
            if s in first
        },
        "differs": [s for s in scenes if first.get(s) != second.get(s)],
    }
    (cell_dir / "determinism.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"determinism {label}: {'PASS' if identical else 'FAIL'} "
        f"(per-scene tracks.jsonl bytes identical across 2 forced runs, "
        f"{len(first)} scenes)"
    )
    return identical


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python scripts/ablate.py",
        description="Run the Phase 4 ablation grid.",
    )
    p.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="ablation manifest TOML (default: %(default)s)",
    )
    p.add_argument(
        "--only",
        action="append",
        metavar="LABEL",
        help="run only this cell label, reference name, or alias (repeatable)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="rerun cells even if summary.json already exists",
    )
    p.add_argument(
        "--check-determinism",
        metavar="LABEL",
        help="run this cell twice and assert per-scene tracks.jsonl bytes are identical",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.manifest, "rb") as f:
        manifest = tomllib.load(f)
    cells = materialize_cells(manifest)
    cells_by_label = {c["label"]: c for c in cells}
    if len(cells_by_label) != 24:
        raise SystemExit(
            f"error: expected 24 unique cells, got {len(cells_by_label)} "
            "(labels must be unique)"
        )
    refs, aliases = load_references(manifest)
    verify_references_materialized(refs, cells_by_label)
    python = resolve_python()
    preflight(python)

    if args.only:
        labels = []
        for name in args.only:
            labels.append(resolve_name(name, cells_by_label, refs, aliases))
        labels = list(dict.fromkeys(labels))
    elif args.check_determinism:
        labels = [resolve_name(args.check_determinism, cells_by_label, refs, aliases)]
    else:
        labels = [c["label"] for c in cells]
    dlabel = (
        resolve_name(args.check_determinism, cells_by_label, refs, aliases)
        if args.check_determinism
        else None
    )

    print(
        f"manifest: {args.manifest} | grid: {len(cells)} cells | "
        f"requested: {len(labels)} cell(s)"
    )
    snapshot_originals()
    restored = False

    def restore() -> None:
        nonlocal restored
        if not restored:
            restore_originals()
            restored = True

    atexit.register(restore)
    failures = []
    try:
        for label in labels:
            summary_path = OUT_ROOT / label / "summary.json"
            if summary_path.is_file() and not args.force:
                print(f"skip {label}: already run; --force to rerun")
                continue
            print(f"=== running {label} ===")
            try:
                run_cell(label, cells_by_label[label]["config"], python)
                aggregate(label)
            except subprocess.CalledProcessError as exc:
                failures.append(label)
                print(f"FAILED {label}: {exc}", file=sys.stderr)
        if dlabel is not None:
            try:
                ok = check_determinism(dlabel, cells_by_label[dlabel]["config"], python)
            except subprocess.CalledProcessError as exc:
                ok = False
                failures.append(f"{dlabel}: determinism run failed ({exc})")
            if not ok and not any(f.startswith(f"{dlabel}:") for f in failures):
                failures.append(f"{dlabel}: determinism check FAILED (tracks not identical)")
    finally:
        restore()

    if failures:
        print("FAILURES:")
        for label in dict.fromkeys(failures):
            print(f"  - {label}")
        return 1
    print("done: all requested cells completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
