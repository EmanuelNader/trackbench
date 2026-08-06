# Design decisions

Recorded at M0. Rationale is public-source only.

## D1 — Detection source: Megvii (CBGS)

**Choice:** Consume Megvii / CBGS published detections from the official nuScenes tracking baselines.

**Cite:** Zhu et al., “Class-balanced Grouping and Sampling for Point Cloud 3D Object Detection,” arXiv:1908.09492. Hosted at https://www.nuscenes.org/data/detection-megvii.zip (documented in [nuscenes-devkit tracking README](https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/eval/tracking/README.md#baselines)).

**Why:** Official challenge baseline, public zip, same JSON schema as the detection submission format. Filter `sample_token`s to the mini split. Do not switch mid-project.

**Rejected:** CenterPoint prediction dumps (SharePoint links, less stable for CI); training our own detector (anti-goal).

## D2 — Association distance: Mahalanobis

**Choice:** Cost = Mahalanobis distance in position (`x`, `y`), gated by class match and a distance threshold.

**Why:** Natural fit for an EKF with covariance; standard in classical MOT (e.g. SORT / AB3DMOT lineage). Public alternative noted but deferred: 3D GIoU / BEV IoU costs.

## D3 — Tracker parameters: one global set

**Choice:** Start with a single parameter set for all classes.

**Why:** Small first. Per-class process noise / coast horizons are a natural M6 finding if clustering surfaces class-specific failure modes.

## D4 — Track in 2D BEV (no `z` in state)

**Choice:** State `[x, y, vx, vy, yaw]`. Measurement `[x, y, yaw]`. Matching uses 2D center distance on the ground plane.

**Why:** Matches the [nuScenes tracking convention](https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/eval/tracking/README.md) (2 m 2D center distance). Halves state complexity vs. full 3D.

## D5 — Interchange format: JSONL in ego frame

**Choice:** Per-scene `detections.jsonl` / `gt.jsonl` / `tracks.jsonl`. Coordinates in the **ego frame at the current timestamp**.

**Why:** Spec §4. Ego motion compensation in ingest, not the tracker. Official nuScenes detection/tracking JSON is global; we transform at ingest so the C++ hot path stays simple and deterministic.
