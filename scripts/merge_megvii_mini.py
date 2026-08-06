#!/usr/bin/env python3
"""Merge Megvii train + val detection dumps for nuScenes mini ingest.

Mini's 10 scenes straddle the official train/val split, so ingest needs the
union (see docs/decisions.md D6). Writes::

    data/raw/detections/megvii_mini_merged.json

Usage::

    python scripts/merge_megvii_mini.py
    python scripts/merge_megvii_mini.py \\
        --train data/raw/detections/megvii_train.json \\
        --val data/raw/detections/megvii_val.json \\
        --out data/raw/detections/megvii_mini_merged.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _results(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ValueError("detections JSON must be an object")
    if "results" in payload:
        results = payload["results"]
        if not isinstance(results, dict):
            raise ValueError("detections JSON 'results' must be an object")
        return dict(results)
    return dict(payload)


def _meta_blob(payload: Any) -> dict[str, Any]:
    """Prefer nuScenes ``meta``; fall back to Megvii ``meta_data`` if present."""
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("meta"), dict):
        return dict(payload["meta"])
    if isinstance(payload.get("meta_data"), dict):
        return dict(payload["meta_data"])
    return {}


def merge_megvii(train_path: Path, val_path: Path, out_path: Path) -> dict[str, int]:
    train = json.loads(train_path.read_text(encoding="utf-8"))
    val = json.loads(val_path.read_text(encoding="utf-8"))

    merged = _results(train)
    n_train = len(merged)
    val_results = _results(val)
    merged.update(val_results)

    meta = _meta_blob(train) or _meta_blob(val)
    meta = {
        **meta,
        "source": "megvii_train ∪ megvii_val",
        "note": "Merged for nuScenes v1.0-mini (scenes span train/val).",
    }

    # Keep both meta keys so either consumer style works.
    out_obj: dict[str, Any] = {
        "meta": meta,
        "meta_data": meta,
        "results": merged,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(out_obj, fh, separators=(",", ":"))
        fh.write("\n")

    return {
        "n_train_tokens": n_train,
        "n_val_tokens": len(val_results),
        "n_merged_tokens": len(merged),
        "bytes": out_path.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--train",
        type=Path,
        default=Path("data/raw/detections/megvii_train.json"),
    )
    p.add_argument(
        "--val",
        type=Path,
        default=Path("data/raw/detections/megvii_val.json"),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/raw/detections/megvii_mini_merged.json"),
    )
    args = p.parse_args(argv)

    for path in (args.train, args.val):
        if not path.is_file():
            print(f"missing detections file: {path}", file=sys.stderr)
            print(
                "Download first (see docs/data.md):\n"
                "  wget -O data/raw/detections/detection-megvii.zip "
                "https://www.nuscenes.org/data/detection-megvii.zip\n"
                "  unzip -d data/raw/detections data/raw/detections/detection-megvii.zip",
                file=sys.stderr,
            )
            return 1

    stats = merge_megvii(args.train, args.val, args.out)
    print(json.dumps({"out": str(args.out), **stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
