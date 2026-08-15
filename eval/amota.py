"""nuScenes AMOTA / AMOTP (recall-curve MOTAR) for TrackBench.

Implements the AMOTA definition in ``docs/superpowers/plans/phase5-amota-pareto.md``,
taken line-by-line from the nuscenes-devkit (``algo.compute_thresholds`` /
``accumulate_threshold``, ``metrics.motar``, ``evaluate.py`` AMOTA aggregation).
Pure stdlib + numpy.

Per-frame matching reuses ``eval/metrics.py`` (min-cost Hungarian on XY center
distance with ``dist_threshold = 2.0`` and the confirmed/coasting active-track
filter) so AMOTA and the CLEAR MOTA/IDS eval share matching semantics.

Documented divergences from the devkit (per the plan, not bugs):
- ``class_range`` filtering (car 50 m / ped 40 m) is OFF, matching our MOTA eval.
- A track's score is the box's own ``score``; the plan's constant birth score
  makes the devkit's per-frame score averaging a no-op. Boxes without a
  ``score`` field default to 1.0 so pre-Task-1 track dumps still evaluate.

Output is JSON-serializable: ``{"per_class": {cls: {amota, amotp, recall,
motar, confidence}}, "all": {amota, amotp}}`` where ``recall``/``motar``/
``confidence`` are the 40 recall slots (highest recall first, the devkit's
presentation order). A class without GT boxes gets ``nan`` per-class values and
is excluded from ``all`` via nanmean.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from eval.metrics import _index_by_frame, _is_active_track, _match_frame

DIST_THRESHOLD = 2.0
MIN_RECALL = 0.1
NUM_THRESHOLDS = 40
AMOTA_WORST = 0.0
AMOTP_WORST = 2.0
_DEFAULT_SCORE = 1.0

Scene = tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]


def _box_score(box: Mapping[str, Any]) -> float:
    return float(box.get("score", _DEFAULT_SCORE))


def _recall_grid() -> np.ndarray:
    return np.linspace(MIN_RECALL, 1.0, NUM_THRESHOLDS).round(12)


def _collect_classes(scenes: Sequence[Scene]) -> list[str]:
    """Sorted union of classes present in GT or tracks (derive from data)."""
    classes: set[str] = set()
    for gt_frames, tr_frames in scenes:
        for row in gt_frames:
            for box in row.get("dets", []):
                classes.add(box["cls"])
        for row in tr_frames:
            for track in row.get("tracks", []):
                classes.add(track["cls"])
    return sorted(classes)


def _class_frames(
    scenes: Sequence[Scene],
    cls: str,
    min_score: Optional[float],
    dist_threshold: float,
):
    """Yield ``(gt_boxes, tracks)`` for one class in pooled frame order.

    Scenes are visited in input order; within a scene, frames are visited in
    ascending ``frame`` id order, so the pooled sequence equals sequentially
    numbered unique frame ids. Frames where the class has no GT boxes and no
    (surviving) tracks are skipped. Tracks are filtered by the active-state
    rule shared with ``eval/metrics.py``.
    """
    for gt_frames, tr_frames in scenes:
        gt_by_frame = _index_by_frame(gt_frames)
        tr_by_frame = _index_by_frame(tr_frames)
        for frame in sorted(set(gt_by_frame) | set(tr_by_frame)):
            gt_row = gt_by_frame.get(frame)
            tr_row = tr_by_frame.get(frame)
            gt_boxes = (
                [b for b in gt_row.get("dets", []) if b["cls"] == cls]
                if gt_row is not None
                else []
            )
            tracks = [
                t
                for t in (tr_row.get("tracks", []) if tr_row is not None else [])
                if t["cls"] == cls and _is_active_track(t)
            ]
            if min_score is not None:
                tracks = [t for t in tracks if _box_score(t) >= min_score]
            if not gt_boxes and not tracks:
                continue
            yield gt_boxes, tracks


def _accumulate_threshold(
    scenes: Sequence[Scene],
    cls: str,
    min_score: float,
    dist_threshold: float,
) -> tuple[int, int, int, int, float, int]:
    """Re-match all frames at ``min_score``; return (tp, fp, fn, ids, motp_sum, motp_n).

    IDS is counted the same way ``eval/metrics.py`` counts identity switches:
    a GT id matched to a different track than the previous frame it was matched.
    """
    tp = 0
    fp = 0
    fn = 0
    ids = 0
    motp_sum = 0.0
    motp_n = 0
    prev_match: dict[str, int] = {}
    for gt_boxes, tracks in _class_frames(scenes, cls, min_score, dist_threshold):
        matches, unmatched_gt, unmatched_tracks = _match_frame(
            gt_boxes, tracks, dist_threshold
        )
        fp += len(unmatched_tracks)
        fn += len(unmatched_gt)
        for gid, tid, dist in matches:
            tp += 1
            motp_sum += dist
            motp_n += 1
            if gid in prev_match and prev_match[gid] != tid:
                ids += 1
            prev_match[gid] = tid
    return tp, fp, fn, ids, motp_sum, motp_n


def _nan_class(rec_grid: np.ndarray) -> dict[str, Any]:
    nan_out = [float("nan")] * NUM_THRESHOLDS
    return {
        "amota": float("nan"),
        "amotp": float("nan"),
        "recall": rec_grid[::-1].tolist(),
        "motar": nan_out,
        "confidence": nan_out,
    }


def _compute_class(
    scenes: Sequence[Scene],
    cls: str,
    dist_threshold: float,
) -> dict[str, Any]:
    rec_grid = _recall_grid()

    # Pass 1: no score filter; collect the score of every TP match.
    gt_boxes_total = 0
    tp_scores: list[float] = []
    for gt_boxes, tracks in _class_frames(scenes, cls, None, dist_threshold):
        gt_boxes_total += len(gt_boxes)
        if not gt_boxes or not tracks:
            continue
        matches, _, _ = _match_frame(gt_boxes, tracks, dist_threshold)
        score_by_id = {int(t["id"]): _box_score(t) for t in tracks}
        for _gid, tid, _dist in matches:
            tp_scores.append(score_by_id.get(tid, _DEFAULT_SCORE))

    if gt_boxes_total == 0 or not tp_scores:
        return _nan_class(rec_grid)

    scores_desc = np.asarray(sorted(tp_scores, reverse=True), dtype=float)
    rec = np.arange(1, len(scores_desc) + 1, dtype=float) / gt_boxes_total
    thresholds = np.interp(rec_grid, rec, scores_desc, right=0.0)
    thresholds[rec_grid > float(rec[-1])] = np.nan  # unachieved recall slots

    # Pass 2: each unique non-nan threshold gets a full re-match.
    counts = {}
    for th in sorted({float(t) for t in thresholds if not math.isnan(t)}):
        counts[th] = _accumulate_threshold(scenes, cls, th, dist_threshold)

    # MOTAR / MOTP per recall slot (presentation order = highest recall first).
    motar: list[float] = []
    motp: list[float] = []
    for th, _target in zip(thresholds[::-1].tolist(), rec_grid[::-1].tolist()):
        if math.isnan(th):
            motar.append(float("nan"))
            motp.append(float("nan"))
            continue
        tp, fp, fn, ids, motp_sum, motp_n = counts[th]
        recall = tp / gt_boxes_total
        denom = recall * gt_boxes_total
        if denom == 0:
            motar.append(float("nan"))
            motp.append(float("nan"))
            continue
        motar.append(
            max(
                0.0,
                1.0
                - (fn + ids + fp - (1.0 - recall) * gt_boxes_total) / denom,
            )
        )
        motp.append(motp_sum / motp_n if motp_n else float("nan"))

    motar_arr = np.asarray(motar, dtype=float)
    motp_arr = np.asarray(motp, dtype=float)
    if bool(np.isnan(motar_arr).all()):
        amota = float("nan")
    else:
        amota = float(np.mean(np.where(np.isnan(motar_arr), AMOTA_WORST, motar_arr)))
    if bool(np.isnan(motp_arr).all()):
        amotp = float("nan")
    else:
        amotp = float(np.mean(np.where(np.isnan(motp_arr), AMOTP_WORST, motp_arr)))

    return {
        "amota": amota,
        "amotp": amotp,
        "recall": rec_grid[::-1].tolist(),
        "motar": motar,
        "confidence": thresholds[::-1].tolist(),
    }


def _nanmean(values: Sequence[float]) -> float:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return float("nan")
    return float(sum(vals) / len(vals))


def compute_amota(
    scenes: Sequence[Scene],
    *,
    dist_threshold: float = DIST_THRESHOLD,
) -> dict[str, Any]:
    """AMOTA/AMOTP over pooled scenes: ``(gt_frames, track_frames)`` per scene.

    Classes are derived from the data (sorted); a class with no GT boxes gets
    ``nan`` and is excluded from ``all`` via nanmean. Deterministic: fixed
    iteration order (scenes in input order, classes sorted), no RNG.
    """
    per_class = {
        cls: _compute_class(scenes, cls, dist_threshold)
        for cls in _collect_classes(scenes)
    }
    return {
        "per_class": per_class,
        "all": {
            "amota": _nanmean([v["amota"] for v in per_class.values()]),
            "amotp": _nanmean([v["amotp"] for v in per_class.values()]),
        },
    }
