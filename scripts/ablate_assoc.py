#!/usr/bin/env python3
"""Greedy vs Hungarian association ablation sweep.

For each of the 5 configs (4 manifest references + post003/"current") and each
association mode (hungarian, greedy), runs the tracker twice per scene into
--out/<assoc_mode>/<label>/run{1,2}/ (never into data/normalized/), audits
that run-1/run-2 per-scene track bytes are sha256-identical (exits 1 on
mismatch), computes MOTA/IDS per scene via eval.metrics.evaluate_scene,
AMOTA/AMOTP via eval.amota.compute_amota (10 scenes), and pooled nearest-rank
p99 over all run-2 timing ms_per_frame values. Emits bench/assoc/sweep.json
(metrics, greedy-hungarian deltas, determinism, provenance) and
bench/assoc/SWEEP.md.

Hungarian runs use the committed cell's config.json directly (missing assoc_mode
defaults to "hungarian"). Greedy runs inject assoc_mode=greedy into a copy of
the cell's config.

Skip mode (nothing to run, no --force) leaves existing outputs byte-untouched.

Usage:
  python3 scripts/ablate_assoc.py
  python3 scripts/ablate_assoc.py --configs baseline post003
  python3 scripts/ablate_assoc.py --force
"""

from __future__ import annotations

import argparse
import copy
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

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eval.metrics import evaluate_scene, load_jsonl  # noqa: E402
from eval.amota import compute_amota  # noqa: E402
from bench.ablation.summarize import cell_label, materialize_cells, load_references  # noqa: E402

MANIFEST = REPO_ROOT / "bench" / "ablation" / "manifest.toml"
NORMALIZED_ROOT = REPO_ROOT / "data" / "normalized"
ABLATION_OUT = REPO_ROOT / "bench" / "ablation" / "out"
DEFAULT_OUT = REPO_ROOT / "bench" / "assoc" / "out"
SWEEP_JSON = REPO_ROOT / "bench" / "assoc" / "sweep.json"
SWEEP_MD = REPO_ROOT / "bench" / "assoc" / "SWEEP.md"
DEFAULT_BIN = "core/build/trackbench_run"
SCHEMA = "trackbench/assoc-sweep/v1"
CROSS_TOL = 1e-6


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


def nearest_rank_p99(values):
    """Nearest-rank p99 over ``values`` (sorted ascending), or None if empty."""
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


def run_scene(binary: str, config_path: Path, scene: str, tracks_out: Path, timing_out: Path) -> None:
    dets = NORMALIZED_ROOT / scene / "detections.jsonl"
    subprocess.run(
        [
            binary,
            "--dets",
            str(dets),
            "--config",
            str(config_path),
            "--out",
            str(tracks_out),
            "--timing",
            str(timing_out),
        ],
        check=True,
    )


