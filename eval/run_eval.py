"""CLI entry for offline evaluation (stub until M2)."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.run_eval",
        description="Run TrackBench tracking evaluation (not implemented until M2).",
    )
    p.add_argument(
        "--scene-dir",
        default=None,
        help="normalized scene directory containing gt.jsonl / tracks.jsonl",
    )
    p.add_argument(
        "--out",
        default=None,
        help="optional path for metrics JSON",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    _ = build_parser().parse_args(argv)
    print("not implemented until M2", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
