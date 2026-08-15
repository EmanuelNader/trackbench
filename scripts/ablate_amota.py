#!/usr/bin/env python3
"""Per-cell AMOTA/AMOTP across the 24-cell ablation grid.

For each materialized cell under bench/ablation/out/<label>/, pools the cell's
per-scene track files (bench/ablation/out/<label>/scene-<id>.jsonl) against the
per-scene GT (data/normalized/<scene-id>/gt.jsonl) and writes
bench/ablation/out/<label>/amota.json:

    {"cell", "config", "scenes", "all": {"amota", "amotp"},
     "per_class": {cls: {"amota", "amotp", "recall", "motar", "confidence"}},
     "provenance": {"commit", "python", "ts"}}

The scene list is whatever `scene-*.jsonl` files exist in the cell dir (sorted).
GT and tracks are read with eval.metrics.load_jsonl; the metric is
eval.amota.compute_amota (recall-curve MOTAR, same per-frame matcher as the
CLEAR MOTA/IDS eval). NaN/inf is written as JSON null so the file is strict JSON.
Given identical inputs and commit the file is byte-identical except
`provenance.ts` (a timestamp is mandated in the schema).

Usage:
  python3 scripts/ablate_amota.py
  python3 scripts/ablate_amota.py --out-root bench/ablation/out
  python3 scripts/ablate_amota.py --force
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eval.amota import compute_amota  # noqa: E402
from eval.metrics import load_jsonl  # noqa: E402

DEFAULT_OUT_ROOT = REPO_ROOT / "bench" / "ablation" / "out"
DEFAULT_MANIFEST = REPO_ROOT / "bench" / "ablation" / "manifest.toml"
NORMALIZED_ROOT = REPO_ROOT / "data" / "normalized"
KNOBS = ["gate_m", "vel_cost_weight", "iou_weight", "min_birth_score"]


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
    cells = []
    for combo in itertools.product(*(levels[k] for k in KNOBS)):
        overrides = dict(zip(KNOBS, combo))
        config = {**defaults, **overrides}
        cells.append({"config": config, "knobs": overrides, "label": cell_label(overrides)})
    return cells


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def clean_nan(value):
    """Recursively convert float nan/inf to JSON null (strict JSON output)."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, list):
        return [clean_nan(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    return value


def compute_cell(out_root: Path, cell: dict, force: bool) -> bool:
    cell_dir = out_root / cell["label"]
    amota_path = cell_dir / "amota.json"
    if amota_path.is_file() and not force:
        print(f"skip {cell['label']}: amota.json exists (--force to rerun)")
        return False
    track_paths = sorted(cell_dir.glob("scene-*.jsonl"))
    if not track_paths:
        raise SystemExit(f"error: no scene-*.jsonl track files in {cell_dir}")
    scenes: list = []
    scene_ids: list[str] = []
    for track_path in track_paths:
        scene_id = track_path.stem
        gt_path = NORMALIZED_ROOT / scene_id / "gt.jsonl"
        if not gt_path.is_file():
            raise SystemExit(f"error: GT missing: {gt_path}")
        scenes.append((load_jsonl(gt_path), load_jsonl(track_path)))
        scene_ids.append(scene_id)
    result = compute_amota(scenes)
    payload = {
        "cell": cell["label"],
        "config": cell["config"],
        "scenes": scene_ids,
        "all": result["all"],
        "per_class": result["per_class"],
        "provenance": {
            "commit": git_head(),
            "python": platform.python_version(),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    }
    cell_dir.mkdir(parents=True, exist_ok=True)
    amota_path.write_text(
        json.dumps(clean_nan(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"  wrote {amota_path.relative_to(REPO_ROOT)} "
        f"all.amota={result['all']['amota']:.6f}"
    )
    return True


def load_amota(out_root: Path, label: str) -> dict:
    path = out_root / label / "amota.json"
    if not path.is_file():
        raise SystemExit(f"error: missing amota.json for {label}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/ablate_amota.py",
        description="Per-cell AMOTA/AMOTP over the 24-cell ablation grid.",
    )
    p.add_argument(
        "--out-root",
        default=str(DEFAULT_OUT_ROOT),
        help="cell output root (default: %(default)s)",
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
        help="compute only this cell label (repeatable)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="recompute cells that already have amota.json",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.manifest, "rb") as f:
        manifest = tomllib.load(f)
    cells = materialize_cells(manifest)
    if len(cells) != 24:
        raise SystemExit(f"error: expected 24 cells, got {len(cells)}")
    if args.only:
        cells = [c for c in cells if c["label"] in args.only]
    out_root = Path(args.out_root)

    for cell in cells:
        compute_cell(out_root, cell, args.force)

    refs = dict(manifest.get("reference", {}))
    if isinstance(refs.get("alias"), dict):
        refs.pop("alias")
    print("\nreference cell all.amota:")
    out_of_range = []
    for name, knobs in refs.items():
        label = cell_label(knobs)
        data = load_amota(out_root, label)
        amota = data["all"]["amota"]
        flag = "" if amota is not None and 0.0 <= amota <= 1.0 else "  <-- OUT OF [0,1]"
        if amota is not None and not (0.0 <= amota <= 1.0):
            out_of_range.append(label)
        print(f"  {name:<9} {label:<38} all.amota = {amota}{flag}")
    return 1 if out_of_range else 0


if __name__ == "__main__":
    raise SystemExit(main())
