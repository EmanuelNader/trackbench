"""JSONL interchange schemas for TrackBench (ego-frame coordinates).

See docs/decisions.md D5. All geometric quantities are in the ego frame at
the current timestamp: x forward, y left, z up (nuScenes lidar/ego convention).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, TypedDict


DETECTION_KEYS = ("cls", "x", "y", "z", "l", "w", "h", "yaw", "score")
GT_BOX_KEYS = ("cls", "x", "y", "z", "l", "w", "h", "yaw", "score", "id", "visibility")
TRACK_KEYS = ("id", "cls", "x", "y", "yaw", "vx", "vy", "state", "age", "cov_trace")


class Detection(TypedDict):
    """Single detection / measured box in ego frame."""

    cls: str
    x: float
    y: float
    z: float
    l: float  # length (along vehicle forward when yaw=0)
    w: float  # width
    h: float  # height
    yaw: float  # radians about z
    score: float


class GTBox(TypedDict):
    """Ground-truth box in ego frame (detection fields + id / visibility)."""

    cls: str
    x: float
    y: float
    z: float
    l: float
    w: float
    h: float
    yaw: float
    score: float  # typically 1.0 for GT
    id: str
    visibility: int  # 0–4 (nuScenes-style bins; 0 = unknown / missing)


class FrameDetections(TypedDict):
    """One JSONL line in detections.jsonl."""

    frame: int
    t: float  # seconds (relative or absolute; ingest uses seconds from first keyframe)
    dets: list[Detection]


class FrameGT(TypedDict):
    """One JSONL line in gt.jsonl."""

    frame: int
    t: float
    dets: list[GTBox]


class Track(TypedDict):
    """Tracker output state (written by the C++ core later)."""

    id: int
    cls: str
    x: float
    y: float
    yaw: float
    vx: float
    vy: float
    state: str  # e.g. tentative / confirmed / coasted
    age: int
    cov_trace: float


class FrameTracks(TypedDict):
    """One JSONL line in tracks.jsonl."""

    frame: int
    t: float
    tracks: list[Track]


def validate_detection(d: Mapping[str, Any], *, require_gt_fields: bool = False) -> list[str]:
    """Return a list of missing/invalid-field messages; empty means valid.

    Checks required keys for a detection dict. When ``require_gt_fields`` is
    True, also requires ``id`` (str) and ``visibility`` (int in 0–4).
    """
    errors: list[str] = []
    required: Iterable[str] = GT_BOX_KEYS if require_gt_fields else DETECTION_KEYS
    for key in required:
        if key not in d:
            errors.append(f"missing key: {key}")

    if "visibility" in d and d["visibility"] is not None:
        vis = d["visibility"]
        if not isinstance(vis, int) or isinstance(vis, bool) or not (0 <= vis <= 4):
            errors.append(f"visibility must be int in 0–4, got {vis!r}")

    if "id" in d and d["id"] is not None and not isinstance(d["id"], str):
        errors.append(f"id must be str, got {type(d['id']).__name__}")

    return errors


def is_valid_detection(d: Mapping[str, Any], *, require_gt_fields: bool = False) -> bool:
    """True if ``validate_detection`` reports no errors."""
    return not validate_detection(d, require_gt_fields=require_gt_fields)
