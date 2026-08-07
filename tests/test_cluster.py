"""Tests for rule-based failure clustering."""

from __future__ import annotations

import pytest

from eval.cluster import cluster_failures, cluster_failures_dbscan


def _event(
    kind: str,
    *,
    range_bin: str = "near",
    cls: str = "car",
    visibility: int | None = 4,
    neighbor_count_5m: int = 0,
    weather: str | None = "clear",
    time_of_day: str | None = "day",
    frame: int = 0,
    track_id: int | None = 1,
    gt_id: str | None = "a",
) -> dict:
    return {
        "scene_id": "s",
        "frame": frame,
        "t": float(frame) * 0.5,
        "kind": kind,
        "track_id": track_id,
        "gt_id": gt_id,
        "severity": 0.5,
        "features": {
            "range_m": {"near": 5.0, "mid": 20.0, "far": 40.0}[range_bin],
            "range_bin": range_bin,
            "cls": cls,
            "visibility": visibility,
            "ego_speed": 0.0,
            "weather": weather,
            "time_of_day": time_of_day,
            "neighbor_count_5m": neighbor_count_5m,
            "duration_frames": 3,
        },
    }


def test_rule_buckets_and_sort_by_size():
    failures = [
        _event("GHOST_TRACK", track_id=1, gt_id=None),
        _event("GHOST_TRACK", track_id=2, gt_id=None, frame=1),
        _event(
            "ID_SWITCH",
            neighbor_count_5m=4,
            frame=2,
        ),
        _event("LATE_INIT", range_bin="far", frame=3),
        _event("ID_SWITCH", neighbor_count_5m=0, frame=4),  # other_id_switch
        _event(
            "TRACK_DROP",
            cls="pedestrian",
            range_bin="far",
            visibility=1,
            frame=5,
        ),  # far_lowvis_ped takes precedence over kind fallback
    ]
    clusters = cluster_failures(failures)
    assert clusters
    assert clusters[0]["size"] >= clusters[-1]["size"]

    by_bucket = {c["bucket"]: c for c in clusters}
    assert "ghost_any" in by_bucket
    assert by_bucket["ghost_any"]["size"] == 2
    assert "dense_id_switch" in by_bucket
    assert by_bucket["dense_id_switch"]["size"] == 1
    assert "late_init_far" in by_bucket
    assert "far_lowvis_ped" in by_bucket
    assert "other_id_switch" in by_bucket

    ghost = by_bucket["ghost_any"]
    assert "event_indices" in ghost
    assert "event_ids" in ghost
    assert "summary" in ghost
    assert ghost["summary"]["n"] == 2
    assert "Ghost" in ghost["label"] or "ghost" in ghost["label"].lower()


def test_night_rain_bucket():
    failures = [
        _event(
            "TRACK_DEATH",
            weather="heavy rain",
            time_of_day="night",
        )
    ]
    clusters = cluster_failures(failures)
    assert len(clusters) == 1
    assert clusters[0]["bucket"] == "night_rain"


def test_pos_spike_bucket():
    failures = [_event("POS_ERROR_SPIKE")]
    clusters = cluster_failures(failures)
    assert clusters[0]["bucket"] == "pos_spike"


def test_dbscan_stub_not_default():
    with pytest.raises(NotImplementedError, match="residual large|not default"):
        cluster_failures_dbscan([])
