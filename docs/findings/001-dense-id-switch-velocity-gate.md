# 001 — Dense-traffic ID switches from position-only association

## What the system surfaced

After ingesting nuScenes `v1.0-mini` with Megvii detections (train∪val),
filtering to the 7 tracking classes, running the CV-EKF tracker, and mining:

| kind | count (10 scenes, pre-fix) |
|------|-------------------------------|
| `ID_SWITCH` | **890** |
| `LATE_INIT` | 374 |
| `GHOST_TRACK` | 369 |

Largest clusters: **`other_id_switch` / `dense_id_switch`** on
`scene-0655` and `scene-0916`.

## Hypothesis

1. **Position-only Mahalanobis cost** lets nearby same-class objects swap IDs
   when both fall inside a ~2 m gate.
2. **Every unmatched detection births a track** (even middling scores), so dense
   frames create many tentative hypotheses that steal associations next frame.

## Experiments

| attempt | result |
|---------|--------|
| Hard lateral/rear velocity **reject** | IDS **worse** (890 → 913). Rejected good matches → coast → rematch as switch. |
| Soft lateral velocity **cost** + `gate_m=1.5` + `min_birth_score=0.5` | *(remeasure — this commit)* |

## Change (current)

1. Ingest: tracking classes only, detection score ≥ 0.3.
2. Association: soft penalty
   `cost += vel_cost_weight * (lat / vel_gate_lateral_m)^2` for moving tracks.
3. Euclidean gate tightened `2.0 → 1.5` m.
4. Birth threshold: unmatched dets with `score < 0.5` do not start tracks
   (they can still update existing tracks if associated).

## How to remeasure

```bash
git pull origin cursor/m0-skeleton-86da
make core
PYTHONPATH=. python -m ingest.nuscenes_ingest \
  --detections-json data/raw/detections/megvii_mini_merged.json --force
# then track + eval all 10 scenes
```

## Before (class-filtered baseline, hard-gate attempt discarded)

| scene | MOTA | IDS | FP | FN |
|-------|------|-----|----|----|
| scene-0655 | -0.205 | 471 | 486 | 1271 |
| scene-0916 | -0.291 | 384 | 813 | 1304 |
| all ID_SWITCH events | | 890 | | |

## After

*(fill after local remeasure)*

## Expected tradeoffs

Higher birth score and tighter gate can raise **LATE_INIT / FN**. Report IDS
wins and FN/MOTA regressions together.
