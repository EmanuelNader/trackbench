# Phase 6 — Precision Sweep (double vs float) + Determinism Audit

> STATUS: DONE — merged via PR #13 (commits 30f3f85, 93c1fe9, cc1acca, 9c5b6df,
> 9254fab, 3ac3a17, b971278). Result in `docs/findings/005` and
> `bench/precision/sweep.{json,md}`: float ≡ double on MOTA/IDS/AMOTA
> (Δ = 0.0), determinism 8/8, fp16 out of scope on x86. The `Real` knob
> (double default) lives in `core/include/trackbench/types.hpp`; `make
> core-float` builds the float variant; CI runs a `core-float` job.

## Why

The tracker is 100% `double` (`Eigen::Matrix<double,...>`, scalar `double`
throughout). Nobody has ever shown that double is the right precision, or that a
lower-precision filter is measurably different. This phase answers, with
numbers: **does the EKF need double, or is float indistinguishable at this
scale?** — plus the companion determinism question: **is the tracker
bit-for-bit reproducible at each precision?**

It is the last planned rigor phase. fp32/fp16-style precision is a classic
embedded-ADAS lever; this project hosts on x86 CPU, so the honest sweep is
**double (baseline) vs float**, with fp16 explicitly scoped out (rationale
below) rather than faked.

## Decisions (already made — do not re-litigate)

- **`Real` compile-time knob, default `double`.** `core/include/trackbench/types.hpp`
  gets `using Real = TRACKBENCH_REAL;` (default `double`), used by the Eigen
  state/covariance scalars and the `Track` filter-state fields (`x, y, yaw, vx,
  vy, cov_trace`). `Detection` and `TrackerConfig` stay `double` (input/JSON
  contract). JSON I/O stays double-signed (`format_json_double(double)`); a
  `float` state converts losslessly on write.
- **CMake option `TRACKBENCH_PRECISION`** (`double`|`float`, default `double`),
  plumbed as `TRACKBENCH_REAL=<type>` + `TRACKBENCH_PRECISION_FLOAT` compile
  definitions on the `trackbench` library (PUBLIC, following the existing
  `TRACKBENCH_STAGE_TIMING` pattern). `make core-float` builds
  `core/build-float/trackbench_run` (Release, `-DTRACKBENCH_PRECISION=float`).
- **The double build must remain byte-identical** — nothing in the emitted JSON
  or tracker state may change when `TRACKBENCH_PRECISION=double`. Proof is
  binding (see Task 1 gate).
- **Golden test is double-only.** The synthetic golden bytes are double
  outputs; under float they differ by design. The float CI job runs
  `ctest -E golden` (exclude the byte-compare) + the determinism smoke.
- **fp16 out of scope** with rationale in the finding: x86 CPUs have no native
  fp16 ALU path — `half` math is software-emulated and *slower*; fp16 only
  matters on ARM/GPU targets this project doesn't host. We measure float as the
  honest lower bound and say why fp16 is skipped.
- **Sweep never mutates `data/normalized/`.** The runner
  (`scripts/eval_all_scenes.sh`) writes `timing.json` INTO each scene dir — the
  sweep script must NOT use it; it calls `trackbench_run` directly per scene
  with `--out`/`--timing` under its own out-root.

## Key facts for the implementer

- Eigen types are `StateVector/StateMatrix/MeasVector/MeasMatrix` =
  `Eigen::Matrix<double,…>` (types.hpp:14-17); `Track::P` is `StateMatrix`
  (types.hpp:62). EKF internals in `core/src/ekf.cpp`; gate/IoU in
  `association.cpp`.
- CMake: `core/CMakeLists.txt` (Eigen via `find_package`/FetchContent; the
  `TRACKBENCH_STAGE_TIMING` compile-def pattern at line 43).
- CI: `.github/workflows/ci.yml` — `core` job = build Release w/ tests +
  `ctest` + a determinism smoke. A float job mirrors it with
  `-DTRACKBENCH_PRECISION=float` + `ctest -E golden`.
- Sweep data: the 4 reference cells in `bench/ablation/manifest.toml`
  (`[reference]`), the 10 scenes under `data/normalized/`, eval via
  `eval.metrics.evaluate_scene`, AMOTA via `eval.amota.compute_amota`, pooled
  p99 from the sweep's own `*_timing.json`. Existing committed double values
  are the expected result (the double sweep must reproduce them).
- `scripts/ablate.py` `--only <label> --force` re-runs one cell; a fresh double
  re-run of post003 must be byte-identical to the committed cell outputs.

## Tasks

### Task 1: `Real` precision knob (core)
- `Real` typedef + Eigen scalars + Track filter-state fields; CMake
  `TRACKBENCH_PRECISION` + `TRACKBENCH_PRECISION_FLOAT`; Makefile `core-float`;
  float CI job (`ctest -E golden`).
- **Gate (binding):** double build byte-identical — (a) `make core-test` golden
  + determinism pass; (b) `make core` then fresh re-run of post003
  (`ablate.py --only gate1p5-vel4p0-iou2p0-birth0p7 --force`) → cell
  `summary.json`/`_eval.json`/`amota.json` byte-identical to committed;
  (c) `summarize.py` in-place byte-identity + landmark gate exit 0.
- Float build: compiles, `ctest -E golden` passes, determinism smoke passes,
  and runs one real scene end-to-end.
- Commit: `feat(core): compile-time precision knob (Real=double default, float via TRACKBENCH_PRECISION)`

### Task 2: Precision sweep + determinism audit
- `scripts/precision_sweep.py` (stdlib+numpy; reuses eval.metrics + eval.amota):
  for each of the 4 reference configs × each precision (double, float): run
  `trackbench_run` per scene into the sweep out-root (never `data/normalized/`),
  **twice**; per-scene track bytes must be sha256-identical across the two runs
  (determinism assertion); compute MOTA/IDS (evaluate_scene), AMOTA/AMOTP
  (compute_amota), pooled p99 (own `*_timing.json`). Write
  `bench/precision/sweep.json` (per config+precision metrics, deltas
  float−double, determinism pass flags, provenance: commits + bin paths + ts)
  and generated `bench/precision/SWEEP.md`. Double values must match the
  committed cell outputs (no drift).
- Deterministic modulo provenance `ts`. Commit: `bench: precision sweep (double vs float) with per-precision determinism audit`

### Task 3: Finding + report
- `docs/findings/005-precision-not-a-lever.md` (001-004 format): measured
  float−double deltas on MOTA/IDS/AMOTA/p99; determinism holds per precision;
  fp16 out-of-scope rationale; statement that at ~0.5 ms/frame precision is not
  a latency or accuracy lever on x86. Every number traceable to sweep.json.
- Commit: `docs: precision sweep finding 005 (double vs float, determinism audit)`

## Out of scope

- fp16/fixed-point (rationale in finding); changing tracker state/matching
  semantics; regenerating the 24-cell grid; CI beyond the float job; any change
  to `data/`, committed cell outputs, or existing findings.

## Gate (binding)

- Double build byte-identical after Task 1 (proofs (a)-(c) above); landmarks
  hold; eval stack deps unchanged (`requirements.lock` untouched); sweep never
  writes into `data/normalized/`; all sweep numbers machine-derived; zero
  hand-edited metrics; no committed `.jsonl`.
