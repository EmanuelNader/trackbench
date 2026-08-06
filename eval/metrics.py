"""CLEAR MOT metrics for TrackBench (M2 early).

Matching follows the nuScenes tracking convention: bipartite assignment by
**2D center distance** with a default threshold of **2.0 m**. Assignment uses
the Hungarian algorithm implemented in pure Python/numpy so the light CI
dependency set (no scipy) still works. ``requirements-full.txt`` may include
scipy for other tooling; this module does not import it.

Formulas
--------
- ``MOTA = 1 - (FN + FP + IDS) / max(GT, 1)`` where ``GT`` is the total number
  of ground-truth boxes across all frames.
- ``MOTP`` = mean 2D center distance over all matched (GT, track) pairs.
- ``IDS`` (identity switches): a GT id matched to track A in the previous
  frame where it was matched, and to a different track B in the current frame.
- ``FRAG`` (fragmentations): a GT id that was matched, then appears
  *unmatched while still present in one or more later frames*, then is matched
  again. Frames where the GT id is absent do not count as unmatched gaps.
- ``FP`` / ``FN``: unmatched hypothesis tracks / unmatched GT boxes after
  thresholded assignment.

Only tracks with ``state in {"confirmed", "coasting"}`` are scored when a
``state`` field is present; if ``state`` is absent, the track is counted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# Cost larger than any valid distance; pairs above the match threshold use this
# so Hungarian still returns a full assignment that we filter afterward.
_INVALID_COST = 1e9

_ACTIVE_STATES = frozenset({"confirmed", "coasting"})


@dataclass
class MotMetrics:
    mota: float
    motp: float
    ids: int
    frag: int
    fp: int
    fn: int
    gt_count: int  # total GT boxes across frames

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass
class FrameMatch:
    frame: int
    t: float
    matches: list[tuple[str, int, float]]  # (gt_id, track_id, dist)
    unmatched_gt: list[str]
    unmatched_tracks: list[int]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts (one object per non-empty line)."""
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object, got {type(obj).__name__}")
            rows.append(obj)
    return rows


def _center_dist(ax: float, ay: float, bx: float, by: float) -> float:
    return float(np.hypot(ax - bx, ay - by))


def _is_active_track(track: Mapping[str, Any]) -> bool:
    if "state" not in track:
        return True
    return track["state"] in _ACTIVE_STATES


