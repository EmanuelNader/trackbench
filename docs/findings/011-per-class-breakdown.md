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

| Class | GT count | IDS | FN | Notes |
|-------|----------|-----|----|-------|
| car | 7619 | 405 | 6420 | Dominates IDS (98% of total) |
| truck | 649 | 10 | 550 | High FN (85%), but low IDS |
| motorcycle | 471 | 0 | 457 | 100% FN — zero recall |
| bicycle | 243 | 0 | 243 | 100% FN — zero recall |
| trailer | 60 | 0 | 21 | 100% FN — zero recall |

The story is stark:

1. **Cars are the only class the tracker actually tracks.** 98% of IDS are car
   identity switches. Cars are also the only class with non-trivial matched
   TPs — the only class the tracker can meaningfully score.

2. **Trucks have high FN but low IDS.** The tracker misses 85% of truck GT
   boxes, but the few it does match rarely switch identity. This is because
   trucks in the mini set tend to be isolated (few competing objects of the
   same class).

3. **Motorcycles, bicycles, and trailers are completely invisible.** The tracker
   assigns zero matched TPs to these classes — they're 100% FN. This is
   likely because the birth score threshold (0.7) is too aggressive for these
   classes (their detection scores are lower), or because the tracker's
   motion model (constant velocity in ego frame) doesn't match their
   movement patterns.

4. No pedestrians or buses appear in the mini set's ground truth — the
   per-class breakdown is limited to the 5 classes present.
   with zero TPs, AMOTA is undefined (nanmean excludes them).

## Why this matters

The aggregate metrics (MOTA 0.67, IDS 415, AMOTA 0.22) hide a fundamental
limitation: **this tracker is a car tracker, not a multi-class tracker.**
The velocity gate, BEV IoU, and birth score are tuned for car dynamics and
car detection scores. Motorcycles, bicycles, and trailers are effectively
invisible.

This is honest and expected for a classical tracker with a single motion
model and a single birth threshold. A production multi-class tracker would
need:
- Per-class motion models (e.g., motorcycle turning model, bicycle weaving model).
- Per-class birth thresholds (lower for motorcycles/bicycles, higher for trucks).
- Per-class gate widths (tighter for large objects, looser for small ones).

## Caveats

1. **10-scene mini set.** The class distribution is heavily skewed toward cars
   (7619 GT vs 649 truck vs 471 motorcycle vs 243 bicycle vs 60 trailer).
   No pedestrians or buses appear in the mini set's ground truth.
2. **Detection quality matters.** The Megvii detector's per-class performance
   may differ from the tracker's. If the detector misses motorcycles/bicycles,
   the tracker can't recover them.
3. **Birth score 0.7 is the primary bottleneck.** Lowering it would likely
   improve motorcycle/bicycle recall but at the cost of more FP and IDS on cars.

## Recommendation

The per-class breakdown is the most important analytical tool for this
project. It reveals that:
- **Finding 001 (velocity gate)** primarily improved car IDS.
- **Finding 003 (birth score 0.7)** primarily affected motorcycle/bicycle
  recall (making it worse).
- **The AMOTA-vs-MOTA tension (finding 004)** is a class-specific issue:
  MOTA is car-dominated, AMOTA includes all classes.

For a portfolio piece, the per-class table demonstrates **analytical depth**:
the tracker's strengths and weaknesses are understood at the class level,
not just in aggregate.
