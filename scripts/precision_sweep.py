#!/usr/bin/env python3
"""Precision sweep (double vs float) + per-precision determinism audit.

For each of the four manifest reference configs ([reference] in
bench/ablation/manifest.toml: baseline, post001, post002, post003) and each
precision build (double, float), runs the tracker twice per scene into
--out/<precision>/<label>/run{1,2}/ (never into data/normalized/), audits that
run-1/run-2 per-scene track bytes are sha256-identical (assertion: any diff
prints the scene and exits 1), computes MOTA/IDS per scene via
eval.metrics.evaluate_scene, AMOTA/AMOTP per config via eval.amota.compute_amota
(over the 10 run-1 scenes), and a pooled nearest-rank p99 over all
ms_per_frame values of the run-2 timing files. Emits
bench/precision/sweep.json (metrics, float-double deltas, determinism,
provenance) and the generated bench/precision/SWEEP.md. Skip mode (nothing to
run, no --force) leaves existing outputs byte-untouched.

The manifest cell/knobs/label logic is imported from bench/ablation/summarize.py
(cell_label / materialize_cells / load_references) rather than duplicated.

Usage:
  python3 scripts/precision_sweep.py
  python3 scripts/precision_sweep.py --precisions double
  python3 scripts/precision_sweep.py --configs baseline post003
  python3 scripts/precision_sweep.py --force
"""

from __future__ import annotations

import argparse
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
DEFAULT_OUT = REPO_ROOT / "bench" / "precision" / "out"
SWEEP_JSON = REPO_ROOT / "bench" / "precision" / "sweep.json"
SWEEP_MD = REPO_ROOT / "bench" / "precision" / "SWEEP.md"
ABLATION_OUT = REPO_ROOT / "bench" / "ablation" / "out"
DEFAULT_BIN_DOUBLE = "core/build/trackbench_run"
DEFAULT_BIN_FLOAT = "core/build-float/trackbench_run"
SCHEMA = "trackbench/precision-sweep/v1"
CROSS_TOL = 1e-9  # tolerance for the double-vs-committed sanity cross-check


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