def linear_sum_assignment(cost: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Minimize assignment cost; scipy-compatible ``(row_ind, col_ind)`` API.

    Pure-Python Hungarian (Kuhn–Munkres) over a dense cost matrix. Prefer this
    path so light deps (numpy only) stay sufficient for eval + unit tests.
    """
    cost = np.asarray(cost, dtype=float)
    if cost.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    if cost.ndim != 2:
        raise ValueError(f"cost must be 2-D, got shape {cost.shape}")

    n_rows, n_cols = cost.shape
    # Pad to square.
    n = max(n_rows, n_cols)
    padded = np.full((n, n), _INVALID_COST, dtype=float)
    padded[:n_rows, :n_cols] = cost

    # Step 1: subtract row minima, then column minima.
    padded = padded - padded.min(axis=1, keepdims=True)
    padded = padded - padded.min(axis=0, keepdims=True)

    star = np.zeros((n, n), dtype=bool)
    prime = np.zeros((n, n), dtype=bool)
    row_cov = np.zeros(n, dtype=bool)
    col_cov = np.zeros(n, dtype=bool)

    # Greedy initial starring of independent zeros.
    for i in range(n):
        for j in range(n):
            if padded[i, j] == 0.0 and not row_cov[i] and not col_cov[j]:
                star[i, j] = True
                row_cov[i] = True
                col_cov[j] = True
    row_cov[:] = False
    col_cov[:] = False

    def cover_starred_columns() -> None:
        col_cov[:] = star.any(axis=0)

    cover_starred_columns()

    def find_uncovered_zero() -> tuple[int, int] | None:
        uncovered = (~row_cov)[:, None] & (~col_cov)[None, :] & (padded == 0.0)
        locs = np.argwhere(uncovered)
        if locs.size == 0:
            return None
        return int(locs[0, 0]), int(locs[0, 1])

    while col_cov.sum() < n:
        while True:
            z = find_uncovered_zero()
            if z is None:
                # Adjust matrix: add min uncovered to covered rows; subtract
                # from uncovered columns.
                mask = (~row_cov)[:, None] & (~col_cov)[None, :]
                m = padded[mask].min()
                padded[row_cov, :] += m
                padded[:, ~col_cov] -= m
                continue

            i, j = z
            prime[i, j] = True
            star_cols = np.flatnonzero(star[i])
            if star_cols.size == 0:
                # Augment along alternating path.
                path = [(i, j)]
                while True:
                    star_rows = np.flatnonzero(star[:, path[-1][1]])
                    if star_rows.size == 0:
                        break
                    r = int(star_rows[0])
                    path.append((r, path[-1][1]))
                    prime_cols = np.flatnonzero(prime[r])
                    c = int(prime_cols[0])
                    path.append((r, c))
                for r, c in path:
                    star[r, c] = not star[r, c]
                prime[:, :] = False
                row_cov[:] = False
                col_cov[:] = False
                cover_starred_columns()
                break

            # Cover the row and uncover the starred column.
            c_star = int(star_cols[0])
            row_cov[i] = True
            col_cov[c_star] = False

    rows_out: list[int] = []
    cols_out: list[int] = []
    for i in range(n_rows):
        js = np.flatnonzero(star[i, :n_cols])
        if js.size:
            rows_out.append(i)
            cols_out.append(int(js[0]))
    return np.asarray(rows_out, dtype=int), np.asarray(cols_out, dtype=int)


def _index_by_frame(frames: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    out: dict[int, Mapping[str, Any]] = {}
    for row in frames:
        out[int(row["frame"])] = row
    return out


def _match_frame(
    gt_boxes: Sequence[Mapping[str, Any]],
    tracks: Sequence[Mapping[str, Any]],
    dist_threshold: float,
) -> tuple[list[tuple[str, int, float]], list[str], list[int]]:
    """Hungarian match one frame; return matches, unmatched GT ids, unmatched track ids."""
    active = [t for t in tracks if _is_active_track(t)]
    gt_ids = [str(g["id"]) for g in gt_boxes]
    track_ids = [int(t["id"]) for t in active]

    if not gt_boxes and not active:
        return [], [], []
    if not gt_boxes:
        return [], [], track_ids
    if not active:
        return [], gt_ids, []

    n_gt = len(gt_boxes)
    n_tr = len(active)
    cost = np.full((n_gt, n_tr), _INVALID_COST, dtype=float)
    dist = np.full((n_gt, n_tr), np.inf, dtype=float)
    for i, g in enumerate(gt_boxes):
        for j, t in enumerate(active):
            d = _center_dist(float(g["x"]), float(g["y"]), float(t["x"]), float(t["y"]))
            dist[i, j] = d
            if d <= dist_threshold:
                cost[i, j] = d

    row_ind, col_ind = linear_sum_assignment(cost)
    matched_gt: set[int] = set()
    matched_tr: set[int] = set()
    matches: list[tuple[str, int, float]] = []
    for r, c in zip(row_ind.tolist(), col_ind.tolist(), strict=True):
        d = float(dist[r, c])
        if d <= dist_threshold:
            matches.append((gt_ids[r], track_ids[c], d))
            matched_gt.add(r)
            matched_tr.add(c)

    unmatched_gt = [gt_ids[i] for i in range(n_gt) if i not in matched_gt]
    unmatched_tracks = [track_ids[j] for j in range(n_tr) if j not in matched_tr]
    return matches, unmatched_gt, unmatched_tracks


def evaluate_scene(
    gt_frames: Sequence[Mapping[str, Any]],
    track_frames: Sequence[Mapping[str, Any]],
    dist_threshold: float = 2.0,
) -> tuple[MotMetrics, list[FrameMatch]]:
    """Compute CLEAR MOT metrics and per-frame match records for one scene."""
    gt_by_frame = _index_by_frame(gt_frames)
    tr_by_frame = _index_by_frame(track_frames)
    frame_ids = sorted(set(gt_by_frame) | set(tr_by_frame))

    total_fp = 0
    total_fn = 0
    total_ids = 0
    total_frag = 0
    gt_count = 0
    motp_sum = 0.0
    motp_n = 0

    # Previous matched track id for each GT (only updated when GT is matched).
    prev_match: dict[str, int] = {}
    # Fragmentation bookkeeping (see module docstring).
    ever_matched: set[str] = set()
    unmatched_since_match: set[str] = set()

    frame_matches: list[FrameMatch] = []

    for frame in frame_ids:
        gt_row = gt_by_frame.get(frame)
        tr_row = tr_by_frame.get(frame)
        gt_boxes: list[Mapping[str, Any]] = list(gt_row["dets"]) if gt_row else []
        tracks: list[Mapping[str, Any]] = list(tr_row["tracks"]) if tr_row else []
        t = float(gt_row["t"] if gt_row is not None else tr_row["t"])  # type: ignore[index]

        gt_count += len(gt_boxes)
        matches, unmatched_gt, unmatched_tracks = _match_frame(
            gt_boxes, tracks, dist_threshold
        )

        total_fp += len(unmatched_tracks)
        total_fn += len(unmatched_gt)

        matched_now = {gid: tid for gid, tid, _d in matches}
        for gid, tid, d in matches:
            motp_sum += d
            motp_n += 1
            if gid in prev_match and prev_match[gid] != tid:
                total_ids += 1
            if gid in unmatched_since_match and gid in ever_matched:
                total_frag += 1
                unmatched_since_match.discard(gid)
            ever_matched.add(gid)
            prev_match[gid] = tid

        for gid in unmatched_gt:
            if gid in ever_matched:
                unmatched_since_match.add(gid)

        frame_matches.append(
            FrameMatch(
                frame=frame,
                t=t,
                matches=matches,
                unmatched_gt=unmatched_gt,
                unmatched_tracks=unmatched_tracks,
            )
        )

    mota = 1.0 - (total_fn + total_fp + total_ids) / max(gt_count, 1)
    motp = (motp_sum / motp_n) if motp_n else 0.0

    metrics = MotMetrics(
        mota=float(mota),
        motp=float(motp),
        ids=int(total_ids),
        frag=int(total_frag),
        fp=int(total_fp),
        fn=int(total_fn),
        gt_count=int(gt_count),
    )
    return metrics, frame_matches


def match_records_for_miner(frame_matches: Sequence[FrameMatch]) -> list[dict[str, Any]]:
    """Flatten per-frame matches into failure_miner-oriented dicts.

    Each record: ``{frame, gt_id, track_id, dist}``.
    """
    rows: list[dict[str, Any]] = []
    for fm in frame_matches:
        for gt_id, track_id, dist in fm.matches:
            rows.append(
                {
                    "frame": fm.frame,
                    "gt_id": gt_id,
                    "track_id": track_id,
                    "dist": dist,
                }
            )
    return rows


def summarize_metrics(
    gt_frames: Sequence[Mapping[str, Any]],
    pred_frames: Sequence[Mapping[str, Any]],
    *,
    dist_threshold: float = 2.0,
    **_kwargs: Any,
) -> dict[str, float | int]:
    """Convenience wrapper returning a plain metrics dict."""
    metrics, _ = evaluate_scene(gt_frames, pred_frames, dist_threshold=dist_threshold)
    return metrics.to_dict()


# Thin aliases kept for earlier stub names.
def mota(
    gt_frames: Sequence[Mapping[str, Any]],
    track_frames: Sequence[Mapping[str, Any]],
    *,
    dist_threshold: float = 2.0,
) -> float:
    return evaluate_scene(gt_frames, track_frames, dist_threshold=dist_threshold)[0].mota


def motp(
    gt_frames: Sequence[Mapping[str, Any]],
    track_frames: Sequence[Mapping[str, Any]],
    *,
    dist_threshold: float = 2.0,
) -> float:
    return evaluate_scene(gt_frames, track_frames, dist_threshold=dist_threshold)[0].motp


def idsw(
    gt_frames: Sequence[Mapping[str, Any]],
    track_frames: Sequence[Mapping[str, Any]],
    *,
    dist_threshold: float = 2.0,
) -> int:
    return evaluate_scene(gt_frames, track_frames, dist_threshold=dist_threshold)[0].ids


def fragmentations(
    gt_frames: Sequence[Mapping[str, Any]],
    track_frames: Sequence[Mapping[str, Any]],
    *,
    dist_threshold: float = 2.0,
) -> int:
    return evaluate_scene(gt_frames, track_frames, dist_threshold=dist_threshold)[0].frag
