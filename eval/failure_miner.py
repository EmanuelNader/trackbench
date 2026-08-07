"""Failure mining over CLEAR MOT match records (M3).

Walks per-frame ``FrameMatch`` output from ``evaluate_scene`` and emits
structured failure event dicts (not persisted to DB yet).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from eval.metrics import FrameMatch, evaluate_scene

_ACTIVE_STATES = frozenset({"confirmed", "coasting"})

KIND_ID_SWITCH = "ID_SWITCH"
KIND_TRACK_DROP = "TRACK_DROP"
KIND_TRACK_DEATH = "TRACK_DEATH"
KIND_GHOST_TRACK = "GHOST_TRACK"
KIND_LATE_INIT = "LATE_INIT"
KIND_POS_ERROR_SPIKE = "POS_ERROR_SPIKE"


def load_scene_meta(path: str | Path | None) -> dict[str, Any]:
    """Load scene_meta.json if present; return empty dict otherwise."""
    if path is None:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def range_bin(range_m: float) -> str:
    if range_m < 15.0:
        return "near"
    if range_m <= 30.0:
        return "mid"
    return "far"


def _hypot(x: float, y: float) -> float:
    return float(math.hypot(x, y))


def _index_by_frame(frames: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    out: dict[int, Mapping[str, Any]] = {}
    for row in frames:
        out[int(row["frame"])] = row
    return out


def _meta_weather(scene_meta: Mapping[str, Any]) -> str | None:
    w = scene_meta.get("weather")
    return str(w) if w is not None else None


def _meta_time_of_day(scene_meta: Mapping[str, Any]) -> str | None:
    tod = scene_meta.get("time_of_day", scene_meta.get("timeOfDay"))
    return str(tod) if tod is not None else None


def _meta_ego_speed(scene_meta: Mapping[str, Any]) -> float:
    for key in ("ego_speed", "egoSpeed", "ego_speed_mps"):
        if key in scene_meta and scene_meta[key] is not None:
            return float(scene_meta[key])
    return 0.0


def _is_active_track(track: Mapping[str, Any]) -> bool:
    if "state" not in track:
        return True
    return track["state"] in _ACTIVE_STATES


def _boxes_by_id(boxes: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(b["id"]): b for b in boxes}


def _active_tracks_by_id(
    tracks: Sequence[Mapping[str, Any]],
) -> dict[int, Mapping[str, Any]]:
    return {int(t["id"]): t for t in tracks if _is_active_track(t)}


def _vis(box: Mapping[str, Any]) -> int | None:
    if "visibility" not in box or box["visibility"] is None:
        return None
    return int(box["visibility"])


def _neighbor_count(
    x: float,
    y: float,
    others: Sequence[Mapping[str, Any]],
    *,
    radius: float = 5.0,
    self_id: str | int | None = None,
) -> int:
    n = 0
    for o in others:
        oid = o.get("id")
        if self_id is not None and oid is not None and str(oid) == str(self_id):
            continue
        if _hypot(float(o["x"]) - x, float(o["y"]) - y) <= radius:
            n += 1
    return n


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(np.median(np.asarray(values, dtype=float)))


def _make_features(
    *,
    x: float,
    y: float,
    cls: str,
    visibility: int | None,
    neighbor_sources: Sequence[Mapping[str, Any]],
    self_id: str | int | None,
    duration_frames: int,
    scene_meta: Mapping[str, Any],
) -> dict[str, Any]:
    r = _hypot(x, y)
    return {
        "range_m": r,
        "range_bin": range_bin(r),
        "cls": cls,
        "visibility": visibility,
        "ego_speed": _meta_ego_speed(scene_meta),
        "weather": _meta_weather(scene_meta),
        "time_of_day": _meta_time_of_day(scene_meta),
        "neighbor_count_5m": _neighbor_count(x, y, neighbor_sources, self_id=self_id),
        "duration_frames": int(duration_frames),
    }


def _event(
    *,
    scene_id: str,
    frame: int,
    t: float,
    kind: str,
    track_id: int | None,
    gt_id: str | None,
    severity: float,
    features: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scene_id": scene_id,
        "frame": int(frame),
        "t": float(t),
        "kind": kind,
        "track_id": track_id,
        "gt_id": gt_id,
        "severity": _clamp01(severity),
        "features": features,
    }


def mine_failures(
    gt_frames: Sequence[Mapping[str, Any]],
    pred_frames: Sequence[Mapping[str, Any]],
    frame_matches: Sequence[FrameMatch] | None = None,
    *,
    scene_id: str = "",
    scene_meta: Mapping[str, Any] | None = None,
    dist_threshold: float = 2.0,
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """Extract per-event failure records from matching output.

    If ``frame_matches`` is omitted, recomputes them via ``evaluate_scene``.
    """
    meta: Mapping[str, Any] = scene_meta or {}
    if frame_matches is None:
        _, frame_matches = evaluate_scene(
            gt_frames, pred_frames, dist_threshold=dist_threshold
        )

    gt_by_frame = _index_by_frame(gt_frames)
    tr_by_frame = _index_by_frame(pred_frames)
    events: list[dict[str, Any]] = []

    prev_match: dict[str, int] = {}
    ever_matched: set[str] = set()
    # Consecutive frames where GT is present but unmatched (after a prior match).
    drop_streak: dict[str, int] = {}
    # Unmatched visible frames before the GT's first match.
    late_streak: dict[str, int] = {}
    late_init_emitted: set[str] = set()
    last_match_track: dict[str, int] = {}
    # GT → frame where its last track disappeared while GT still present.
    death_start: dict[str, dict[str, Any]] = {}

    ghost_streak: dict[int, int] = {}
    ghost_emitted: set[int] = set()
    track_error_history: dict[int, list[float]] = {}

    for fm in frame_matches:
        frame = fm.frame
        t = fm.t
        gt_row = gt_by_frame.get(frame)
        tr_row = tr_by_frame.get(frame)
        gt_boxes: list[Mapping[str, Any]] = list(gt_row["dets"]) if gt_row else []
        all_tracks: list[Mapping[str, Any]] = list(tr_row["tracks"]) if tr_row else []
        active_tracks = [tr for tr in all_tracks if _is_active_track(tr)]
        gt_map = _boxes_by_id(gt_boxes)
        active_map = _active_tracks_by_id(all_tracks)

        matched_gt = {gid: (tid, dist) for gid, tid, dist in fm.matches}
        matched_track_ids = {tid for _gid, tid, _d in fm.matches}

        # --- Matches ---
        for gid, (tid, dist) in matched_gt.items():
            gbox = gt_map[gid]

            if gid in prev_match and prev_match[gid] != tid:
                prev_tid = int(prev_match[gid])
                feats = _make_features(
                    x=float(gbox["x"]),
                    y=float(gbox["y"]),
                    cls=str(gbox.get("cls", "unknown")),
                    visibility=_vis(gbox),
                    neighbor_sources=gt_boxes,
                    self_id=gid,
                    duration_frames=1,
                    scene_meta=meta,
                )
                feats["prev_track_id"] = prev_tid
                feats["new_track_id"] = int(tid)
                events.append(
                    _event(
                        scene_id=scene_id,
                        frame=frame,
                        t=t,
                        kind=KIND_ID_SWITCH,
                        track_id=tid,
                        gt_id=gid,
                        severity=1.0,
                        features=feats,
                    )
                )

            streak = drop_streak.get(gid, 0)
            if gid in ever_matched and streak >= 2:
                events.append(
                    _event(
                        scene_id=scene_id,
                        frame=frame,
                        t=t,
                        kind=KIND_TRACK_DROP,
                        track_id=tid,
                        gt_id=gid,
                        severity=_clamp01(streak / 10.0),
                        features=_make_features(
                            x=float(gbox["x"]),
                            y=float(gbox["y"]),
                            cls=str(gbox.get("cls", "unknown")),
                            visibility=_vis(gbox),
                            neighbor_sources=gt_boxes,
                            self_id=gid,
                            duration_frames=streak,
                            scene_meta=meta,
                        ),
                    )
                )

            if gid not in ever_matched and gid not in late_init_emitted:
                n_late = late_streak.get(gid, 0)
                if n_late >= 3:
                    events.append(
                        _event(
                            scene_id=scene_id,
                            frame=frame,
                            t=t,
                            kind=KIND_LATE_INIT,
                            track_id=tid,
                            gt_id=gid,
                            severity=_clamp01(n_late / 10.0),
                            features=_make_features(
                                x=float(gbox["x"]),
                                y=float(gbox["y"]),
                                cls=str(gbox.get("cls", "unknown")),
                                visibility=_vis(gbox),
                                neighbor_sources=gt_boxes,
                                self_id=gid,
                                duration_frames=n_late,
                                scene_meta=meta,
                            ),
                        )
                    )
                    late_init_emitted.add(gid)

            hist = track_error_history.setdefault(tid, [])
            if len(hist) >= 5:
                med = _median(hist)
                if med > 0.0 and dist > 3.0 * med:
                    events.append(
                        _event(
                            scene_id=scene_id,
                            frame=frame,
                            t=t,
                            kind=KIND_POS_ERROR_SPIKE,
                            track_id=tid,
                            gt_id=gid,
                            severity=_clamp01(dist / (3.0 * med) - 1.0),
                            features=_make_features(
                                x=float(gbox["x"]),
                                y=float(gbox["y"]),
                                cls=str(gbox.get("cls", "unknown")),
                                visibility=_vis(gbox),
                                neighbor_sources=gt_boxes,
                                self_id=gid,
                                duration_frames=1,
                                scene_meta=meta,
                            ),
                        )
                    )
            hist.append(float(dist))

            drop_streak[gid] = 0
            death_start.pop(gid, None)
            ever_matched.add(gid)
            prev_match[gid] = tid
            last_match_track[gid] = tid

        # --- Unmatched present GTs ---
        for gid, gbox in gt_map.items():
            if gid in matched_gt:
                continue
            if gid not in ever_matched:
                late_streak[gid] = late_streak.get(gid, 0) + 1
            else:
                drop_streak[gid] = drop_streak.get(gid, 0) + 1
                last_tid = last_match_track.get(gid)
                if last_tid is not None and last_tid not in active_map:
                    if gid not in death_start:
                        death_start[gid] = {
                            "frame": frame,
                            "t": t,
                            "track_id": last_tid,
                        }

        # GT left the scene → not TRACK_DEATH
        for gid in list(death_start):
            if gid not in gt_map:
                death_start.pop(gid, None)

        # --- GHOST_TRACK ---
        active_ids = set(active_map)
        for tid in list(ghost_streak):
            if tid not in active_ids:
                ghost_streak.pop(tid, None)
                ghost_emitted.discard(tid)

        for tid, tr in active_map.items():
            if tid in matched_track_ids:
                ghost_streak[tid] = 0
                ghost_emitted.discard(tid)
                continue
            ghost_streak[tid] = ghost_streak.get(tid, 0) + 1
            streak = ghost_streak[tid]
            if streak >= 3 and tid not in ghost_emitted:
                events.append(
                    _event(
                        scene_id=scene_id,
                        frame=frame,
                        t=t,
                        kind=KIND_GHOST_TRACK,
                        track_id=tid,
                        gt_id=None,
                        severity=_clamp01(streak / 10.0),
                        features=_make_features(
                            x=float(tr["x"]),
                            y=float(tr["y"]),
                            cls=str(tr.get("cls", "unknown")),
                            visibility=None,
                            neighbor_sources=active_tracks,
                            self_id=tid,
                            duration_frames=streak,
                            scene_meta=meta,
                        ),
                    )
                )
                ghost_emitted.add(tid)

    # TRACK_DEATH: still in death_start ⇒ never rematched while GT remained present.
    for gid, info in death_start.items():
        last_gbox: Mapping[str, Any] | None = None
        last_frame = int(info["frame"])
        last_t = float(info["t"])
        duration = 0
        for fm in frame_matches:
            if fm.frame < int(info["frame"]):
                continue
            gt_row = gt_by_frame.get(fm.frame)
            if not gt_row:
                continue
            gmap = _boxes_by_id(list(gt_row["dets"]))
            if gid not in gmap:
                continue
            last_gbox = gmap[gid]
            last_frame = fm.frame
            last_t = fm.t
            if gid not in {m[0] for m in fm.matches}:
                duration += 1
        if last_gbox is None:
            continue
        gt_neighbors = list(gt_by_frame.get(last_frame, {}).get("dets", []))  # type: ignore[union-attr]
        if not gt_neighbors:
            gt_neighbors = [last_gbox]
        events.append(
            _event(
                scene_id=scene_id,
                frame=last_frame,
                t=last_t,
                kind=KIND_TRACK_DEATH,
                track_id=int(info["track_id"]),
                gt_id=gid,
                severity=1.0,
                features=_make_features(
                    x=float(last_gbox["x"]),
                    y=float(last_gbox["y"]),
                    cls=str(last_gbox.get("cls", "unknown")),
                    visibility=_vis(last_gbox),
                    neighbor_sources=gt_neighbors,
                    self_id=gid,
                    duration_frames=max(duration, 1),
                    scene_meta=meta,
                ),
            )
        )

    # LATE_INIT for GTs visible ≥3 unmatched frames and never matched.
    for gid, n_late in late_streak.items():
        if gid in ever_matched or gid in late_init_emitted or n_late < 3:
            continue
        emit_frame: int | None = None
        emit_t = 0.0
        gbox_at: Mapping[str, Any] | None = None
        seen = 0
        for fm in frame_matches:
            gt_row = gt_by_frame.get(fm.frame)
            if not gt_row:
                continue
            gmap = _boxes_by_id(list(gt_row["dets"]))
            if gid not in gmap:
                continue
            seen += 1
            if seen >= 3:
                emit_frame = fm.frame
                emit_t = fm.t
                gbox_at = gmap[gid]
                break
        if emit_frame is None or gbox_at is None:
            continue
        gt_boxes_emit = list(gt_by_frame[emit_frame]["dets"])  # type: ignore[index]
        events.append(
            _event(
                scene_id=scene_id,
                frame=emit_frame,
                t=emit_t,
                kind=KIND_LATE_INIT,
                track_id=None,
                gt_id=gid,
                severity=_clamp01(n_late / 10.0),
                features=_make_features(
                    x=float(gbox_at["x"]),
                    y=float(gbox_at["y"]),
                    cls=str(gbox_at.get("cls", "unknown")),
                    visibility=_vis(gbox_at),
                    neighbor_sources=gt_boxes_emit,
                    self_id=gid,
                    duration_frames=n_late,
                    scene_meta=meta,
                ),
            )
        )

    events.sort(
        key=lambda e: (
            e["frame"],
            e["kind"],
            e.get("gt_id") or "",
            -1 if e.get("track_id") is None else int(e["track_id"]),
        )
    )
    return events
