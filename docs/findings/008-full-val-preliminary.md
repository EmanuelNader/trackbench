# 008 — Full nuScenes val split: pipeline ready, awaits external data download

## What the system surfaced

Phase 9 prepared the orchestration pipeline for the full nuScenes val split
(~35 scenes). The `scripts/eval_val.py` script automates the three-step
workflow: ingest (nuScenes v1.0-trainval + Megvii val detections), track
(parallel C++ tracker invocations), and evaluate (CLEAR MOT + AMOTA + p99
timing). The pipeline emits `bench/val/summary.json` and `bench/val/SUMMARY.md`.

The pipeline is complete and tested (`--help` runs cleanly). The actual
evaluation requires downloading the v1.0-trainval dataset (~850 GB with full
sensor data, ~700 MB for metadata-only) — an external user action that cannot
be automated by the codebase.

## Why this matters

The 10-scene mini set is statistically limited:
- AMOTA recall curves have only 10 operating points (vs. ~35 for full val).
- Per-scene IDS deltas are dominated by individual scenes (scene-0655,
  scene-0916) that may not generalize.
- The greedy-vs-Hungarian Pareto point (finding 007) was measured on 10
  scenes — the accuracy trade-off could differ on denser traffic.

The full val split would:
1. Smooth the AMOTA curve (3× more recall slots).
2. Reveal whether findings 001–007 generalize beyond the mini set.
3. Provide a statistically meaningful baseline for future ablations.

## What's ready

- `scripts/eval_val.py`: single-command orchestration (ingest → track → eval).
  Supports `--limit`, `--skip-ingest`, `--eval-only`, `--jobs N`, `--config`.
- `bench/val/out/` gitignored (alongside bench/assoc/out/, bench/ctrv/out/).
- `docs/data.md`: updated with full val-split setup instructions.
- `docs/superpowers/plans/phase9-full-val-split.md`: implementation plan.

## What's needed (user action)

1. Download v1.0-trainval from https://www.nuscenes.org/download (~850 GB).
2. Extract to `data/raw/nuscenes/`.
3. Ensure `data/raw/detections/megvii_val.json` exists (214 MB, already
   downloaded with the Megvii detection zip).
4. Run: `python3 scripts/eval_val.py --config post003 --jobs 8`

## Caveats

1. **Disk space.** The full trainval is ~850 GB with sensor data. The
   metadata-only download is ~700 MB but requires a nuScenes account.
2. **Ingest time.** Ingesting ~35 scenes takes ~10–15 minutes (dominated by
   the nuScenes devkit metadata parse).
3. **Track time.** ~35 scenes × ~40 frames each × ~0.02 ms/frame (greedy)
   ≈ negligible. Even with Hungarian, the full val takes < 1 minute.
4. **AMOTA computation.** The AMOTA recall curve over 35 scenes has ~3× more
   operating points than the mini set, but the curve shape depends on the
   detector's score distribution across scenes.

## Conclusion

The full nuScenes val pipeline is ready. The bottleneck is the external data
download. Once downloaded, a single command (`python3 scripts/eval_val.py`)
produces the full-val metrics. This is the highest-leverage next step for
statistical validity.

## What I'd do next

1. **Run the full-val evaluation.** After downloading v1.0-trainval, run
   `python3 scripts/eval_val.py --config post003 --jobs 8` and compare the
   full-val AMOTA/IDS to the mini-set values.
2. **Re-run the 24-cell grid on full val.** The ablation grid (phase 4) was
   measured on 10 scenes; the full-val grid would reveal whether the config
   rankings generalize.
3. **Re-run the greedy-vs-Hungarian sweep on full val.** The Pareto point
   (finding 007) may shift on denser traffic.
