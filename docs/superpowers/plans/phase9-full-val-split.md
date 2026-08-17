# Phase 9 — Full nuScenes val split

## Why

The current 10-scene mini set (v1.0-mini) is statistically limited — per-scene
IDS deltas are dominated by individual scenes (scene-0655, scene-0916) and the
AMOTA recall curve is computed over only 10 operating points. The full nuScenes
val split (~35 scenes) would dramatically increase statistical power, smooth
the AMOTA curve, and reveal whether the findings from the mini set generalize.

The Megvii detection files already cover the full val set (`megvii_val.json`,
214 MB); the ingest script already supports `--version v1.0-trainval` and
`--detections-json`; the C++ tracker processes scenes independently
(embarrassingly parallel). The bottleneck is the external data download
(~700 MB metadata-only, ~850 GB with full sensor data) — which is a user
action, not a code change.

This phase prepares everything downstream of the download: an orchestration
script that ingests the val split, runs the tracker on all val scenes, and
computes the full-val metrics.

## Decisions

- **Orchestration script** (`scripts/eval_val.py`): single command that
  (a) ingests all val scenes into `data/normalized/`, (b) runs the tracker
  on each scene with the post003 config, (c) evaluates with CLEAR MOT +
  AMOTA, (d) emits `bench/val/summary.json` + `bench/val/SUMMARY.md`.
- **Config:** post003 (the current best) for the initial val run. The script
  accepts `--config` to rerun with any reference config.
- **Parallelism:** `--jobs N` for parallel tracker invocations (default: 4).
- **Output:** `bench/val/` (new directory, gitignored alongside bench/assoc/out/).
- **No changes to the C++ tracker, EKF, or eval scripts.** The pipeline is
  already scene-agnostic.

## Files to touch

- `scripts/eval_val.py` (new): orchestration script for the full val pipeline.
- `.gitignore`: add `bench/val/out/`.
- `docs/data.md`: add a "Full val split" section explaining the download +
  ingest + eval workflow.

## Tasks

### Task 1: Orchestration script
- Implement: `scripts/eval_val.py` — ingest, track, evaluate, aggregate.
- Gate: `python3 scripts/eval_val.py --help` works; dry-run with `--limit 1`
  (requires v1.0-trainval data).
- Commit: `feat(scripts): full nuScenes val orchestration (eval_val.py)`

### Task 2: Documentation and gitignore
- Update `docs/data.md` with val-split setup instructions.
- Add `bench/val/out/` to `.gitignore`.
- Commit: `docs: val split setup guide; gitignore bench/val/out/`

### Task 3: Finding 008 (placeholder)
- `docs/findings/008-full-val-preliminary.md`: documents the val-split
  preparation and notes that results require the external data download.
- Commit: `docs: finding 008 (full val split preparation)`

## Out of scope

- Actually downloading the data (user action).
- Running the full 24-cell grid on val (too expensive for initial validation).
- Phase 10 (triage UI).

## Gate

Script runs cleanly with `--help`. No committed data/normalized changes.
bench/val/out/ gitignored.
