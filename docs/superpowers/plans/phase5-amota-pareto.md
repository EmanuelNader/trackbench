# Phase 5: AMOTA + Accuracy-vs-Latency Pareto Chart

> STATUS: DONE — merged to main via PR #11 (commits 3b4a1a7, 1e9129e, 57c6c0a,
> 7fc548f, 02db85b). Final whole-branch review: Ready to merge (0C/0I/3M).
>
> Housekeeping handoff (deferred minors, all triaged SHIP):
> - `ablate_amota.py` `--only` crashes on partial out-root (line ~198); and a
>   `relative_to` crash on out-of-repo `--out-root` (line 137). Dev-tooling only.
> - `amotp` not range-checked in ablate_amota.py.
> - Finding 004 wording nits (RESULTS.md:152 unqualified "+26%", finding:51/106).
> - `bench/pareto.py`: best-ring data-driven (not manifest alias `current`);
>   provenance footer uses HEAD commit date + parent-SHA on regen at new HEAD.
> - Task 1: emitted `l/w` are last-associated, not literal birth-box (documented).
> - Next plan: Phase 6 (fp32/fp16 precision sweep + determinism audit); also
>   consider committing docs/superpowers/plans/ and fixing the `.env` detections
>   file note.

## Why

Phase 4 decomposed the IDS win per component. But MOTA/IDS is the legacy CLEAR
metric. The metric that actually ranks trackers on nuScenes is **AMOTA** — a
recall-thresholded variant of MOTA that penalizes trackers which hide failures
by emitting only high-confidence tracks. Two gaps:

1. **Metric gap:** we cannot compare against any published tracker because we
   only report MOTA/IDS. AMOTA answers "how does the tracker do as you raise
   the confidence bar?" — it rewards high-recall, low-error trackers.
2. **Trade-off gap:** the perf work and the accuracy work have never been shown
   on the same chart. The Pareto chart makes the accuracy-vs-latency trade-off
   across the 24 ablation cells visible and machine-generated.

## Decisions (already made — do not re-litigate)

- **Self-implemented AMOTA in stdlib + numpy** (user-approved). The official
  nuscenes-devkit TrackingEvaluation pulls `motmetrics`, `sklearn`, `pandas`,
  `tqdm` and ties evaluation to official splits. Our eval stack stays
  `stdlib + numpy` (requirements.lock is untouched). The definition below is
  taken line-by-line from the installed devkit
  (`nuscenes/eval/tracking/{algo,metrics,data_classes,evaluate}.py`).
- **Ego frame throughout.** The devkit's center-distance matching uses
  `translation[:2]` (XY plane only, `algo.py:264-266`); XY distance is invariant
  under the ego↔global rigid transform, so AMOTA is computed in ego frame,
  exactly like our MOTA. No global-frame conversion.
- **`tracking_score` = birth detection's score**, constant over the track's life
  (the devkit averages per-frame scores; a constant makes that a no-op). It is
  the same value the birth gate (`min_birth_score`) already thresholds on.
- **Official config values:** `dist_th_tp = 2.0 m`, `min_recall = 0.1`,
  `num_thresholds = 40` recall slots (`linspace(0.1, 1.0, 40)`), `alpha = 1.0`,
  AMOTA worst (unachieved-threshold) value `0.0`, AMOTP worst `2.0`.
  `max_boxes_per_sample = 500` is irrelevant at our density. `class_range`
  filtering (car 50 m / ped 40 m) is **OFF** to match our existing MOTA eval —
  documented as a configurable divergence from the devkit.

## The AMOTA definition (verbatim from the devkit — the implementer MUST match this)

For each class (bicycle, bus, car, motorcycle, pedestrian, trailer, truck),
pooling GT + predicted tracks across all frames of all scenes in the eval set:

