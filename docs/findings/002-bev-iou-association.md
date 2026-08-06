# 002 — BEV IoU term for dense near-parallel association

## What the system surfaced

Finding [001](001-dense-id-switch-velocity-gate.md) cut aggregate `ID_SWITCH`
890 → 618 with soft lateral velocity cost + tighter gate + birth score.
Residual switches remain concentrated on dense near-parallel traffic
(`scene-0655`, `scene-0916`), where same-class neighbors share similar
Mahalanobis distance and motion direction so velocity alone cannot
disambiguate.

## Hypothesis

Position + soft velocity still under-constrains association when two
vehicles travel side-by-side: both fall inside the gate with similar
longitudinal residuals. Adding a BEV oriented-box IoU term should prefer
the detection whose footprint overlaps the track’s last size/yaw, cutting
lateral ID swaps without a hard IoU reject (hard gates previously raised
FN/IDS).

Cost inside existing gates:

```
cost = mahalanobis_m2
     + vel_soft_penalty
     + iou_weight * (1 - bev_iou)
```

`iou_weight` default `2.0` (`core/config/default.json`). Track `l`/`w`
copied from detection at birth/update; class defaults (vehicle 4.5×1.8,
pedestrian 0.8×0.6, bike/moto 1.8×0.6) when missing.

## Change that shipped

1. `bev_oriented_iou` (oriented rectangle polygon IoU) in association.
2. Soft `(1 - IoU)` cost term gated by `iou_weight`.
3. Optional `Track::l` / `Track::w` persisted from detections.
4. Unit tests: identical IoU=1, separated IoU=0, association prefers
   high-IoU neighbor at similar Euclidean distance.

Code: `core/src/association.cpp`, `core/include/trackbench/association.hpp`,
`core/include/trackbench/types.hpp`, `core/src/track.cpp`, `core/src/ekf.cpp`,
`core/config/default.json`.

## Before / after (10-scene mini — fill after remeasure)

### Aggregate failure counts

| kind | before (post-001) | after | Δ |
|------|-------------------|-------|---|
| `ID_SWITCH` | 618 | | |
| `GHOST_TRACK` | 228 | | |
| `LATE_INIT` | 393 | | |
| `TRACK_DROP` | 58 | | |
| `POS_ERROR_SPIKE` | 78 | | |
| `TRACK_DEATH` | 25 | | |

### Per-scene CLEAR MOT (headline scenes)

| scene | MOTA before | IDS before | MOTA after | IDS after |
|-------|-------------|------------|------------|-----------|
| scene-0655 | -0.142 | 326 | | |
| scene-0916 | -0.204 | 287 | | |

## Remeasure

```bash
# After merge / rebuild of trackbench_run on mini JSONL:
./scripts/eval_all_scenes.sh
# or per-scene mine + aggregate ID_SWITCH from failure digests
PYTHONPATH=. python -m eval.write_run --mine --notes "finding 002 BEV IoU"
```

Compare aggregate miner counts and scene-0655 / scene-0916 IDS against the
post-001 table above. Fill before/after once numbers are in.

## What I'd do next

1. Class-specific `iou_weight` / coast / process noise.
2. Tune `min_birth_score` per class; revisit `gate_m` on high-speed scenes.
3. If IoU helps but IDS plateau, consider appearance or longer coast with
   stronger motion priors.