def run_one(
    binary: str,
    assoc_mode: str,
    label: str,
    base_config: dict,
    out_root: Path,
    scenes: list[str],
    force: bool,
) -> bool:
    """Run both runs of one (assoc_mode, config) cell; return True if anything ran."""
    cell_dir = out_root / assoc_mode / label
    ran = False
    for run_no in (1, 2):
        run_dir = cell_dir / f"run{run_no}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            tracks_out = run_dir / f"{scene}.jsonl"
            timing_out = run_dir / f"{scene}_timing.json"
            if not force and tracks_out.is_file() and timing_out.is_file():
                continue
            if assoc_mode == "greedy":
                cfg = copy.deepcopy(base_config)
                cfg["assoc_mode"] = "greedy"
                config_path = run_dir / "config.json"
                config_path.write_text(
                    json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            else:
                config_path = ABLATION_OUT / label / "config.json"
            run_scene(binary, config_path, scene, tracks_out, timing_out)
            ran = True
    return ran


def audit_determinism(cell_dir: Path, scenes: list[str]) -> dict:
    """sha256 compare of per-scene run1/run2 track files; empty differs = pass."""
    run1, run2 = cell_dir / "run1", cell_dir / "run2"
    differs: list[str] = []
    for scene in scenes:
        b1 = (run1 / f"{scene}.jsonl").read_bytes()
        b2 = (run2 / f"{scene}.jsonl").read_bytes()
        if b1 != b2:
            differs.append(scene)
    return {
        "pass": not differs,
        "differs": differs,
        "scene_bytes_compared": len(scenes),
    }


def compute_metrics(cell_dir: Path, scenes: list[str]) -> dict:
    """MOTA/IDS (run 1), AMOTA/AMOTP (run 1), pooled nearest-rank p99 (run 2)."""
    run1, run2 = cell_dir / "run1", cell_dir / "run2"
    gt_scenes = [(load_jsonl(NORMALIZED_ROOT / s / "gt.jsonl")) for s in scenes]
    per_scene: dict[str, dict] = {}
    amota_input: list = []
    for scene, gt in zip(scenes, gt_scenes):
        tracks = load_jsonl(run1 / f"{scene}.jsonl")
        metrics, _ = evaluate_scene(gt, tracks)
        per_scene[scene] = {"mota": float(metrics.mota), "ids": int(metrics.ids)}
        amota_input.append((gt, tracks))
    amota = compute_amota(amota_input)

    ms: list[float] = []
    for scene in scenes:
        timing = json.loads((run2 / f"{scene}_timing.json").read_text(encoding="utf-8"))
        ms.extend(timing["ms_per_frame"])
    p99 = nearest_rank_p99(ms)
    if p99 is None:
        raise SystemExit(f"error: no ms_per_frame values in {cell_dir / 'run2'} timing files")

    return {
        "mota": float(sum(v["mota"] for v in per_scene.values())),
        "ids": int(sum(v["ids"] for v in per_scene.values())),
        "amota": float(amota["all"]["amota"]),
        "amotp": float(amota["all"]["amotp"]),
        "p99_ms": p99,
        "scenes": per_scene,
    }


def render_sweep_json(configs_results: dict, deltas: dict, args) -> dict:
    return {
        "schema": SCHEMA,
        "configs": configs_results,
        "deltas": deltas,
        "provenance": {
            "commit": git_head(),
            "bin": args.binary,
            "python": platform.python_version(),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    }


def fmt_val(value, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def fmt_signed(value, digits: int) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}"


def render_sweep_md(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# Greedy vs Hungarian — association ablation sweep")
    lines.append("")
    lines.append(
        "Machine-generated by `scripts/ablate_assoc.py`. Do not hand-edit; "
        "regenerate with `python3 scripts/ablate_assoc.py`."
    )
    lines.append("")
    lines.append("## Per config+assoc_mode metrics")
    lines.append("")
    lines.append(
        "| config | assoc_mode | MOTA | IDS | AMOTA | AMOTP | p99 ms | determinism |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    configs = payload["configs"]
    seen_table: set[tuple[str, str]] = set()
    for label in sorted(configs):
        for e in configs[label]:
            am = e["assoc_mode"]
            key = (label, am)
            if key in seen_table:
                continue
            seen_table.add(key)
            lines.append(
                f"| {label} | {am} | "
                f"{fmt_val(e['mota'], 6)} | {e['ids']} | "
                f"{fmt_val(e['amota'], 6)} | {fmt_val(e['amotp'], 6)} | "
                f"{fmt_val(e['p99_ms'], 4)} | "
                f"{'PASS' if e['determinism']['pass'] else 'FAIL'} |"
            )
    lines.append("")
    lines.append("## Greedy − Hungarian deltas")
    lines.append("")
    lines.append("| config | ΔMOTA | ΔIDS | ΔAMOTA | ΔAMOTP | Δp99 ms |")
    lines.append("|---|---|---|---|---|---|")
    for label in sorted(payload["deltas"]):
        d = payload["deltas"][label]
        lines.append(
            f"| {label} | {fmt_signed(d['mota'], 6)} | "
            f"{d['ids']:+d} | {fmt_signed(d['amota'], 6)} | "
            f"{fmt_signed(d['amotp'], 6)} | {fmt_signed(d['p99_ms'], 4)} |"
        )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- commit: `{payload['provenance']['commit']}`")
    lines.append(f"- tracker binary: `{payload['provenance']['bin']}`")
    lines.append(f"- python: {payload['provenance']['python']}")
    lines.append(f"- ts: {payload['provenance']['ts']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/ablate_assoc.py",
        description="Greedy vs Hungarian association ablation sweep across reference cells.",
    )
    p.add_argument(
        "--configs",
        action="append",
        metavar="REF",
        help="manifest reference name or alias (repeatable; default: all 5)",
    )
    p.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="sweep output root (default: %(default)s)",
    )
    p.add_argument(
        "--binary",
        default=DEFAULT_BIN,
        help="tracker binary (default: %(default)s)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="rerun every (assoc_mode, config) cell even if outputs exist",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    with open(MANIFEST, "rb") as f:
        manifest = tomllib.load(f)
    cells = materialize_cells(manifest)
    cells_by_label = {c["label"]: c for c in cells}
    if len(cells_by_label) != 24:
        raise SystemExit("error: expected 24 unique cells in the ablation grid")
    refs = load_references(manifest)
    aliases = dict(manifest.get("meta", {}).get("status", {}).get("aliases") or {})
    ref_alias = manifest.get("reference", {}).get("alias") or {}
    if isinstance(ref_alias, dict):
        aliases.update(ref_alias)

    selected = list(args.configs or [])
    resolved = []
    config_names = []
    for name in selected:
        if name in refs:
            resolved.append(name)
            config_names.append(name)
        elif name in aliases and aliases[name] in refs:
            resolved.append(aliases[name])
            config_names.append(name)
        else:
            raise SystemExit(
                f"error: unknown reference {name!r}; known: {', '.join(refs)}"
            )
    if not resolved:
        resolved = list(refs)
        config_names = list(refs)
        if "current" in aliases:
            resolved.append(aliases["current"])
            config_names.append("current")

    bin_path = Path(args.binary)
    if not bin_path.is_absolute():
        bin_path = REPO_ROOT / bin_path
    if not bin_path.is_file():
        raise SystemExit(
            f"error: tracker binary missing: {bin_path} "
            f"(build with `make core`)"
        )

    scenes = scene_ids()
    if len(scenes) != 10:
        print(f"warning: expected 10 normalized scenes, found {len(scenes)}", file=sys.stderr)

    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root

    assoc_modes = ["hungarian", "greedy"]
    configs_results: dict[str, list] = {}
    cell_metrics: dict[tuple[str, str], dict] = {}
    failures: list[str] = []
    ran_any = False

    seen_cells: set[tuple[str, str]] = set()
    for assoc_mode in assoc_modes:
        for ref_name, config_name in zip(resolved, config_names):
            label = cell_label(refs[ref_name])
            cell_key = (assoc_mode, label)
            if cell_key not in seen_cells:
                seen_cells.add(cell_key)
                base_config = cells_by_label[label]["config"]
                ran = run_one(
                    str(bin_path.resolve()), assoc_mode, label, base_config,
                    out_root, scenes, args.force,
                )
                ran_any = ran_any or ran

            cell_dir = out_root / assoc_mode / label
            det = audit_determinism(cell_dir, scenes)
            if not det["pass"]:
                failures.append(
                    f"{assoc_mode}/{label} ({config_name}): determinism FAIL "
                    f"({', '.join(det['differs'])})"
                )
                print(
                    f"determinism {assoc_mode}/{label} ({config_name}): FAIL — differing scene(s): "
                    + ", ".join(det["differs"]),
                    file=sys.stderr,
                )
            else:
                print(
                    f"determinism {assoc_mode}/{label} ({config_name}): PASS "
                    f"(run1/run2 sha256-identical for {det['scene_bytes_compared']} scenes)"
                )

            if cell_key not in cell_metrics:
                metrics = compute_metrics(cell_dir, scenes)
                cell_metrics[cell_key] = {
                    "mota": metrics["mota"],
                    "ids": metrics["ids"],
                    "amota": metrics["amota"],
                    "amotp": metrics["amotp"],
                    "p99_ms": metrics["p99_ms"],
                    "determinism": {
                        "pass": det["pass"],
                        "scene_bytes_compared": det["scene_bytes_compared"],
                    },
                    "scenes": metrics["scenes"],
                }

            entry = {
                "label": label,
                "reference": config_name,
                "assoc_mode": assoc_mode,
                **cell_metrics[cell_key],
            }
            configs_results.setdefault(label, []).append(entry)

    if failures:
        print("FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    deltas: dict[str, dict] = {}
    unique_labels = {cell_label(refs[r]) for r in resolved}
    for label in unique_labels:
        hun_key = ("hungarian", label)
        gr_key = ("greedy", label)
        if hun_key not in cell_metrics or gr_key not in cell_metrics:
            continue
        hun_m, gr_m = cell_metrics[hun_key], cell_metrics[gr_key]
        deltas[label] = {
            "mota": gr_m["mota"] - hun_m["mota"],
            "ids": gr_m["ids"] - hun_m["ids"],
            "amota": gr_m["amota"] - hun_m["amota"],
            "amotp": gr_m["amotp"] - hun_m["amotp"],
            "p99_ms": None
            if gr_m["p99_ms"] is None or hun_m["p99_ms"] is None
            else gr_m["p99_ms"] - hun_m["p99_ms"],
        }

    payload = render_sweep_json(configs_results, deltas, args)

    if not ran_any and SWEEP_JSON.is_file():
        print(
            f"skip: {SWEEP_JSON.relative_to(REPO_ROOT)} exists and nothing re-ran "
            "(use --force to rerun)"
        )
        return 0

    SWEEP_JSON.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_JSON.write_text(
        json.dumps(clean_nan(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    SWEEP_MD.write_text(render_sweep_md(payload), encoding="utf-8")
    print(f"wrote {SWEEP_JSON.relative_to(REPO_ROOT)}")
    print(f"wrote {SWEEP_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