1. **Threshold inference** (`algo.py:compute_thresholds`):
   - Run per-frame matching with **no score threshold**; collect the `tracking_score`
     of every TP match.
   - Sort scores descending; `rec = [1..len(scores)] / gt_box_count` where
     `gt_box_count` = total class GT boxes (all frames, all scenes).
   - Recall grid `rec_interp = linspace(0.1, 1.0, 40).round(12)`; thresholds =
     `np.interp(rec_interp, rec, scores, right=0)`; set `nan` where
     `rec_interp > max_recall_achieved` (penalizes unachieved recall).
   - Reverse both arrays (presentation order).
2. **Per-threshold matching** (`algo.py:accumulate_threshold`): for each unique
   non-nan threshold, filter predicted tracks to `score >= threshold`, re-run
   per-frame matching, accumulate TP/FP/FN/IDS. (Frames with no GT and no pred
   are skipped; frame ids are unique across scenes; matching is per-frame
   Hungarian on XY center distance, `distance >= 2.0` → no match.)
3. **MOTAR** (`metrics.py:motar`, `alpha = 1.0`):
   `recall = TP / gt_box_count`;
   `MOTAR = max(0, 1 - (FN + IDS + FP - (1-recall)*gt_box_count) / (recall*gt_box_count))`.
   MOTP per threshold = mean XY center distance of TPs (nan if no TP).
4. **AMOTA** (`evaluate.py:180-193`): array of MOTAR over the 40 recall slots
   (duplicate a threshold's value for each slot it covers; unachieved slots are
   `nan`). If all slots nan → per-class AMOTA = nan (class absent). Else fill
   nan with worst (`amota` worst 0.0, `amotp` worst 2.0) and
   **`AMOTA = mean` over the 40 slots**.
5. **Aggregate** (`data_classes.py:compute_metric`): per metric,
   `class_name == 'all'` = `nanmean` over classes (sums for fp/fn/ids/etc.).
6. Determinism: fixed iteration order, no RNG, no tqdm; every number from real
   per-frame matches.

## Key facts for the implementer

- `Detection` (core/include/trackbench/types.hpp) already carries
  `z, l, w, h, score`; the synthetic fixture detections include them. The
  `Track` struct does NOT store them yet — Task 1 threads them from the birth
  detection.
- `core/tests/test_golden.cpp` does a **byte-for-byte** comparison of track
  output vs `data/fixtures/synthetic_scene_001/tracks_expected.jsonl` — adding
  output fields requires regenerating that fixture file.
- The eval stack reads tracks by field, so extra JSON fields are backward-safe.
- Every cell dir has `scene-*_timing.json` with `ms_per_frame` (per-frame ms) —
  the Pareto x-axis (pooled p99 per cell) is already available. No re-run
  needed for latency.
- `bench/ablation/summarize.py` has a machine-enforced landmark gate
  (890/618/619/415 ±20, non-zero exit). Re-running the grid with the new binary
  MUST reproduce those numbers (score/box fields must not change state).
- The 7 classes must match the tracker's class vocabulary (the ingest already
  filters/merges Megvii classes into exactly these).

## Tasks

### Task 1: C++ Track carries score + 3D box
- `Track` gains `score, z, l, w, h`. `score, z, h` are set at birth from the
  birth detection and constant for the track's life. `l, w` already existed as
  association-updated track state (finding-002 IoU cost); the emitter reports
  their current (last-associated) values, which on all real runs equal the birth
  values. This is passive metadata — AMOTA matches on XY center distance only,
  so `l/w/h/z` never affect the metric. Emit all five in `write_tracks_jsonl`.
- Regenerate `data/fixtures/synthetic_scene_001/tracks_expected.jsonl` with the
  new binary (deterministic). `core` ctest + the CI eval-gate must stay green.
- Commit: `feat(core): tracks carry score + 3D box (z/l/w/h) from birth detection`

