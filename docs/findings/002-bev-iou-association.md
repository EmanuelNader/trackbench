# 002 — BEV IoU term for dense near-parallel association

## What the system surfaced

Finding [001](001-dense-id-switch-velocity-gate.md) cut aggregate CLEAR-MOT
IDS ~618 with soft lateral velocity cost + tighter gate + birth score.
Residual switches remained on dense near-parallel traffic (`scene-0655`,
`scene-0916`).

## Hypothesis

Position + soft velocity under-constrains association when two vehicles
travel side-by-side. A BEV oriented-box IoU term should prefer the detection
whose footprint overlaps the track box.

Cost inside existing gates:

```
cost = mahalanobis_m2
     + vel_soft_penalty
     + iou_weight * (1 - bev_iou)
```

`iou_weight` default `2.0`.

## Change that shipped

1. Oriented BEV IoU helper in association.
2. Soft `(1 - IoU)` cost term.
3. `Track::l` / `Track::w` from detections (class defaults if missing).
4. Unit tests for IoU + preference under equal distance.

## Before / after (10-scene mini)

### CLEAR MOT IDS (sum across scenes)

| | post-001 | post-002 (IoU) | Δ |
|--|----------|----------------|---|
| Total IDS | 618 | **619** | **+1 (≈ no change)** |
| scene-0655 IDS | 326 | 327 | +1 |
| scene-0916 IDS | 287 | 287 | 0 |

### Per-scene after IoU

| scene | MOTA | IDS | n_failures |
|-------|------|-----|------------|
| scene-0061 | 0.079 | 0 | 31 |
| scene-0103 | -0.004 | 0 | 94 |
| scene-0553 | -0.005 | 0 | 33 |
| scene-0655 | -0.140 | 327 | 526 |
| scene-0757 | 0.162 | 1 | 27 |
| scene-0796 | 0.102 | 0 | 38 |
| scene-0916 | -0.200 | 287 | 498 |
| scene-1077 | 0.048 | 0 | 55 |
| scene-1094 | -0.057 | 3 | 57 |
| scene-1100 | -0.267 | 1 | 40 |

## Conclusion

**Null result on the metric we cared about.** Soft BEV IoU at `iou_weight=2.0`
did not reduce dense-scene IDS versus post-001. Likely causes:

1. Same-class neighbors in 0655/0916 already have similar overlap once inside
   the 1.5 m gate, so `(1 - IoU)` does not reorder Hungarian enough.
2. Residual switches may be driven more by **birth/death churn** and FN
   recovery than by parallel-box ambiguity.
3. Weight may be too weak relative to Mahalanobis — worth a higher
   `iou_weight` ablation, but not the default without evidence.

Shipping the code + tests is still useful (correct IoU helper, size on
tracks). We do **not** claim an IDS win in the README metrics table.

## What I'd do next

1. ~~Harder birth~~ — done in [003](003-harder-birth-score.md); **IDS 619 → 415**.
2. Per-class birth/coast — pedestrians vs cars (LATE_INIT / FN residual).
3. Optional IoU weight ablation on 0655/0916 only (not default without evidence).
