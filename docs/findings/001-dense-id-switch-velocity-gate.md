# 001 — Dense-traffic ID switches from position-only association

## What the system surfaced

After ingesting nuScenes `v1.0-mini` with Megvii detections (train∪val),
running the CV-EKF tracker, and mining failures:

| kind | count (10 scenes) |
|------|-------------------|
| `ID_SWITCH` | **890** |
| `LATE_INIT` | 374 |
| `GHOST_TRACK` | 369 |
| `TRACK_DROP` | 92 |
| `POS_ERROR_SPIKE` | 91 |
| `TRACK_DEATH` | 23 |

Largest clusters were **`other_id_switch` / `dense_id_switch`** on
`scene-0655` and `scene-0916` (hundreds of events each).

## Hypothesis

Association cost was **squared Mahalanobis in position only**, gated by
class + Euclidean radius. In dense same-class traffic, a neighboring vehicle
often falls inside the gate of the wrong track. Hungarian then swaps IDs
even when the detection disagrees with the track’s estimated velocity.

Public lineage: motion-consistency / velocity gating is standard in classical
MOT (SORT / AB3DMOT-style association refinements).

## Also required for a fair loop

Unfiltered Megvii outputs include barriers, cones, and low-score boxes.
Evaluating those as tracks vs all GT boxes made MOTA unreadable. Ingest now
keeps only the **7 nuScenes tracking classes** and detections with
**score ≥ 0.3** (same convention as the tracking challenge class set).

## Change

1. **Ingest filters** — `TRACKING_CLASSES` + `DEFAULT_MIN_DET_SCORE = 0.3`
2. **Velocity-consistency gate** in `core/src/association.cpp` (config keys
   `vel_gate_min_speed`, `vel_gate_lateral_m`, `vel_gate_rear_m`):
   for tracks with `hits >= 2` and speed ≥ threshold, reject associations
   whose innovation is too far **lateral** to velocity or too far **behind**
   the predicted position.

## How to remeasure

```bash
git pull origin cursor/m0-skeleton-86da
make core

PYTHONPATH=. python -m ingest.nuscenes_ingest \
  --detections-json data/raw/detections/megvii_mini_merged.json --force

# track + eval all 10 (same loops as before)
```

Compare aggregate IDS and the size of `other_id_switch` / `dense_id_switch`
clusters on `scene-0655` / `scene-0916` before vs after.

## Expected tradeoff

Tight velocity gates can increase **FN / LATE_INIT / TRACK_DROP** when
detections jitter or objects brake hard. Report both the IDS win and any
MOTA/FN regression — something always moves the wrong way.

## Before / after

Fill in after local remeasure:

| scene | MOTA before | IDS before | MOTA after | IDS after |
|-------|-------------|------------|------------|-----------|
| scene-0655 | -0.205 | 471 | | |
| scene-0916 | -0.291 | 384 | | |
| aggregate | | 890 ID_SWITCH events | | |
