# 006 — CTRRV motion model degrades IDS and MOTA everywhere (null hypothesis supported)

## What the system surfaced

Phase 7 added a **`motion_model` config knob** (`core/include/trackbench/config.hpp`:
`MotionModel` enum, `"cv"` default, `"ctrv"` via `motion_model: "ctrv"` in
`config.yaml`; CMake option `TRACKBENCH_CTRRV` enables the compile path; EKF
predict branch in `core/src/ekf.cpp`) and swept the four `[reference]`
configs of `bench/ctrv/manifest.toml` × {cv, ctrv} × 2 runs on the 10-scene
mini set (`scripts/ctrv_sweep.py` → `bench/ctrv/sweep.json`, generated
`bench/ctrv/SWEEP.md`). It surfaced that CTRRV **degrades IDS and MOTA on every
reference config** — the hypothesis that turn-rate modeling reduces identity
switches is not supported on this 10-scene mini split. The one nuance: the
baseline config sees an AMOTA improvement of +0.04 (0.1791 → 0.2197), a
precision-vs-recall trade-off where CTRRV's turn-rate prediction keeps more
tracks alive through turns at the cost of more identity switches.

## Question

Does the CTRRV (constant turn-rate and velocity) motion model reduce identity
switches and improve tracking quality compared to the CV (constant velocity)
model? — plus the companion determinism question: is the tracker bit-for-bit
reproducible at each motion model?

## Hypothesis

CTRRV models yaw rate, so predicted positions should better follow curved
trajectories — reducing association errors and thus IDS. Predicted: IDS should
decrease, MOTA should improve (fewer ID switches → fewer IDS penalties), AMOTA
should improve (better recall through turns). The tracker is single-threaded
with no non-deterministic iteration, so determinism should hold at each motion
model.

## Experiment / Method

- **`motion_model` knob:** `config.hpp`; CMake option `TRACKBENCH_CTRRV`
  (`cv` default, `ctrv` enabled via `-DTRACKBENCH_CTRRV=ON`); both models
  run from the same binary `core/build/trackbench_run` (config-selected at
  runtime).
- **Grid:** the 4 `[reference]` cells × 2 motion models × 2 runs, 10 scenes
  each (`data/normalized/`), output written to the sweep's own out-root —
  never into `data/normalized/`.
- **Yaw rate:** fixed at `0.1` rad/s (`provenance.yawrate`).
- **Metrics:** MOTA/IDS via CLEAR MOT (`eval.metrics.evaluate_scene`);
  AMOTA/AMOTP via the Phase 5 nuScenes recall-curve metric
  (`eval.amota.compute_amota`); pooled p99 from the sweep's own
  `*_timing.json` files.
- **Determinism audit:** per-scene track bytes sha256-compared between run 1
  and run 2 at each motion model; 10 scene-byte streams compared per
  config+motion_model.
- **Output:** `bench/ctrv/sweep.json` (metrics, `deltas` ctrv−cv, per-cell
  `determinism.pass`, provenance: commit
  `53ca836e3852c88115c28bb86bf8f77616d74c8f`, binary path
  `core/build/trackbench_run`, python 3.9.6,
  ts 2026-08-17T02:20:33.229751+00:00, yawrate 0.1) and the generated
  `bench/ctrv/SWEEP.md`.

Every number below is taken from `bench/ctrv/sweep.json`. No significance
testing; all as measured on the 10-scene mini set.

## Config × motion model (from `bench/ctrv/sweep.json`)

