#!/usr/bin/env python3
"""CTRV vs CV motion-model ablation sweep.

For each of the 5 configs (4 manifest references + post003/"current") and each
motion model (cv, ctrv), runs the tracker twice per scene into
--out/<motion_model>/<label>/run{1,2}/ (never into data/normalized/), audits
that run-1/run-2 per-scene track bytes are sha256-identical (exits 1 on
mismatch), computes MOTA/IDS per scene via eval.metrics.evaluate_scene,
AMOTA/AMOTP via eval.amota.compute_amota (10 scenes), and pooled nearest-rank
p99 over all run-2 timing ms_per_frame values. Emits bench/ctrv/sweep.json
(metrics, CTRV-CV deltas, determinism, provenance) and bench/ctrv/SWEEP.md.

CV runs use the committed cell's config.json directly (missing motion_model
defaults to "cv"). CTRRV runs inject motion_model=ctrv and
process_var_yawrate into a copy of the cell's config.

Skip mode (nothing to run, no --force) leaves existing outputs byte-untouched.

Usage:
  python3 scripts/ablate_ctrv.py
  python3 scripts/ablate_ctrv.py --configs baseline post003
  python3 scripts/ablate_ctrv.py --yawrate 0.2
  python3 scripts/ablate_ctrv.py --force
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
DEFAULT_OUT = REPO_ROOT / "bench" / "ctrv" / "out"
SWEEP_JSON = REPO_ROOT / "bench" / "ctrv" / "sweep.json"
SWEEP_MD = REPO_ROOT / "bench" / "ctrv" / "SWEEP.md"
DEFAULT_BIN = "core/build/trackbench_run"
SCHEMA = "trackbench/ctrv-sweep/v1"
CROSS_TOL = 1e-6  # tolerance for the CV-vs-committed sanity cross-check


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


def make_ctrv_config(cv_config: dict, yawrate: float) -> dict:
    cfg = copy.deepcopy(cv_config)
    cfg["motion_model"] = "ctrv"
    cfg["process_var_yawrate"] = yawrate
    return cfg


def run_one(
    binary: str,
    motion_model: str,
    label: str,
    cv_config: dict,
    out_root: Path,
    scenes: list[str],
    force: bool,
    yawrate: float,
) -> bool:
    """Run both runs of one (motion_model, config) cell; return True if anything ran."""
    cell_dir = out_root / motion_model / label
    ran = False
    for run_no in (1, 2):
        run_dir = cell_dir / f"run{run_no}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            tracks_out = run_dir / f"{scene}.jsonl"
            timing_out = run_dir / f"{scene}_timing.json"
            if not force and tracks_out.is_file() and timing_out.is_file():
                continue
            if motion_model == "ctrv":
                cfg = make_ctrv_config(cv_config, yawrate)
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


def cross_check_cv(configs_results: dict) -> list[str]:
    """Compare CV sweep values to committed ablation cell outputs."""
    problems: list[str] = []
    checked: set[str] = set()
    for label, entries in configs_results.items():
        if label in checked:
            continue
        checked.add(label)
        cv_entry = next((e for e in entries if e["motion_model"] == "cv"), None)
        if cv_entry is None:
            continue
        summary_path = ABLATION_OUT / label / "summary.json"
        amota_path = ABLATION_OUT / label / "amota.json"
        if not summary_path.is_file() or not amota_path.is_file():
            problems.append(
                f"{label}: committed bench/ablation/out/{label} summary.json/amota.json missing"
            )
            continue
        committed_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        committed_amota = json.loads(amota_path.read_text(encoding="utf-8"))
        diffs = []
        if cv_entry["ids"] != committed_summary["total_ids"]:
            diffs.append(
                f"ids {cv_entry['ids']} vs committed {committed_summary['total_ids']}"
            )
        for key, committed_key in (
            ("mota", "total_mota"),
            ("amota", "amota"),
            ("amotp", "amotp"),
        ):
            got, want = cv_entry[key], committed_amota["all"][committed_key] if committed_key in committed_amota.get("all", {}) else committed_summary.get(committed_key)
            if committed_key in committed_amota.get("all", {}):
                want = committed_amota["all"][committed_key]
            else:
                want = committed_summary[committed_key]
            if math.isnan(got) or math.isnan(want) or abs(got - want) > CROSS_TOL:
                diffs.append(f"{key} {got} vs committed {want}")
        scene_diffs = 0
        for scene, got in cv_entry["scenes"].items():
            want = committed_summary["scenes"].get(scene)
            if want is None:
                scene_diffs += 1
                continue
            if got["ids"] != want["ids"] or abs(got["mota"] - want["mota"]) > CROSS_TOL:
                scene_diffs += 1
        if scene_diffs:
            diffs.append(f"{scene_diffs} per-scene mota/ids mismatches")
        if diffs:
            problems.append(f"{label} (cv): drift — " + "; ".join(diffs))
    return problems


def render_sweep_json(configs_results: dict, deltas: dict, args) -> dict:
    return {
        "schema": SCHEMA,
        "configs": configs_results,
        "deltas": deltas,
        "provenance": {
            "commit": git_head(),
            "bin": args.binary,
            "python": platform.python_version(),
            "yawrate": args.yawrate,
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
    lines.append("# CTRRV vs CV — motion-model ablation sweep")
    lines.append("")
    lines.append(
        "Machine-generated by `scripts/ablate_ctrv.py`. Do not hand-edit; "
        "regenerate with `python3 scripts/ablate_ctrv.py`."
    )
    lines.append("")
    lines.append("## Per config+motion_model metrics")
    lines.append("")
    lines.append(
        "| config | motion_model | MOTA | IDS | AMOTA | AMOTP | p99 ms | determinism |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    configs = payload["configs"]
    seen_table: set[tuple[str, str]] = set()
    for label in sorted(configs):
        for e in configs[label]:
            mm = e["motion_model"]
            key = (label, mm)
            if key in seen_table:
                continue
            seen_table.add(key)
            lines.append(
                f"| {label} | {mm} | "
                f"{fmt_val(e['mota'], 6)} | {e['ids']} | "
                f"{fmt_val(e['amota'], 6)} | {fmt_val(e['amotp'], 6)} | "
                f"{fmt_val(e['p99_ms'], 4)} | "
                f"{'PASS' if e['determinism']['pass'] else 'FAIL'} |"
            )
    lines.append("")
    lines.append("## CTRRV − CV deltas")
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
    lines.append(f"- yawrate: {payload['provenance']['yawrate']}")
    lines.append(f"- ts: {payload['provenance']['ts']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/ablate_ctrv.py",
        description="CTRV vs CV motion-model ablation sweep across reference cells.",
    )
    p.add_argument(
        "--configs",
        action="append",
        metavar="REF",
        help="manifest reference name or alias (repeatable; default: all 5)",
    )
    p.add_argument(
        "--yawrate",
        type=float,
        default=0.1,
        help="process_var_yawrate for CTRRV configs (default: %(default)s)",
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
        help="rerun every (motion_model, config) cell even if outputs exist",
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
    config_names = []  # original user-provided names, parallel to resolved
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
    # Keep all config names (no name-level dedup) so sweep.json lists each.
    # Cell-label dedup happens below to avoid running the same cell twice.

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

    motion_models = ["cv", "ctrv"]
    configs_results: dict[str, list] = {}
    # Map (motion_model, cell_label) -> metrics entry (computed once per unique cell)
    cell_metrics: dict[tuple[str, str], dict] = {}
    failures: list[str] = []
    ran_any = False

    # Run each unique (motion_model, cell_label) once; audit and record for all config names
    seen_cells: set[tuple[str, str]] = set()
    for motion_model in motion_models:
        for ref_name, config_name in zip(resolved, config_names):
            label = cell_label(refs[ref_name])
            cell_key = (motion_model, label)
            if cell_key not in seen_cells:
                seen_cells.add(cell_key)
                cv_config = cells_by_label[label]["config"]
                cell_dir = out_root / motion_model / label
                ran = run_one(
                    str(bin_path.resolve()), motion_model, label, cv_config,
                    out_root, scenes, args.force, args.yawrate,
                )
                ran_any = ran_any or ran

            cell_dir = out_root / motion_model / label
            det = audit_determinism(cell_dir, scenes)
            if not det["pass"]:
                failures.append(
                    f"{motion_model}/{label} ({config_name}): determinism FAIL "
                    f"({', '.join(det['differs'])})"
                )
                print(
                    f"determinism {motion_model}/{label} ({config_name}): FAIL — differing scene(s): "
                    + ", ".join(det["differs"]),
                    file=sys.stderr,
                )
            else:
                print(
                    f"determinism {motion_model}/{label} ({config_name}): PASS "
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

            # Record entry for this config name (may share metrics with another name)
            entry = {
                "label": label,
                "reference": config_name,
                "motion_model": motion_model,
                **cell_metrics[cell_key],
            }
            configs_results.setdefault(label, []).append(entry)

    if failures:
        print("FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    problems = cross_check_cv(configs_results)
    if problems:
        print("CV-VS-COMMITTED DRIFT:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        print(
            "STOP: the CV sweep no longer matches the committed cell outputs; "
            "investigate before proceeding.",
            file=sys.stderr,
        )
        return 1

    deltas: dict[str, dict] = {}
    # Compute deltas per unique cell label (not per config name)
    unique_labels = {cell_label(refs[r]) for r in resolved}
    for label in unique_labels:
        cv_key = ("cv", label)
        ctrv_key = ("ctrv", label)
        if cv_key not in cell_metrics or ctrv_key not in cell_metrics:
            continue
        cv_m, ctrv_m = cell_metrics[cv_key], cell_metrics[ctrv_key]
        deltas[label] = {
            "mota": ctrv_m["mota"] - cv_m["mota"],
            "ids": ctrv_m["ids"] - cv_m["ids"],
            "amota": ctrv_m["amota"] - cv_m["amota"],
            "amotp": ctrv_m["amotp"] - cv_m["amotp"],
            "p99_ms": None
            if ctrv_m["p99_ms"] is None or cv_m["p99_ms"] is None
            else ctrv_m["p99_ms"] - cv_m["p99_ms"],
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
