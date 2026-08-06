"""Synthetic ingest end-to-end checks."""

import json
from pathlib import Path

from ingest.nuscenes_ingest import SYNTHETIC_SCENE_NAME, write_synthetic_scene
from ingest.schema import is_valid_detection


def test_synthetic_ingest_writes_valid_jsonl(tmp_path: Path):
    scene_dir = write_synthetic_scene(tmp_path, force=True, also_fixtures=False)
    assert scene_dir.name == SYNTHETIC_SCENE_NAME

    det_path = scene_dir / "detections.jsonl"
    gt_path = scene_dir / "gt.jsonl"
    meta_path = scene_dir / "scene_meta.json"
    assert det_path.is_file()
    assert gt_path.is_file()
    assert meta_path.is_file()

    det_lines = det_path.read_text(encoding="utf-8").strip().splitlines()
    gt_lines = gt_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(det_lines) == 20
    assert len(gt_lines) == 20

    first_det = json.loads(det_lines[0])
    assert first_det["frame"] == 0
    assert "t" in first_det
    assert isinstance(first_det["dets"], list)
    assert len(first_det["dets"]) == 2
    for d in first_det["dets"]:
        assert is_valid_detection(d)

    first_gt = json.loads(gt_lines[0])
    assert first_gt["frame"] == 0
    for d in first_gt["dets"]:
        assert is_valid_detection(d, require_gt_fields=True)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["source"] == "synthetic"
    assert meta["n_frames"] == 20


def test_synthetic_cli(tmp_path: Path, monkeypatch):
    from ingest.nuscenes_ingest import main

    out = tmp_path / "normalized"
    rc = main(["--synthetic", "--force", "--out-root", str(out)])
    assert rc == 0
    assert (out / SYNTHETIC_SCENE_NAME / "detections.jsonl").is_file()
