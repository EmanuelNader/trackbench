# Phase 7 — CTRRV Motion Model (constant-turn-rate-and-velocity)

> STATUS: DONE — merged via PR #14 (commits 53ca836, 0382e2f, 06199c8).
> Result in `docs/findings/006` and `bench/ctrv/sweep.{json,md}`: CTRRV is a
> null on IDS/MOTA (+88 to +129 IDS, −0.10 to −0.27 MOTA); one AMOTA
> trade-off on the baseline (+0.04 recall-curve gain). The `motion_model`
> knob ("cv" default, "ctrv" option) lives in `TrackerConfig`; `default.json`
> unchanged; 24-cell grid untouched.

## Why

The current EKF is a constant-velocity (CV) model: state `[x, y, vx, vy, yaw]`,
linear predict, yaw not part of the motion. On curvy urban scenes (nuScenes mini
scenes 0655/0916, where the dense ID-switch clusters live), CV cannot track
turning objects — the predicted position diverges from the turning target, the
Hungarian matcher assigns a fresh track, and identity switches accumulate. A
constant-turn-rate-and-velocity (CTRV) model predicts the yaw rate and uses it
in the position prediction — the standard fix in tracking for road scenes.

This phase tests, with numbers, whether CTRRV actually helps on this 10-scene
split. The null result is as valuable as a positive one.

## Decisions

- **Config-driven toggle**: `TrackerConfig.motion_model` (`"cv"` default,
  `"ctrv"` option). Loader tolerates missing keys (existing `extract_*` functions
  return false and leave defaults untouched), so **default.json is NOT modified**,
  **no committed cell config.json is touched**, and **the 24-cell grid is fully
  unchanged**. CTRV is activated only via ad-hoc experiment configs.
- **No output-schema change in CV mode**: all bytes identical. CTRV mode emits
  the same JSONL fields (vx, vy derived as `v*cos(yaw), v*sin(yaw)`);
  internal yaw-rate is not emitted.
- **Track gains `yaw_rate` (double, not emitted)**: in CV mode it stays 0; in
  CTRV mode it is the filtered turn rate. Track struct grows by one `double`
  (unused bytes in CV mode, harmless).
- **Binding gate**: `make core` default (CV) → golden byte-compare, post003
  re-run, summarize byte-identity, 24-cell grid landmarks all hold. Zero
  committed output bytes change.

## CTRRV state and predict

State: `[x, y, yaw, v, ω]` (5-dim, same kStateDim as CV — Track::P stays 5×5,
cov_trace from 5×5; no layout change).

Output derived from internal state:
`vx = v * cos(yaw)`, `vy = v * sin(yaw)`.

Predict (nonlinear):
```
ω_dt = ω * dt
if |ω_dt| < ε  (small yaw rate → CV limit):
  x'  = x + v * cos(yaw) * dt
  y'  = y + v * sin(yaw) * dt
  yaw' = yaw
else:
  x'  = x + (v/ω) * (sin(yaw + ω_dt) - sin(yaw))
  y'  = y + (v/ω) * (-cos(yaw + ω_dt) + cos(yaw))
  yaw' = yaw + ω_dt
v'  = v
ω'  = ω
```
Jacobian F (5×5) is standard CTRV (transcribed from Thrun, Fox, Burgard or
the nuScenes-devkit CTRV reference). The ε threshold: `1e-6` (below this the
taylor-series first-order limit is exact to double precision).

Process noise Q: 3×3 on `[x, y, yaw, v, ω]` with noise parameters:
- `process_var_pos` → x, y (same as CV)
- `process_var_vel` → v
- `process_var_yaw` → yaw
- `process_var_yawrate` → ω (new optional config key, default 0.1)

Update: H measures `[x, y, yaw]` — identical to CV (measurement model unchanged).

## Files to touch

- `core/include/trackbench/types.hpp` (95-118): add `motion_model = "cv"`,
  `process_var_yawrate = 0.1` to TrackerConfig; add `yaw_rate = 0.0` to Track
  (after `score`, before `state`).
- `core/src/io.cpp` (252-278): add `extract_string(body, "motion_model", cfg.motion_model)`
  and `extract_number(body, "process_var_yawrate", cfg.process_var_yawrate)`.
- `core/src/ekf.cpp` (19-43 predict): branch on `config_.motion_model`.
  CV path = current code verbatim; CTRRV path = nonlinear predict with Jacobian.
- `core/src/track.cpp`: `refresh_cov_trace` unchanged (5×5 P.trace());
  `make_track_from_detection` sets `yaw_rate = 0.0`.
- `core/include/trackbench/ekf.hpp`: no interface change (predict/update
  signatures unchanged; CTRRV is internal to predict).
- `core/tests/test_ekf.cpp` (new): CTRRV predict unit tests.
- `core/config/default.json`: unchanged.

## Tasks

### Task 1: CTRRV EKF (core)
- Implement: TrackerConfig fields, extract_* calls, CTRRV predict, Track.yaw_rate,
  unit tests (straight-line ≈ CV, constant ω circle, ω≈0 guard, Jacobian
  finite-difference check, determinism).
- **Gate (binding)**: `make core-test` golden + all existing tests pass; `make
  core` then post003 re-run → eval/summary/amota byte-identical (only timing
  drift); summarize.py exit 0 byte-identity. CV mode is untouched.
- Verify one CTRV scene runs end-to-end: `./core/build/trackbench_run --dets
  data/normalized/scene-0655/detections.jsonl --config
  bench/ctrv/ctrv_reference.json --out /tmp/ctrv.jsonl --timing /tmp/ctrv_t.json`
  exits 0.
- Commit: `feat(core): CTRRV motion model (config toggle, CV default byte-identical)`

### Task 2: CTRRV experiment
- `bench/ctrv/ctrv_reference.json`: ad-hoc config (CV defaults + motion_model
  "ctrv" + process_var_yawrate 0.1).
- `scripts/ablate_ctrv.py`: run reference cells + AMOTA-best cell (5 configs)
  under CV and CTRV on the 10 scenes; compute MOTA/IDS/AMOTA/AMOTP via
  eval.metrics + eval.amota; pooled p99; determinism audit; write
  `bench/ctrv/sweep.json` + `bench/ctrv/SWEEP.md`.
  Deterministic modulo provenance.ts.
- Verify: determinism 10/10 PASS; CTRRV vs CV deltas; honest result either way.
- Commit: `bench: CTRRV vs CV across reference cells (motion-model ablation)`

### Task 3: Finding 006
- `docs/findings/006-ctrv-motion-model.md` (001-005 format): honest measurement
  story (CTRRV helps on curvy scenes or doesn't, with per-scene evidence);
  config knob documented; null or positive finding stated plainly; fp16/double
  caveats from 005 not re-litigated.
- Commit: `docs: motion-model finding 006 (CTRV vs CV)`

## Out of scope

- Greedy/JV association (separate feature), full nuScenes val, UI wiring, any
  change to the 24-cell grid, ablate.py, summarize.py, eval scripts, or
  committed cell outputs. Changing the CV path's behavior.

## Gate

Default (CV) byte-identical (golden + post003 + summarize). CTRV configs are
ad-hoc and not committed to the grid. Sweep numbers machine-derived; no
hand-edited metrics; zero committed `.jsonl`.
