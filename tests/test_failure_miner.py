"""Tiny synthetic match sequences for failure mining."""

from __future__ import annotations

from eval.failure_miner import (
    KIND_GHOST_TRACK,
    KIND_ID_SWITCH,
    KIND_LATE_INIT,
    KIND_TRACK_DROP,
    mine_failures,
    range_bin,
)
from eval.metrics import evaluate_scene


def _gt_box(
    gt_id: str,
    x: float,
    y: float,
    *,
    cls: str = "car",
    visibility: int = 4,
) -> dict:
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
        "visibility": visibility,
    }


def _track(
    track_id: int,
    x: float,
    y: float,
    *,
    state: str = "confirmed",
    cls: str = "car",
) -> dict:
    return {
        "id": track_id,
        "cls": cls,
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


def test_range_bin_edges():
    assert range_bin(0.0) == "near"
    assert range_bin(14.9) == "near"
    assert range_bin(15.0) == "mid"
    assert range_bin(30.0) == "mid"
    assert range_bin(30.1) == "far"


def test_id_switch_emitted():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0), _track(2, 10.0, 0.0)]),
        _tr_frame(1, 0.5, [_track(1, 10.0, 0.0), _track(2, 0.0, 0.0)]),
    ]
    _, matches = evaluate_scene(gt, tracks)
    events = mine_failures(
        gt, tracks, matches, scene_id="s1", scene_meta={"weather": "clear", "timeOfDay": "day"}
    )
    switches = [e for e in events if e["kind"] == KIND_ID_SWITCH]
    assert len(switches) >= 1
    e0 = switches[0]
    assert e0["scene_id"] == "s1"
    assert e0["frame"] == 1
    assert e0["gt_id"] in {"a", "b"}
    assert e0["track_id"] is not None
    assert 0.0 <= e0["severity"] <= 1.0
    assert e0["features"]["weather"] == "clear"
    assert e0["features"]["time_of_day"] == "day"
    assert e0["features"]["range_bin"] in {"near", "mid", "far"}
    assert e0["features"]["ego_speed"] == 0.0
    assert e0["features"]["prev_track_id"] != e0["features"]["new_track_id"]
    assert e0["features"]["new_track_id"] == e0["track_id"]


def test_late_init_after_three_unmatched_frames():
    # GT present frames 0–3 unmatched, matched at frame 3 → LATE_INIT.
    # Actually: unmatched 0,1,2 then match at 3.
    gt = [
        _gt_frame(0, 0.0, [_gt_box("ped-1", 40.0, 0.0, cls="pedestrian", visibility=1)]),
        _gt_frame(1, 0.5, [_gt_box("ped-1", 40.0, 0.0, cls="pedestrian", visibility=1)]),
        _gt_frame(2, 1.0, [_gt_box("ped-1", 40.0, 0.0, cls="pedestrian", visibility=1)]),
        _gt_frame(3, 1.5, [_gt_box("ped-1", 40.0, 0.0, cls="pedestrian", visibility=1)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, []),
        _tr_frame(1, 0.5, []),
        _tr_frame(2, 1.0, []),
        _tr_frame(3, 1.5, [_track(9, 40.0, 0.0, cls="pedestrian")]),
    ]
    events = mine_failures(gt, tracks, scene_id="late")
    late = [e for e in events if e["kind"] == KIND_LATE_INIT]
    assert len(late) == 1
    assert late[0]["gt_id"] == "ped-1"
    assert late[0]["track_id"] == 9
    assert late[0]["frame"] == 3
    assert late[0]["features"]["range_bin"] == "far"
    assert late[0]["features"]["duration_frames"] >= 3


def test_ghost_track_three_unmatched_frames():
    # Confirmed track with no GT for frames 0–2 → GHOST at frame 2.
    gt = [
        _gt_frame(0, 0.0, []),
        _gt_frame(1, 0.5, []),
        _gt_frame(2, 1.0, []),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(7, 5.0, 0.0)]),
        _tr_frame(1, 0.5, [_track(7, 5.0, 0.0)]),
        _tr_frame(2, 1.0, [_track(7, 5.0, 0.0)]),
    ]
    events = mine_failures(gt, tracks, scene_id="ghost")
    ghosts = [e for e in events if e["kind"] == KIND_GHOST_TRACK]
    assert len(ghosts) == 1
    assert ghosts[0]["track_id"] == 7
    assert ghosts[0]["gt_id"] is None
    assert ghosts[0]["frame"] == 2
    assert ghosts[0]["features"]["duration_frames"] >= 3


def test_track_drop_gap_of_two_then_rematch():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 0.0, 0.0)]),
        _gt_frame(2, 1.0, [_gt_box("a", 0.0, 0.0)]),
        _gt_frame(3, 1.5, [_gt_box("a", 0.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0)]),
        _tr_frame(1, 0.5, []),  # drop
        _tr_frame(2, 1.0, []),  # drop
        _tr_frame(3, 1.5, [_track(1, 0.0, 0.0)]),  # rematch
    ]
    events = mine_failures(gt, tracks, scene_id="drop")
    drops = [e for e in events if e["kind"] == KIND_TRACK_DROP]
    assert len(drops) == 1
    assert drops[0]["gt_id"] == "a"
    assert drops[0]["frame"] == 3
    assert drops[0]["features"]["duration_frames"] >= 2
