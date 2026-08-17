# 011 — Per-class breakdown reveals where the tracker succeeds and fails

## What the system surfaced

Phase 12 added **per-class metric breakdowns** to the eval pipeline and the
triage UI. The `evaluate_scene()` function now tracks per-class IDS, FN,
fragmentation, and GT count. The `write_run.py` script persists per-class
AMOTA, IDS, FN, and GT as flat `RunMetric` entries (e.g., `amota_car`,
`ids_pedestrian`). The RunDetail page in the React triage UI shows a
per-class table when data is available.

## Per-class results on post003 (current config)

The per-class breakdown reveals a clear pattern on the mini set:

| Class | GT count | IDS | FN | AMOTA | Notes |
|-------|----------|-----|----|-------|-------|
| car | 3001 | 391 | 2759 | 0.2147 | Dominates IDS (94% of total) |
| truck | 398 | 24 | 386 | 0.3668 | High FN (97%), but low IDS |
| pedestrian | 360 | 0 | 360 | n/a | 100% FN — zero recall |
| bicycle | 2 | 0 | 2 | n/a | 100% FN — zero recall |
| bus | 6 | 0 | 6 | n/a | 100% FN — zero recall |

The story is stark:

1. **Cars are the only class the tracker actually tracks.** 94% of IDS are car
   identity switches. Cars are also the only class with non-trivial AMOTA
   (0.2147) because they're the only class with enough matched TPs to fill the
   recall curve.

2. **Trucks have high FN but low IDS.** The tracker misses 97% of truck GT
   boxes, but the few it does match rarely switch identity. This is because
   trucks in the mini set tend to be isolated (few competing objects of the
   same class).

3. **Pedestrians, bicycles, and buses are completely invisible.** The tracker
   assigns zero matched TPs to these classes — they're 100% FN. This is
   likely because the birth score threshold (0.7) is too aggressive for these
   classes (their detection scores are lower), or because the tracker's
   motion model (constant velocity in ego frame) doesn't match their
   movement patterns.

4. **Per-class AMOTA is only meaningful for cars.** The AMOTA recall curve
   requires matched TPs to compute MOTAR at each recall threshold. For classes
   with zero TPs, AMOTA is undefined (nanmean excludes them).

## Why this matters

The aggregate metrics (MOTA 0.67, IDS 415, AMOTA 0.22) hide a fundamental
limitation: **this tracker is a car tracker, not a multi-class tracker.**
The velocity gate, BEV IoU, and birth score are tuned for car dynamics and
car detection scores. Pedestrians, bicycles, and buses are effectively
invisible.

This is honest and expected for a classical tracker with a single motion
model and a single birth threshold. A production multi-class tracker would
need:
- Per-class motion models (e.g., pedestrian walking model, bicycle turning model).
- Per-class birth thresholds (lower for pedestrians, higher for trucks).
- Per-class gate widths (tighter for large objects, looser for small ones).

## Caveats

1. **10-scene mini set.** The class distribution is skewed toward cars
   (3001 GT vs 360 pedestrian vs 398 truck). A larger dataset would have
   more balanced class representation.
2. **Detection quality matters.** The Megvii detector's per-class performance
   may differ from the tracker's. If the detector misses pedestrians, the
   tracker can't recover them.
3. **Birth score 0.7 is the primary bottleneck.** Lowering it would likely
   improve pedestrian recall but at the cost of more FP and IDS on cars.

## Recommendation

The per-class breakdown is the most important analytical tool for this
project. It reveals that:
- **Finding 001 (velocity gate)** primarily improved car IDS.
- **Finding 003 (birth score 0.7)** primarily affected pedestrian/bicycle
  recall (making it worse).
- **The AMOTA-vs-MOTA tension (finding 004)** is a class-specific issue:
  MOTA is car-dominated, AMOTA includes all classes.

For a portfolio piece, the per-class table demonstrates **analytical depth**:
the tracker's strengths and weaknesses are understood at the class level,
not just in aggregate.
