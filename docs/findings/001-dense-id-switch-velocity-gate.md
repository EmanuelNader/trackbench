# 001 — Dense-traffic ID switches from position-only association

## What the system surfaced

After ingesting nuScenes `v1.0-mini` with Megvii detections (train∪val),
filtering to the 7 tracking classes (score ≥ 0.3), running the CV-EKF
tracker, and mining failures across all 10 scenes:

| kind | count (pre-fix) |
|------|------------------|
| `ID_SWITCH` | **890** |
| `LATE_INIT` | 374 |
| `GHOST_TRACK` | 369 |
| `TRACK_DROP` | 92 |
| `POS_ERROR_SPIKE` | 91 |
| `TRACK_DEATH` | 23 |

Largest clusters: **`other_id_switch` / `dense_id_switch`** on
`scene-0655` and `scene-0916` (hundreds of events each).

## Hypothesis

1. **Position-only Mahalanobis cost** lets nearby same-class objects swap IDs
   when both fall inside the association gate.
2. **Every unmatched detection births a track**, so dense frames create many
   tentative hypotheses that steal associations on the next frame.

Public lineage: motion-consistency costs and score-gated birth are standard
refinements in classical MOT (SORT / AB3DMOT-style pipelines).

## Experiments

| attempt | result |
|---------|--------|
| Hard lateral/rear velocity **reject** | IDS **worse** (890 → 913). Good matches dropped → coast → rematch counted as switch. |
| Soft lateral velocity **cost** + `gate_m=1.5` + `min_birth_score=0.5` | **IDS 890 → 618 (−30%)**. Ghosts 369 → 228. |

## Change that shipped

1. Ingest keeps only nuScenes tracking classes + det score ≥ 0.3.
2. Association cost: `m2 + vel_cost_weight * (lat / vel_gate_lateral_m)^2`
   for tracks with `hits >= 2` and speed ≥ 1 m/s.
3. Euclidean gate `2.0 → 1.5` m.
4. Unmatched dets with `score < 0.5` do not birth tracks (can still update
   existing tracks if associated).

Code: `core/src/association.cpp`, `core/src/tracker.cpp`,
`core/config/default.json`, `ingest/nuscenes_ingest.py`.

## Before / after (10-scene mini, class-filtered GT/dets)

### Aggregate failure counts

| kind | before | after | Δ |
|------|--------|-------|---|
| `ID_SWITCH` | 890 | **618** | **−272** |
| `GHOST_TRACK` | 369 | 228 | −141 |
| `LATE_INIT` | 374 | 393 | +19 |
| `TRACK_DROP` | 92 | 58 | −34 |
| `POS_ERROR_SPIKE` | 91 | 78 | −13 |
| `TRACK_DEATH` | 23 | 25 | +2 |

### Per-scene CLEAR MOT (headline scenes)

| scene | MOTA before | IDS before | MOTA after | IDS after |
|-------|-------------|------------|------------|-----------|
| scene-0655 | -0.205 | 471 | -0.142 | **326** |
| scene-0916 | -0.291 | 384 | -0.204 | **287** |
| scene-0061 | -0.144 | 8 | 0.079 | **0** |
| scene-1094 | -0.417 | 17 | -0.057 | **3** |

Full after table:

| scene | MOTA | IDS | FP | FN |
|-------|------|-----|----|----|
| scene-0061 | 0.079 | 0 | 34 | 548 |
| scene-0103 | -0.004 | 0 | 178 | 891 |
| scene-0553 | -0.005 | 0 | 201 | 589 |
| scene-0655 | -0.142 | 326 | 360 | 1425 |
| scene-0757 | 0.162 | 1 | 29 | 291 |
| scene-0796 | 0.102 | 0 | 2 | 465 |
| scene-0916 | -0.204 | 287 | 548 | 1499 |
| scene-1077 | 0.048 | 0 | 0 | 690 |
| scene-1094 | -0.057 | 3 | 144 | 556 |
| scene-1100 | -0.280 | 1 | 270 | 342 |

## What regressed

- **LATE_INIT +19** — higher birth score and tighter gate delay some starts.
- **FN still high** on dense scenes — simple CV tracker + 2 m matching still
  misses a lot; not the focus of this change.
- Absolute MOTA remains weak/negative on several scenes; the deliverable here
  is the **ID-switch reduction the miner pointed at**, not a leaderboard score.

## What I'd do next

1. ~~BEV IoU term~~ — tried in [002](002-bev-iou-association.md); **null** on IDS.
2. Harder / per-class birth (score + N-hit confirm) to cut ID churn on 0655/0916.
3. Class-specific coast / process noise (pedestrians vs cars); revisit `gate_m` on high-speed scenes.