| config | reference | motion | MOTA | IDS | AMOTA | AMOTP | p99 ms | determinism |
|--------|-----------|--------|------|-----|-------|-------|--------|-------------|
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | cv | −1.351184 | 890 | 0.179062 | 1.645237 | 4.9784 | PASS |
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | ctrv | −1.625940 | 978 | 0.219738 | 1.552571 | 4.6207 | PASS |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | cv | −0.300577 | 618 | 0.224958 | 1.582040 | 2.5507 | PASS |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | ctrv | −0.407865 | 747 | 0.220131 | 1.583879 | 2.6445 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | cv | −0.281785 | 619 | 0.225064 | 1.582056 | 2.4969 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | ctrv | −0.398229 | 746 | 0.220201 | 1.583724 | 2.5906 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | cv | 0.665956 | 415 | 0.219651 | 1.623278 | 1.5915 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | ctrv | 0.496736 | 508 | 0.215787 | 1.623080 | 1.6677 | PASS |

The sweep also contains two duplicate `reference: "current"` entries for
post003 (cv and ctrv) with identical metrics to the `reference: "post003"`
entries; these are omitted from the table above.

**CTRRV − CV deltas** (from `sweep.json` `deltas`):

| config | reference | ΔMOTA | ΔIDS | ΔAMOTA | ΔAMOTP | Δp99 ms |
|--------|-----------|-------|------|--------|--------|---------|
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | −0.274756 | +88 | +0.040676 | −0.092666 | −0.3577 |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | −0.107288 | +129 | −0.004826 | +0.001839 | +0.0938 |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | −0.116445 | +127 | −0.004863 | +0.001669 | +0.0938 |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | −0.169220 | +93 | −0.003864 | −0.000198 | +0.0762 |

**ΔIDS = +88 to +129 across all four reference configs.** IDS worsens
everywhere — CTRRV's turn-rate prediction does not reduce identity switches on
this mini set. **ΔMOTA is negative on all four configs** (−0.11 to −0.27),
consistent with the IDS penalty propagating into MOTA.

**ΔAMOTA is positive only on the baseline** (+0.0407), and slightly negative
on the other three (−0.0039 to −0.0049). The baseline AMOTA improvement is
the one noteworthy result and is discussed below.

**Δp99 is comparable** (range −0.36 to +0.09 ms); CTRRV's nonlinear predict
is not measurably slower than the linear one at this state dimension. **Determinism: 8/8 PASS** (4 configs × 2 motion models; per-scene track bytes
sha256-identical between the two runs at each motion model).

## The baseline AMOTA nuance

The baseline config (gate=2.0, no velocity cost, no IoU, birth=0.0) is the
only config where CTRRV improves AMOTA: 0.179062 → 0.219738 (+0.0407). This
is a **precision-vs-recall trade-off**, not a free improvement:

- IDS worsens by +88 (890 → 978), so CTRRV is not reducing identity
  switches.
- But the baseline has the most IDS of any config (890 with CV), meaning many
  tracks are being broken and re-initialized. CTRRV's turn-rate prediction
  keeps more tracks alive *through turns* (improving recall on the AMOTA
  recall curve), even though it creates new identity switches elsewhere.
- AMOTP improves on the baseline (1.6452 → 1.5526, Δ = −0.0927), suggesting
  that when CTRRV does associate correctly, the predicted positions are
  closer to ground truth.
- The already-optimized configs (post001–003) do not benefit because their
  tighter gate/vel/birth settings already compensate for turn-induced drift;
  adding turn-rate modeling on top creates additional association instability
  without a recall offset.

## Per-scene IDS breakdown

Which scenes drive the IDS increase? Per-scene ΔIDS (CTRRV − CV):

| scene | baseline | post001 | post002 | post003 |
|-------|----------|---------|---------|---------|
| scene-0061 | +3 | +1 | +1 | +1 |
| scene-0103 | +14 | +10 | +10 | +1 |
| scene-0553 | 0 | 0 | 0 | 0 |
| scene-0655 | +28 | +68 | +66 | +59 |
| scene-0757 | +1 | 0 | 0 | 0 |
| scene-0796 | 0 | 0 | 0 | 0 |
| scene-0916 | +44 | +41 | +41 | +25 |
| scene-1077 | 0 | 0 | 0 | 0 |
| scene-1094 | −2 | +9 | +9 | +7 |
| scene-1100 | 0 | 0 | 0 | 0 |
| **total** | **+88** | **+129** | **+127** | **+93** |