### Task 2: eval/amota.py — the metric
- New module implementing the definition above, reusing `eval/metrics.py`'s
  per-frame matcher (or its own copy if metrics.py is scene-local). Pure
  stdlib+numpy. Input: list of scenes, each = (gt frames, track frames) +
  class set. Output: per-class + 'all' AMOTA/AMOTP (+ motar recall curve).
- Unit tests (tests/): tiny hand-verified cases — perfect tracker → AMOTA≈1;
  score-hiding trackers (high MOTA, low recall) score worse on AMOTA than MOTA;
  no-GT class → nan, excluded from 'all'; unachieved recall → worst-filled.
- Commit: `feat(eval): nuScenes AMOTA/AMOTP (recall-curve MOTAR, stdlib+numpy)`

### Task 3: Per-cell AMOTA on the 24-cell grid
- Re-run `scripts/ablate.py` with the new binary (24 × 10). Verify the landmark
  gate reproduces (890/618/619/415) and MOTA/IDS per cell are unchanged.
- New `scripts/ablate_amota.py`: for each cell, pool the 10 scenes' tracks vs
  GT, run eval/amota.py, write `bench/ablation/out/<cell>/amota.json`
  (per-class + 'all' AMOTA/AMOTP).
- Commit: `bench: per-cell AMOTA across the 24-cell grid (landmarks hold, MOTA/IDS unchanged)`

### Task 4: Pareto chart
- New `bench/pareto.py` (stdlib-only SVG emitter): one dot per cell,
  x = pooled p99 per-frame latency (ms), y = selectable accuracy (AMOTA,
  MOTA, or IDS), the 4 reference configs labeled, baseline/current
  highlighted, axis units + provenance footer. Outputs
  `bench/ablation/pareto.svg` + `bench/ablation/pareto.md` (table).
- Deterministic: same inputs → byte-identical SVG/md.
- Commit: `bench: accuracy-vs-latency Pareto chart (MOTA/IDS/AMOTA vs p99)`

### Task 5: Findings + close-out
- Findings writeup in `docs/findings/`: does AMOTA rank the 24 cells the same
  way MOTA/IDS do? Expected honest outcome: the birth-score raises (−100,
  −204 on IDS) also raise AMOTA, but the *magnitude* differs — AMOTA penalizes
  the recall loss from high birth scores. State it as measured.
- Append the AMOTA table + Pareto chart reference to `bench/ablation/RESULTS.md`
  (via the §Analysis-preserve pattern or a generated section).
- Final whole-branch review + PR.

## Out of scope

- nuscenes-devkit validation run (needs the heavy dep tree) — documented
  divergence, not a blocker.
- 3D IoU / class-range matching; AMOTA uses XY center distance only.
- Other classes beyond the 7; other splits (full nuScenes) — separate plan.
- Changing tracker state semantics — the score/box fields are passive.

## Risks / notes

- **Golden fixture regeneration must be a no-op for state**: the ONLY changed
  bytes in `tracks_expected.jsonl` are the added fields. If the diff shows
  changed x/y/id/etc., STOP (state bug) and fix.
- **Matcher parity**: our per-frame matcher must equal motmetrics' per-frame
  behavior (min-cost Hungarian + `>= dist_th` no-match). Reuse the matcher that
  already backs our CLEAR MOTA/IDS so MOTA-from-AMOTA-path is consistent.
- **p99 pooling**: latency = pooled p99 across all frames of all 10 scenes per
  cell; hardware variance noted in the chart footer, not erased.
- Task 3 re-runs the grid — compute is minutes, not hours; do it once with the
  new binary and commit only aggregate outputs (amota.json), never re-commit the
  tracks.jsonl.

## Gate (binding)

- Landmark gate reproduced exactly (Δ=0) after the C++ change; MOTA/IDS per cell
  unchanged.
- AMOTA numbers are machine-generated from real per-frame matches; no hand-typed
  metric.
- eval stack deps unchanged (`pip install` of nothing; requirements.lock
  untouched).
- No `*.jsonl` track files committed in the grid re-run.