def run_cell(binary: str, precision: str, label: str, config: dict, out_root: Path, scenes: list[str], force: bool) -> bool:
    """Run both runs of one (precision, config) cell; return True if anything ran."""
    cell_dir = out_root / precision / label
    config_path = cell_dir / "config.json"
    ran = False
    for run_no in (1, 2):
        run_dir = cell_dir / f"run{run_no}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            tracks_out = run_dir / f"{scene}.jsonl"
            timing_out = run_dir / f"{scene}_timing.json"
            if not force and tracks_out.is_file() and timing_out.is_file():
                continue
            if not config_path.is_file():
                config_path.write_text(
                    json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            run_scene(binary, config_path, scene, tracks_out, timing_out)
            ran = True
    return ran


def audit_determinism(cell_dir: Path, scenes: list[str]) -> dict:
    """sha256 compare of per-scene run1/run2 track files; empty `differs` = pass."""
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


def committed_double(label: str) -> dict | None:
    """Committed bench/ablation cell values for the double cross-check, or None."""
    summary_path = ABLATION_OUT / label / "summary.json"
    amota_path = ABLATION_OUT / label / "amota.json"
    if not summary_path.is_file() or not amota_path.is_file():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    amota = json.loads(amota_path.read_text(encoding="utf-8"))
    return {
        "total_ids": int(summary["total_ids"]),
        "total_mota": float(summary["total_mota"]),
        "amota": float(amota["all"]["amota"]),
        "amotp": float(amota["all"]["amotp"]),
        "scenes": {
            name: {"mota": float(v["mota"]), "ids": int(v["ids"])}
            for name, v in summary["scenes"].items()
        },
    }


def cross_check_double(configs: dict, precisions: list[str]) -> list[str]:
    """Compare double-mode sweep values to committed ablation cell outputs.

    Returns a list of drift messages; a non-empty list means the sweep should
    STOP (the double build no longer reproduces the committed cell outputs).
    """
    problems: list[str] = []
    if "double" not in precisions:
        return problems
    for label, entries in configs.items():
        entry = next((e for e in entries if e["precision"] == "double"), None)
        if entry is None:
            continue
        committed = committed_double(label)
        if committed is None:
            problems.append(
                f"{label}: committed bench/ablation/out/{label} summary.json/amota.json missing — cannot cross-check"
            )
            continue
        diffs = []
        if entry["ids"] != committed["total_ids"]:
            diffs.append(f"ids {entry['ids']} vs committed {committed['total_ids']}")
        for key, committed_key, tol in (
            ("mota", "total_mota", CROSS_TOL),
            ("amota", "amota", CROSS_TOL),
            ("amotp", "amotp", CROSS_TOL),
        ):
            got, want = entry[key], committed[committed_key]
            if math.isnan(got) or math.isnan(want) or abs(got - want) > tol:
                diffs.append(f"{key} {got} vs committed {want}")
        scene_diffs = 0
        for scene, got in entry["scenes"].items():
            want = committed["scenes"].get(scene)
            if want is None:
                scene_diffs += 1
                continue
            if got["ids"] != want["ids"] or abs(got["mota"] - want["mota"]) > CROSS_TOL:
                scene_diffs += 1
        if scene_diffs:
            diffs.append(f"{scene_diffs} per-scene mota/ids mismatches")
        if diffs:
            problems.append(f"{label} (double): real drift — " + "; ".join(diffs))
    return problems


def fmt_val(value, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def fmt_signed(value, digits: int) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}"


def render_sweep_json(configs: dict, deltas: dict, args) -> dict:
    return {
        "schema": SCHEMA,
        "configs": configs,
        "deltas": deltas,
        "provenance": {
            "commit": git_head(),
            "bin_double": args.bin_double,
            "bin_float": args.bin_float,
            "python": platform.python_version(),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    }


def render_sweep_md(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# Precision Sweep — double vs float")
    lines.append("")
    lines.append(
        "Machine-generated by `scripts/precision_sweep.py` from the four "
        "`[reference]` cells of `bench/ablation/manifest.toml`. Do not hand-edit; "
        "regenerate with `python3 scripts/precision_sweep.py`."
    )
    lines.append("")
    lines.append("## Per config+precision metrics")
    lines.append("")
    lines.append(
        "| config | reference | precision | MOTA | IDS | AMOTA | AMOTP | p99 ms | determinism |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    configs = payload["configs"]
    for label in sorted(configs):
        entries = {e["precision"]: e for e in configs[label]}
        for prec in ("double", "float"):
            row = entries.get(prec)
            if row is None:
                continue
            lines.append(
                f"| {label} | {row['reference']} | {row['precision']} | "
                f"{fmt_val(row['mota'], 6)} | {row['ids']} | "
                f"{fmt_val(row['amota'], 6)} | {fmt_val(row['amotp'], 6)} | "
                f"{fmt_val(row['p99_ms'], 4)} | "
                f"{'PASS' if row['determinism']['pass'] else 'FAIL'} |"
            )
    lines.append("")
    lines.append("## float − double deltas")
    lines.append("")
    lines.append("| config | reference | ΔMOTA | ΔIDS | ΔAMOTA | ΔAMOTP | Δp99 ms |")
    lines.append("|---|---|---|---|---|---|---|")
    for label in sorted(payload["deltas"]):
        d = payload["deltas"][label]
        reference = next(
            c["reference"] for c in configs[label] if c["precision"] == "float"
        )
        lines.append(
            f"| {label} | {reference} | {fmt_signed(d['mota'], 6)} | "
            f"{d['ids']:+d} | {fmt_signed(d['amota'], 6)} | "
            f"{fmt_signed(d['amotp'], 6)} | {fmt_signed(d['p99_ms'], 4)} |"
        )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- commit: `{payload['provenance']['commit']}`")
    lines.append(f"- tracker binary (double): `{payload['provenance']['bin_double']}`")
    lines.append(f"- tracker binary (float): `{payload['provenance']['bin_float']}`")
    lines.append(f"- python: {payload['provenance']['python']}")
    lines.append(f"- ts: {payload['provenance']['ts']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 scripts/precision_sweep.py",
        description="Double vs float precision sweep with per-precision determinism audit.",
    )
    p.add_argument(
        "--precisions",
        nargs="+",
        choices=["double", "float"],
        default=["double", "float"],
        help="precision builds to sweep (default: double float)",
    )
    p.add_argument(
        "--configs",
        action="append",
        metavar="REF",
        help="manifest reference name to sweep (repeatable; default: all four)",
    )
    p.add_argument(
        "--bin-double",
        default=DEFAULT_BIN_DOUBLE,
        help="double tracker binary (default: %(default)s)",
    )
    p.add_argument(
        "--bin-float",
        default=DEFAULT_BIN_FLOAT,
        help="float tracker binary (default: %(default)s)",
    )
    p.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="sweep output root (default: %(default)s)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="rerun every (precision, config) cell even if outputs exist",
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
    aliases = dict(manifest.get("meta", {}).get("aliases") or {})

    selected = list(args.configs or [])
    resolved_refs = []
    for name in selected:
        if name in refs:
            resolved_refs.append(name)
        elif name in aliases and aliases[name] in refs:
            resolved_refs.append(aliases[name])
        else:
            raise SystemExit(
                f"error: unknown reference {name!r}; known: {', '.join(refs)}"
            )
    if not resolved_refs:
        resolved_refs = list(refs)
    resolved_refs = list(dict.fromkeys(resolved_refs))

    for prec in args.precisions:
        binary = args.bin_double if prec == "double" else args.bin_float
        bin_path = Path(binary)
        if not bin_path.is_absolute():
            bin_path = REPO_ROOT / bin_path
        if not bin_path.is_file():
            raise SystemExit(
                f"error: tracker binary missing for {prec}: {bin_path} "
                f"(build with `make {'core' if prec == 'double' else 'core-float'}`)"
            )
    binaries = {
        "double": str(Path(args.bin_double).resolve()),
        "float": str(Path(args.bin_float).resolve()),
    }

    scenes = scene_ids()
    if len(scenes) != 10:
        print(f"warning: expected 10 normalized scenes, found {len(scenes)}", file=sys.stderr)

    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root

    configs: dict[str, list] = {}
    failures: list[str] = []
    ran_any = False

    for prec in args.precisions:
        binary = binaries[prec]
        for ref in resolved_refs:
            label = cell_label(refs[ref])
            config = cells_by_label[label]["config"]
            cell_dir = out_root / prec / label
            ran = run_cell(binary, prec, label, config, out_root, scenes, args.force)
            ran_any = ran_any or ran

            det = audit_determinism(cell_dir, scenes)
            if not det["pass"]:
                failures.append(f"{prec}/{label}: determinism FAIL ({', '.join(det['differs'])})")
                print(
                    f"determinism {prec}/{label}: FAIL — differing scene(s): "
                    + ", ".join(det["differs"]),
                    file=sys.stderr,
                )
            else:
                print(
                    f"determinism {prec}/{label}: PASS "
                    f"(run1/run2 sha256-identical for {det['scene_bytes_compared']} scenes)"
                )

            metrics = compute_metrics(cell_dir, scenes)
            entry = {
                "label": label,
                "reference": ref,
                "precision": prec,
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
            configs.setdefault(label, []).append(entry)

    if failures:
        print("FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    problems = cross_check_double(configs, args.precisions)
    if problems:
        print("DOUBLE-VS-COMMITTED DRIFT:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        print(
            "STOP: the double sweep no longer matches the committed cell outputs; "
            "investigate before proceeding.",
            file=sys.stderr,
        )
        return 1

    deltas: dict[str, dict] = {}
    for label, entries in configs.items():
        by_prec = {e["precision"]: e for e in entries}
        dbl, flt = by_prec.get("double"), by_prec.get("float")
        if dbl is None or flt is None:
            continue
        deltas[label] = {
            "mota": flt["mota"] - dbl["mota"],
            "ids": flt["ids"] - dbl["ids"],
            "amota": flt["amota"] - dbl["amota"],
            "amotp": flt["amotp"] - dbl["amotp"],
            "p99_ms": None
            if flt["p99_ms"] is None or dbl["p99_ms"] is None
            else flt["p99_ms"] - dbl["p99_ms"],
        }

    payload = render_sweep_json(configs, deltas, args)

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