**scene-0655 and scene-0916 dominate the IDS increase** across all configs.
These two scenes alone account for 72 of the baseline's +88 IDS and 109 of
post001's +129 IDS. scene-0103 contributes a secondary +10–14 on the three
lower-birth configs (baseline, post001, post002) but nearly vanishes (+1) on
post003 where the higher birth score already filters transient tracks.
scene-1094 shows a small mixed signal: −2 on baseline (CTRRV actually
*improves* this scene) but +7 to +9 on the other configs.

Five scenes (0553, 0796, 1077, 1100, and partially 0757) show zero or
near-zero IDS delta — CTRRV and CV are equivalent on these scenes.

## Caveats — what this does *not* claim

1. **Yaw rate is fixed at 0.1 rad/s.** The sweep does not vary yaw rate; a
   dataset with sharper turns might benefit more (or less) from CTRRV. The
   `process_var_yawrate` parameter was not swept.
2. **10-scene mini set.** This is a small, representative subset — not a
   full-scale evaluation. The per-scene IDS deltas (especially scene-0655
   and scene-0916) are driven by individual scene characteristics that may
   not generalize.
3. **`p99_ms` is wall-clock jitter.** The run-to-run and cv-vs-ctrv p99
   spread (measured range 1.59–4.98 ms/frame) reflects single-run wall-clock
   jitter. CTRRV's nonlinear predict is not measurably slower than the linear
   one at this state dimension; no latency claim is made.
4. **No parameter tuning for CTRRV.** The CTRCV model runs with the same
   gate, velocity cost, IoU, and birth settings as CV — a fair apples-to-
   apples comparison, but one that does not explore whether CTRRV-specific
   tuning could recover the IDS loss.
5. **"current" duplicate entries.** The sweep contains two `reference: "current"`
   entries for the post003 config that are metric-identical to the
   `reference: "post003"` entries; these are artifacts of the sweep script's
   reference labeling and are not separately analyzed.

## Conclusion

**CTRRV is not a lever on IDS or MOTA at this scale and on this dataset.**
IDS worsens by +88 to +129 across all four reference configs; MOTA degrades
by 0.11–0.27; three of four configs see slight AMOTA degradation (−0.004 to
−0.005). The one exception — baseline AMOTA improving +0.04 — is a
precision-vs-recall trade-off where CTRRV's turn-rate prediction keeps more
tracks alive through turns (improving recall) even as it creates new identity
switches (worsening IDS). The velocity gate and birth-score tightening
(findings 001/003) remain the effective levers for IDS reduction.

**Recommendation:** keep `cv` as the default motion model. CTRRV is available
as a config option for future datasets where turn-rate tracking may help
(e.g., highway scenes with longer, smoother turns), but it should not be
enabled on the current mini set without per-scene investigation of why
scene-0655 and scene-0916 are so adversely affected. All figures are as
measured on the 10-scene mini set; no significance claims.

## What I'd do next

1. **Profile scene-0655 and scene-0916.** These two scenes drive the
   majority of the IDS increase — understanding their trajectory geometry
   (sharp turns? high curvature? occlusions during turns?) would clarify
   whether CTRRV's degradation is a model-mismatch issue or a parameter
   tuning issue.
2. **Sweep `process_var_yawrate`.** The yaw rate process noise was fixed at
   0.1 rad/s; a dataset-specific sweep might find a value that reduces IDS
   without sacrificing the baseline AMOTA gain.
3. **Try CTRRV on a larger dataset.** The 10-scene mini set may not have
   enough curved trajectories to benefit from turn-rate modeling; a full
   nuScenes or Waymo split with highway/interchange scenes could change the
   picture.
