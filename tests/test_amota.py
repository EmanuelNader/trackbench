"""Unit tests for eval/amota.py (nuScenes AMOTA/AMOTP, tiny hand-built fixtures).

No C++ dependency: every scene is built inline with the helpers below.
"""

from __future__ import annotations

import math

import pytest

from eval import amota
from eval.amota import compute_amota
from eval.metrics import evaluate_scene


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


def _track(track_id: int, x: float, y: float, score: float, *, cls: str = "car") -> dict:
    return {
        "id": track_id,
        "cls": cls,
        "x": x,
        "y": y,
        "yaw": 0.0,
        "vx": 0.0,
        "vy": 0.0,
        "state": "confirmed",
        "age": 1,
        "cov_trace": 0.0,
        "score": score,
    }


def _gt_frame(frame: int, t: float, boxes: list[dict]) -> dict:
    return {"frame": frame, "t": t, "dets": boxes}


def _tr_frame(frame: int, t: float, tracks: list[dict]) -> dict:
    return {"frame": frame, "t": t, "tracks": tracks}


def _nanaware_equal(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_nanaware_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_nanaware_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    return a == b


def test_perfect_tracker_amota_one():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 1.0, 0.0), _gt_box("b", 11.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0, 1.0), _track(2, 10.0, 0.0, 1.0)]),
        _tr_frame(1, 0.5, [_track(1, 1.0, 0.0, 1.0), _track(2, 11.0, 0.0, 1.0)]),
    ]
    res = compute_amota([(gt, tracks)])
    car = res["per_class"]["car"]
    assert car["amota"] == 1.0
    assert car["amotp"] == 0.0
    assert res["all"]["amota"] == 1.0
    assert res["all"]["amotp"] == 0.0


def test_score_hiding_scores_lower_than_full_emission():
    # One persistent GT box (a) over 2 frames; one persistent FP track (99).
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 1.0, 0.0)]),
    ]
    # Full emission: every box keeps a high score, so no threshold hides GT.
    full = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0, 1.0), _track(99, 5.0, 5.0, 1.0)]),
        _tr_frame(1, 0.5, [_track(1, 1.0, 0.0, 1.0)]),
    ]
    # Hider: the frame-1 GT-bearing track is low-scored, so any threshold above
    # 0.1 drops it and recall drops to 0.5 -- although per-frame errors at the
    # score floor are identical to `full`.
    hide = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0, 1.0), _track(99, 5.0, 5.0, 1.0)]),
        _tr_frame(1, 0.5, [_track(1, 1.0, 0.0, 0.1)]),
    ]

    full_metrics, _ = evaluate_scene(gt, full)
    hide_metrics, _ = evaluate_scene(gt, hide)
    assert full_metrics.fp == hide_metrics.fp == 1
    assert full_metrics.fn == hide_metrics.fn == 0
    assert full_metrics.ids == hide_metrics.ids == 0
    assert full_metrics.mota == hide_metrics.mota

    full_res = compute_amota([(gt, full)])
    hide_res = compute_amota([(gt, hide)])
    # Full emission: all 40 slots at threshold 1.0, MOTAR 0.5 -> AMOTA 0.5.
    assert full_res["per_class"]["car"]["amota"] == pytest.approx(0.5)
    # Hider: only the 1.0-recall slot (threshold 0.1) reaches MOTAR 0.5.
    assert hide_res["per_class"]["car"]["amota"] == pytest.approx(0.0125)
    assert hide_res["per_class"]["car"]["amota"] < full_res["per_class"]["car"]["amota"]


def test_no_gt_class_is_nan_and_excluded_from_all():
    gt = [_gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0)])]
    tracks = [
        _tr_frame(
            0,
            0.0,
            [
                _track(1, 0.0, 0.0, 1.0),
                _track(7, 2.0, 2.0, 1.0, cls="motorcycle"),
            ],
        )
    ]
    res = compute_amota([(gt, tracks)])
    car = res["per_class"]["car"]
    assert not math.isnan(car["amota"])
    assert math.isnan(res["per_class"]["motorcycle"]["amota"])
    assert math.isnan(res["per_class"]["motorcycle"]["amotp"])
    assert res["all"]["amota"] == car["amota"]


def test_unachieved_recall_slots_filled_with_worst():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 0.0, 0.0)]),
    ]
    full = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0, 1.0)]),
        _tr_frame(1, 0.5, [_track(1, 0.0, 0.0, 1.0)]),
    ]
    # Never tracks frame 1: max recall achieved is 0.5 -> slots above are nan.
    partial = [
        _tr_frame(0, 0.0, [_track(1, 0.0, 0.0, 1.0)]),
        _tr_frame(1, 0.5, []),
    ]
    res_full = compute_amota([(gt, full)])["per_class"]["car"]
    res_part = compute_amota([(gt, partial)])["per_class"]["car"]
    assert res_full["amota"] == 1.0
    nan_slots = sum(1 for v in res_part["motar"] if math.isnan(v))
    assert nan_slots == 22
    assert res_part["amota"] == pytest.approx(0.45)  # 18 achieved slots / 40
    assert res_part["amota"] < res_full["amota"]


def test_deterministic_same_inputs_same_output():
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 1.0, 0.0), _gt_box("b", 11.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(
            0,
            0.0,
            [_track(1, 0.0, 0.0, 1.0), _track(2, 10.0, 0.0, 0.5), _track(3, 4.0, 4.0, 0.9)],
        ),
        _tr_frame(1, 0.5, [_track(1, 1.0, 0.0, 1.0), _track(2, 11.0, 0.0, 0.5)]),
    ]
    res1 = compute_amota([(gt, tracks)])
    res2 = compute_amota([(gt, tracks)])
    assert _nanaware_equal(res1, res2)


def test_cross_check_tp_fp_fn_ids_vs_evaluate_scene():
    # Frame 1 swaps the two track ids onto the other GT (2 IDS); a persistent
    # FP survives both frames. Min TP score is 0.0, so the 1.0-recall slot's
    # threshold is exactly the score floor 0.
    gt = [
        _gt_frame(0, 0.0, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
        _gt_frame(1, 0.5, [_gt_box("a", 0.0, 0.0), _gt_box("b", 10.0, 0.0)]),
    ]
    tracks = [
        _tr_frame(
            0,
            0.0,
            [
                _track(1, 0.0, 0.0, 1.0),
                _track(2, 10.0, 0.0, 0.0),
                _track(9, 20.0, 20.0, 1.0),
            ],
        ),
        _tr_frame(
            1,
            0.5,
            [
                _track(1, 10.0, 0.0, 1.0),
                _track(2, 0.0, 0.0, 0.0),
                _track(9, 20.0, 20.0, 1.0),
            ],
        ),
    ]
    metrics, _ = evaluate_scene(gt, tracks)
    res = compute_amota([(gt, tracks)])["per_class"]["car"]

    tp, fp, fn, ids, _, _ = amota._accumulate_threshold(
        [(gt, tracks)], "car", 0.0, amota.DIST_THRESHOLD
    )
    assert fp == metrics.fp == 2
    assert fn == metrics.fn == 0
    assert ids == metrics.ids == 2
    assert tp == metrics.gt_count - metrics.fn

    # The AMOTA 1.0-recall slot must agree with evaluate_scene's totals.
    slot = res["recall"].index(1.0)
    recall = 1.0
    expected = max(
        0.0,
        1.0
        - (metrics.fn + metrics.ids + metrics.fp - (1.0 - recall) * metrics.gt_count)
        / (recall * metrics.gt_count),
    )
    assert res["motar"][slot] == pytest.approx(expected)
