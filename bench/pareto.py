#!/usr/bin/env python3
"""Generate the Phase 5 accuracy-vs-latency Pareto chart (bench/ablation/pareto.*).

Materializes the 24-cell ablation grid from bench/ablation/manifest.toml (same
cross product as bench/ablation/summarize.py, no hardcoded labels) and, for
each cell, reads its summary.json (MOTA/IDS), amota.json (AMOTA/AMOTP) and the
10 scene-*_timing.json ms_per_frame arrays (pooled nearest-rank p99 latency).
Emits a deterministic SVG scatter (x = p99 per-frame latency ms, y = selected
accuracy metric) and a markdown table sorted by AMOTA descending. Reference
cells (manifest [reference] keys) get a distinct fill and their manifest
names; the best cell for the selected metric (lowest IDS / highest AMOTA/MOTA)
is ringed. Every number traces to a cell output file; outputs are byte-identical
for identical inputs. Missing amota.json for any cell is a hard error (no chart
with gaps).

Usage:
  python3 bench/pareto.py [--metric amota|mota|ids]
                          [--svg PATH] [--md PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
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
DEFAULT_SVG = REPO_ROOT / "bench" / "ablation" / "pareto.svg"
DEFAULT_MD = REPO_ROOT / "bench" / "ablation" / "pareto.md"
KNOBS = ["gate_m", "vel_cost_weight", "iou_weight", "min_birth_score"]
KNOB_SHORT = {
    "gate_m": "gate",
    "vel_cost_weight": "vel",
    "iou_weight": "iou",
    "min_birth_score": "birth",
}
METRIC_META = {
    "amota": {"title": "AMOTA", "y_title": "AMOTA (nuScenes)"},
    "mota": {"title": "MOTA", "y_title": "total MOTA"},
    "ids": {"title": "IDS", "y_title": "total ID switches"},
}


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
    expected_keys = set(json.loads((REPO_ROOT / "core" / "config" / "default.json").read_text(encoding="utf-8")))
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


def load_references(manifest: dict) -> dict:
    refs = dict(manifest["reference"])
    if isinstance(refs.get("alias"), dict):
        refs.pop("alias")
    return refs


def load_summary(label: str) -> dict:
    path = OUT_ROOT / label / "summary.json"
    if not path.is_file():
        raise SystemExit(
            f"error: missing summary.json for cell {label!r}: expected {path}\n"
            f"rerun `python scripts/ablate.py` to materialize the full 24-cell grid"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_amota(label: str) -> dict:
    path = OUT_ROOT / label / "amota.json"
    if not path.is_file():
        raise SystemExit(
            f"error: missing amota.json for cell {label!r}: expected {path}\n"
            f"rerun `python scripts/ablate_amota.py` to compute per-cell AMOTA"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"amota": data["all"]["amota"], "amotp": data["all"]["amotp"]}


def load_timing_p99(label: str) -> float:
    timings = sorted(OUT_ROOT.glob(f"{label}/scene-*_timing.json"))
    if len(timings) != 10:
        raise SystemExit(
            f"error: cell {label!r} has {len(timings)} scene-*_timing.json files, expected 10"
        )
    values = []
    for path in timings:
        values.extend(json.loads(path.read_text(encoding="utf-8"))["ms_per_frame"])
    if not values:
        raise SystemExit(f"error: no ms_per_frame values in timing files for cell {label!r}")
    ordered = sorted(values)
    return ordered[int(round(0.99 * (len(ordered) - 1)))]


def git_provenance() -> tuple[str, str]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        date = subprocess.run(
            ["git", "log", "-1", "--format=%cs"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"error: git provenance unavailable: {e}")
    return sha, date


def nice_step(span: float) -> float:
    if span <= 0.0:
        span = 1e-9
    mag = 10 ** math.floor(math.log10(span))
    norm = span / mag
    if norm <= 1:
        return mag
    if norm <= 2:
        return 2 * mag
    if norm <= 5:
        return 5 * mag
    return 10 * mag


def axis_range(values: list[float], target_ticks: int = 7) -> tuple[float, float, float]:
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * 0.05, 1e-12)
    step = nice_step((hi - lo) / max(target_ticks - 1, 1))
    alo = math.floor((lo - pad) / step) * step
    ahi = math.ceil((hi + pad) / step) * step
    return round(alo, 10), round(ahi, 10), step


def tick_decimals(step: float) -> int:
    s = f"{step:g}"
    if "e" in s:
        return max(0, -int(s.split("e")[1]))
    if "." not in s:
        return 0
    return len(s.split(".")[1])


def fmt_axis(v: float, ndp: int) -> str:
    return f"{round(v, ndp):.{ndp}f}"


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(cells: list[dict], rows: dict, metric: str, sha: str, date: str) -> str:
    meta = METRIC_META[metric]
    xvals = [rows[label]["p99_ms"] for label in rows]
    yvals = [rows[label][metric] for label in rows]
    xlo, xhi, xstep = axis_range(xvals)
    ylo, yhi, ystep = axis_range(yvals)

    x0, x1, y0, y1 = 90.0, 860.0, 80.0, 460.0
    xndp, yndp = tick_decimals(xstep), tick_decimals(ystep)

    def xpix(v: float) -> float:
        return x0 + (v - xlo) / (xhi - xlo) * (x1 - x0)

    def ypix(v: float) -> float:
        return y1 - (v - ylo) / (yhi - ylo) * (y1 - y0)

    sign = 1 if metric == "ids" else -1
    best_label = min(rows, key=lambda label: (sign * rows[label][metric], label))

    refs = {label: rows[label]["ref"] for label in rows if rows[label]["ref"]}

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="540" '
        'viewBox="0 0 900 540" font-family="Helvetica, Arial, sans-serif">',
        '<rect width="900" height="540" fill="#ffffff"/>',
        f'<text x="450" y="36" font-size="20" font-weight="bold" text-anchor="middle" '
        f'fill="#0f172a">TrackBench ablation — {meta["title"]} vs p99 per-frame latency '
        f'({len(rows)} cells)</text>',
    ]

    for i in range(round((xhi - xlo) / xstep) + 1):
        v = xlo + i * xstep
        px = xpix(v)
        parts.append(f'<line x1="{px:.2f}" y1="{y0}" x2="{px:.2f}" y2="{y1}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{px:.2f}" y="{y1 + 16}" font-size="12" text-anchor="middle" fill="#334155">{fmt_axis(v, xndp)}</text>')
    for i in range(round((yhi - ylo) / ystep) + 1):
        v = ylo + i * ystep
        py = ypix(v)
        parts.append(f'<line x1="{x0}" y1="{py:.2f}" x2="{x1}" y2="{py:.2f}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{x0 - 8}" y="{py:.2f}" font-size="12" text-anchor="end" dominant-baseline="middle" fill="#334155">{fmt_axis(v, yndp)}</text>')

    parts.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="#0f172a" stroke-width="1.5"/>')
    parts.append(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#0f172a" stroke-width="1.5"/>')

    for label in sorted(rows):
        r = rows[label]
        if label in refs:
            parts.append(
                f'<circle cx="{xpix(r["p99_ms"]):.2f}" cy="{ypix(r[metric]):.2f}" '
                f'r="5" fill="#e11d48"/>'
            )
        else:
            parts.append(
                f'<circle cx="{xpix(r["p99_ms"]):.2f}" cy="{ypix(r[metric]):.2f}" '
                f'r="4.5" fill="#64748b"/>'
            )

    if best_label:
        b = rows[best_label]
        parts.append(
            f'<circle cx="{xpix(b["p99_ms"]):.2f}" cy="{ypix(b[metric]):.2f}" '
            f'r="9" fill="none" stroke="#0f172a" stroke-width="1.6"/>'
        )

    label_h = 12.0
    label_w = 6.5
    placed_boxes: list[tuple[float, float, float, float]] = []
    label_placements: list[tuple[str, float, float]] = []
    for label in sorted(refs):
        r = rows[label]
        px, py = xpix(r["p99_ms"]), ypix(r[metric])
        name = refs[label]
        w = len(name) * label_w
        candidates = [
            ("start", px + 8.0, py - 8.0),
            ("end", px - 8.0, py - 8.0),
            ("start", px + 8.0, py + 15.0),
            ("end", px - 8.0, py + 15.0),
            ("start", px + 8.0, py + 1.0),
            ("end", px - 8.0, py + 1.0),
        ]
        chosen = None
        for anchor, lx, ly in candidates:
            if anchor == "start":
                box = (lx, ly - label_h, lx + w, ly)
                if lx + w > x1 or ly - label_h < y0:
                    continue
            else:
                box = (lx - w, ly - label_h, lx, ly)
                if lx - w < x0 or ly - label_h < y0:
                    continue
            if any(
                not (box[2] <= other[0] or box[0] >= other[2]
                     or box[3] <= other[1] or box[1] >= other[3])
                for other in placed_boxes
            ):
                continue
            placed_boxes.append(box)
            chosen = (anchor, lx, ly)
            break
        if chosen is None:
            chosen = ("start", px + 8.0, py - 8.0)
        label_placements.append(chosen)

    for (anchor, lx, ly), label in zip(label_placements, sorted(refs)):
        parts.append(
            f'<text x="{lx:.2f}" y="{ly:.2f}" font-size="12" '
            f'text-anchor="{anchor}" fill="#e11d48">{esc(refs[label])}</text>'
        )

    parts.append(
        f'<text x="475" y="498" font-size="13" text-anchor="middle" fill="#0f172a">'
        f'p99 per-frame latency (ms)</text>'
    )
    parts.append(
        f'<text x="28" y="270" font-size="13" text-anchor="middle" fill="#0f172a" '
        f'transform="rotate(-90 28 270)">{esc(meta["y_title"])}</text>'
    )
    parts.append(
        '<text x="90" y="510" font-size="11" fill="#64748b">data: '
        'bench/ablation/out/&lt;label&gt;/{summary,amota,scene-*_timing}.json '
        f'({len(rows)} cells)</text>'
    )
    parts.append(
        f'<text x="90" y="524" font-size="11" fill="#64748b">gen: python3 bench/pareto.py '
        f'--metric {metric} | commit {sha} | {date}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def md_table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def build_md(rows: dict, sha: str, date: str, n: int) -> str:
    lines = [
        "# TrackBench ablation — accuracy vs latency Pareto",
        "",
        "Machine-generated by `python3 bench/pareto.py` from `bench/ablation/manifest.toml` "
        "and the per-cell cell outputs under `bench/ablation/out/<label>/` "
        "(`summary.json`, `amota.json`, `scene-*_timing.json`). Do not hand-edit; "
        "regenerate with `python3 bench/pareto.py`.",
        "",
        "## What was measured",
        "",
        f"One row per cell ({n} cells = full factorial over `gate_m` × `vel_cost_weight` × "
        "`iou_weight` × `min_birth_score`, everything else fixed at manifest `[defaults]`).",
        "",
        "- **MOTA / IDS** — CLEAR metrics from `summary.json` (`total_mota`, `total_ids`).",
        "- **AMOTA / AMOTP** — nuScenes recall-curve MOTA/MOTP pooled over all classes "
        "from `amota.json` (`all.amota`, `all.amotp`).",
        "- **p99_ms** — nearest-rank 99th percentile of per-frame tracking latency pooled "
        "over all frames of the cell's 10 `scene-*_timing.json` files.",
        "",
        "Sorted by AMOTA descending; the `reference` column marks manifest reference cells.",
        "",
    ]
    headers = ["label"] + [KNOB_SHORT[k] for k in KNOBS] + \
        ["MOTA", "IDS", "AMOTA", "AMOTP", "p99_ms", "reference"]
    table_rows = []
    for label in sorted(rows, key=lambda l: (-rows[l]["amota"], l)):
        r = rows[label]
        table_rows.append(
            [label] + [str(float(r["knobs"][k])) for k in KNOBS] +
            [f"{r['mota']:.4f}", r["ids"], f"{r['amota']:.4f}", f"{r['amotp']:.4f}",
             f"{r['p99_ms']:.4f}", r["ref"] or "—"]
        )
    lines.extend(md_table(headers, table_rows))
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append("- Data source: `bench/ablation/out/<label>/{summary,amota,scene-*_timing}.json`")
    lines.append("- Generation: `python3 bench/pareto.py`")
    lines.append(f"- Commit: `{sha}`")
    lines.append(f"- Date: {date}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python3 bench/pareto.py",
        description="Generate the deterministic accuracy-vs-latency Pareto chart "
                    "(SVG scatter + markdown table) from manifest.toml and per-cell "
                    "cell outputs.",
    )
    p.add_argument(
        "--metric", choices=sorted(METRIC_META), default="amota",
        help="y-axis accuracy metric for the scatter (default: %(default)s)",
    )
    p.add_argument(
        "--svg", metavar="PATH", default=str(DEFAULT_SVG),
        help="write SVG scatter to PATH (default: %(default)s)",
    )
    p.add_argument(
        "--md", metavar="PATH", default=str(DEFAULT_MD),
        help="write markdown table to PATH (default: %(default)s)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with open(DEFAULT_MANIFEST, "rb") as f:
            manifest = tomllib.load(f)
    except FileNotFoundError:
        print(f"error: manifest not found: {DEFAULT_MANIFEST}", file=sys.stderr)
        return 1
    except tomllib.TOMLDecodeError as e:
        print(f"error: {DEFAULT_MANIFEST}: {e}", file=sys.stderr)
        return 1

    cells = materialize_cells(manifest)
    cells_by_label = {c["label"]: c for c in cells}
    if len(cells_by_label) != 24:
        print(f"error: expected 24 unique cells, got {len(cells_by_label)}", file=sys.stderr)
        return 1

    refs = load_references(manifest)
    for name, knobs in refs.items():
        if cell_label(knobs) not in cells_by_label:
            print(
                f"error: reference {name!r} ({cell_label(knobs)}) is not "
                "materialized in the 24-cell grid",
                file=sys.stderr,
            )
            return 1

    rows = {}
    for label in sorted(cells_by_label):
        summary = load_summary(label)
        amota = load_amota(label)
        rows[label] = {
            "knobs": cells_by_label[label]["knobs"],
            "mota": summary["total_mota"],
            "ids": summary["total_ids"],
            "amota": amota["amota"],
            "amotp": amota["amotp"],
            "p99_ms": load_timing_p99(label),
            "ref": "",
        }
    for name, knobs in refs.items():
        rows[cell_label(knobs)]["ref"] = name

    sha, date = git_provenance()

    svg_path = Path(args.svg)
    if not svg_path.is_absolute():
        svg_path = REPO_ROOT / svg_path
    md_path = Path(args.md)
    if not md_path.is_absolute():
        md_path = REPO_ROOT / md_path

    svg = build_svg(cells, rows, args.metric, sha, date)
    md = build_md(rows, sha, date, len(rows))
    svg_path.write_text(svg, encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    print(f"wrote {svg_path}", file=sys.stderr)
    print(f"wrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
