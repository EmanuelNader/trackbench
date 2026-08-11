#!/usr/bin/env python3
"""Summarize per-frame stage timings CSV (trackbench_run --timing-csv).

Discards the first --warmup frames of each scene as warmup, then emits a
markdown table with p50/p95/p99/max per stage (integer nanoseconds, nearest
rank). Stdlib only; no numpy dependency.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Producer contract: must byte-match the CSV header written by
# core/src/main.cpp (trackbench_run --timing-csv). Keep in sync if the
# producer changes its column set or ordering.
EXPECTED_HEADER = (
    "frame,scene_id,n_active,n_dets,dt_ns,predict_ns,"
    "build_active_ns,cost_matrix_construct_ns,association_solve_ns,"
    "update_ns,birth_ns,coast_kill_ns,compact_ns,sort_emit_ns,total_ns"
)

STAGE_ORDER = [
    "DT",
    "PREDICT",
    "BUILD_ACTIVE",
    "COST_MATRIX_CONSTRUCT",
    "ASSOCIATION_SOLVE",
    "UPDATE",
    "BIRTH",
    "COAST_KILL",
    "COMPACT",
    "SORT_EMIT",
    "TOTAL",
]

STAGE_COLUMNS = [
    "dt_ns",
    "predict_ns",
    "build_active_ns",
    "cost_matrix_construct_ns",
    "association_solve_ns",
    "update_ns",
    "birth_ns",
    "coast_kill_ns",
    "compact_ns",
    "sort_emit_ns",
    "total_ns",
]


def percentile_ns(sorted_vals: list[int], p: int) -> int:
    """Nearest-rank percentile on ascending integer ns values.

    p50 = sorted[N/2], p95 = sorted[ceil(0.95*N)-1], p99 = sorted[ceil(0.99*N)-1]
    (1-based rank clamped to last), max = sorted[-1].
    """
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("no samples for percentile")
    if p == 50:
        return sorted_vals[n // 2]
    rank = (p * n + 99) // 100
    return sorted_vals[min(rank - 1, n - 1)]


def read_rows(path: Path) -> tuple[str, list[list[str]]]:
    """Return (header, data rows). Raises ValueError on bad CSV."""
    text = path.read_text(encoding="utf-8")
    lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip() != ""]
    if not lines:
        raise ValueError(f"{path}: empty CSV file")
    header = lines[0]
    if header != EXPECTED_HEADER:
        raise ValueError(
            f"{path}: header mismatch\n"
            f"  expected: {EXPECTED_HEADER}\n"
            f"  got:      {header}"
        )
    columns = header.split(",")
    parse_cols = [
        ("frame", columns.index("frame")),
        ("scene_id", columns.index("scene_id")),
        *[(name, columns.index(name)) for name in STAGE_COLUMNS],
    ]
    rows = []
    for line_no, ln in enumerate(lines[1:], start=2):
        fields = ln.split(",")
        if len(fields) != len(columns):
            raise ValueError(
                f"{path}:{line_no}: expected {len(columns)} columns, got "
                f"{len(fields)}: {ln}"
            )
        for label, idx in parse_cols:
            try:
                int(fields[idx])
            except ValueError:
                raise ValueError(
                    f"{path}:{line_no}: non-integer {label} "
                    f"({fields[idx]!r}): {ln}"
                )
        rows.append(fields)
    return header, rows


def build_report(
    rows: list[list[str]], header: str, warmup: int
) -> tuple[str, dict[str, int]]:
    """Group by scene_id, drop warmup frames per scene, compute percentiles.

    Returns (markdown text, stats dict with scenes/sampled/warmup).
    """
    columns = header.split(",")
    stage_col_idx = {name: i for i, name in enumerate(columns)}

    by_scene: dict[int, list[list[str]]] = {}
    for row in rows:
        scene_id = int(row[columns.index("scene_id")])
        by_scene.setdefault(scene_id, []).append(row)

    # The CSV producer currently writes scene_id = input frame number as a
    # placeholder (one distinct scene_id per frame). With no repeated scene_id
    # there is no real scene grouping, so treat the whole file as one scene.
    if len(by_scene) > 1 and all(len(v) == 1 for v in by_scene.values()):
        by_scene = {0: rows}

    discarded_note: list[str] = []
    sampled: list[list[str]] = []
    for scene_id in sorted(by_scene):
        scene_rows = sorted(
            by_scene[scene_id],
            key=lambda r: int(r[columns.index("frame")]),
        )
        if len(scene_rows) <= warmup:
            discarded_note.append(
                f"scene {scene_id}: {len(scene_rows)} rows <= warmup "
                f"({warmup}), contributed no samples"
            )
            continue
        sampled.extend(scene_rows[warmup:])

    if not sampled:
        raise ValueError(
            "no scene has more than warmup rows; nothing to summarize "
            "(every scene had fewer than warmup+1 frames)"
        )

    per_stage: dict[str, list[int]] = {}
    for row in sampled:
        for stage, col in zip(STAGE_ORDER, STAGE_COLUMNS):
            per_stage.setdefault(stage, []).append(int(row[stage_col_idx[col]]))
    for stage in STAGE_ORDER:
        per_stage[stage].sort()

    lines = [f"Warmup frames discarded: {warmup} per scene"]
    if discarded_note:
        lines.extend(discarded_note)
    lines.append(
        f"Scenes: {len(by_scene)}, frames sampled: {len(sampled)}"
    )
    lines.append("")
    lines.append("| Stage | p50_ns | p95_ns | p99_ns | max_ns |")
    lines.append("|-------|--------|--------|--------|--------|")
    for stage in STAGE_ORDER:
        vals = per_stage[stage]
        lines.append(
            f"| {stage} | {percentile_ns(vals, 50)} | "
            f"{percentile_ns(vals, 95)} | {percentile_ns(vals, 99)} | "
            f"{percentile_ns(vals, 100)} |"
        )
    stats = {"scenes": len(by_scene), "sampled": len(sampled), "warmup": warmup}
    return "\n".join(lines) + "\n", stats


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Summarize per-frame stage timings CSV (--timing-csv output)"
    )
    ap.add_argument("csv", metavar="CSV", help="path to timing CSV")
    ap.add_argument(
        "--out",
        metavar="PATH",
        help="write markdown table to PATH instead of stdout",
    )
    ap.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="frames to discard per scene as warmup (default: 5)",
    )
    args = ap.parse_args()

    if args.warmup < 0:
        print("error: --warmup must be >= 0", file=sys.stderr)
        return 1

    try:
        header, rows = read_rows(Path(args.csv))
        report, _ = build_report(rows, header, args.warmup)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
