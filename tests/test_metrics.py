"""Unit tests for CLEAR MOT metrics (tiny inline fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.metrics import MotMetrics, evaluate_scene, load_jsonl, match_records_for_miner


def _gt_box(gt_id: str, x: float, y: float, *, cls: str = "car") -> dict:
    return {
        "cls": cls,
        "x": x,
        "y": y,
        "z": 0.0,
        "l": 4.5,
        "w": 1.8,
        "h": 1.6,
        "yaw": 0.0,
        "score": 1.0,
        "id": gt_id,
        "visibility": 4,
    }


def _track(track_id: int, x: float, y: float, *, state: str = "confirmed") -> dict:
    return {
        "id": track_id,
        "cls": "car",
        "x": x,
        "y": y,
        "yaw": 0.0,
        "vx": 0.0,
        "vy": 0.0,
        "state": state,
        "age": 1,
        "cov_trace": 0.0,
    }


def _gt_frame(frame: int, t: float, boxes: list[dict]) -> dict:
    return {"frame": frame, "t": t, "dets": boxes}


def _tr_frame(frame: int, t: float, tracks: list[dict]) -> dict:
    return {"frame": frame, "t": t, "tracks": tracks}


def test_perfect_match_mota_one():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 1.0, 0.0), _gt_box("b", 11.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0), _track(2, 10.0, 0.0)]),
        _tr_frame(1, 0.5, [_track(1, 1.0, 0.0), _track(2, 11.0, 0.0)]),
    ]
    metrics, frame_matches = evaluate_scene(gt, tracks)
    assert isinstance(metrics, MotMetrics)
    assert metrics.gt_count == 4
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.ids == 0
    assert metrics.frag == 0
    assert metrics.mota == 1.0
    assert metrics.motp == 0.0
    assert len(frame_matches) == 2
    assert len(match_records_for_miner(frame_matches)) == 4


def test_one_fn_decreases_mota():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0)]),  # misses b
    ]
    metrics, _ = evaluate_scene(gt, tracks)
    assert metrics.fn == 1
    assert metrics.fp == 0
    assert metrics.gt_count == 2
    assert metrics.mota == 1.0 - (1 + 0 + 0) / 2
    assert metrics.mota < 1.0


def test_id_switch_across_two_frames():
    # Frame 0: a→1, b→2; frame 1: positions swap association → a→2, b→1.
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0), _track(2, 10.0, 0.0)]),
        # Tracks jump to the other GT centers → identity switch.
        _tr_frame(1, 0.5, [_track(1, 10.0, 0.0), _track(2, 0.0, 0.0)]),
    ]
    metrics, frame_matches = evaluate_scene(gt, tracks)
    assert metrics.ids >= 1
    # Both GTs change partners → typically 2 IDS.
    assert metrics.ids == 2
    assert frame_matches[0].matches
    assert frame_matches[1].matches


def test_empty_tracks_all_fn():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 5.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 1.0, 0.0)]),
    ]
    tracks: list[dict] = [
        _tr_frame(0, 0.0, []),
        _tr_frame(1, 0.5, []),
    ]
    metrics, frame_matches = evaluate_scene(gt, tracks)
    assert metrics.fn == 3
    assert metrics.fp == 0
    assert metrics.gt_count == 3
    assert metrics.ids == 0
    assert metrics.mota == 1.0 - 3 / 3
    assert all(len(fm.matches) == 0 for fm in frame_matches)


def test_tentative_tracks_ignored_when_state_present():
    gt = [_gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0)])]
    tracks = [_tr_frame(0, 0.0, [_track(1, 0.0, 0.0, state="tentative")])]
    metrics, _ = evaluate_scene(gt, tracks)
    assert metrics.fn == 1
    assert metrics.fp == 0


def test_load_jsonl_roundtrip(tmp_path: Path):
    path = tmp_path / "gt.jsonl"
    rows = [_gt_frame(0, 0.0, [_gt_box("a", 1.0, 2.0)])]
    path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    loaded = load_jsonl(path)
    assert loaded == rows
