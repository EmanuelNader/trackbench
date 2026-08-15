# 005 — Precision is not a lever: float is indistinguishable from double on the mini set

## What the system surfaced

Phase 6 added a compile-time **`Real` precision knob** to the tracker
(`core/include/trackbench/types.hpp`: `using Real = TRACKBENCH_REAL`, default
`double`; float via `-DTRACKBENCH_PRECISION=float` in CMake) and swept the four
`[reference]` configs of `bench/ablation/manifest.toml` × {double, float} × 2
runs on the 10-scene mini set
(`scripts/precision_sweep.py` → `bench/precision/sweep.json`,
generated `bench/precision/SWEEP.md`). It surfaced that the tracker does **not
need double** for any accuracy metric at this scale: float and double produce
**identical** MOTA, IDS, and AMOTA on every reference config, differ on AMOTP
only at the ~1e-8 level (float summation noise), and are each bit-for-bit
deterministic across runs.

## Question

Does the EKF need `double`, or is `float` indistinguishable at this scale? —
plus the companion determinism question: is the tracker bit-for-bit
reproducible at each precision?

## Hypothesis

The tracker runs at ~0.1–0.5 ms/frame on the 10-scene mini set and its
association decisions are gated in order-1-meter space, far above float's
~1e-7 relative resolution. Predicted: float should not change any CLEAR-MOT or
AMOTA decision (Δ = 0.0 on MOTA/IDS/AMOTA); AMOTP may show float-precision
summation noise at ~1e-8; the tracker is single-threaded and has no atomics or
non-deterministic iteration, so determinism should hold at each precision.

## Experiment / Method

- **`Real` knob:** `types.hpp:18-21`; CMake option `TRACKBENCH_PRECISION`
  (`double` default, `float` → `TRACKBENCH_PRECISION_FLOAT`); double binary
  `core/build/trackbench_run`, float binary `core/build-float/trackbench_run`
  (`make core-float`).
- **Grid:** the 4 `[reference]` cells × 2 precisions × 2 runs, 10 scenes each
  (`data/normalized/`), output written to the sweep's own out-root — never into
  `data/normalized/`.
- **Metrics:** MOTA/IDS via CLEAR MOT (`eval.metrics.evaluate_scene`); AMOTA/AMOTP
  via the Phase 5 nuScenes recall-curve metric (`eval.amota.compute_amota`);
  pooled p99 from the sweep's own `*_timing.json` files.
- **Determinism audit:** per-scene track bytes sha256-compared between run 1 and
  run 2 at each precision; 10 scene-byte streams compared per config+precision.
- **Output:** `bench/precision/sweep.json` (metrics, `deltas` float−double,
  per-cell `determinism.pass`, provenance: commit
  `93c1fe9c37389443df22bbbc06a5adc9b48e7381`, binary paths, python 3.9.6,
  ts 2026-08-15T07:38:32Z) and the generated `bench/precision/SWEEP.md`.

Every number below is taken from `bench/precision/sweep.json`; the double
columns reproduce the committed cell outputs from Phases 4/5 (no drift — cf.
finding [004](004-amota-vs-mota-ranking.md) reference table). No significance
testing; all as measured on the 10-scene mini set.

## Config × precision (from `bench/precision/sweep.json`)

| config | reference | precision | MOTA | IDS | AMOTA | AMOTP | p99 ms | determinism |
|--------|-----------|-----------|------|-----|-------|-------|--------|-------------|
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | double | −1.351184 | 890 | 0.179062 | 1.645237 | 0.5103 | PASS |
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | float  | −1.351184 | 890 | 0.179062 | 1.645237 | 0.5058 | PASS |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | double | −0.300577 | 618 | 0.224958 | 1.582040 | 0.2030 | PASS |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | float  | −0.300577 | 618 | 0.224958 | 1.582040 | 0.2606 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | double | −0.281785 | 619 | 0.225064 | 1.582056 | 0.2045 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | float  | −0.281785 | 619 | 0.225064 | 1.582056 | 0.2002 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | double | 0.665956 | 415 | 0.219651 | 1.623278 | 0.1200 | PASS |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | float  | 0.665956 | 415 | 0.219651 | 1.623278 | 0.1184 | PASS |

## float − double deltas (from `sweep.json` `deltas`)

| config | reference | ΔMOTA | ΔIDS | ΔAMOTA | ΔAMOTP | Δp99 ms |
|--------|-----------|-------|------|--------|--------|---------|
| gate2p0-vel0p0-iou0p0-birth0p0 | baseline | 0.0 | 0 | 0.0 | +2.2745189731665505e-08 | −0.0045 |
| gate1p5-vel4p0-iou0p0-birth0p5 | post001 | 0.0 | 0 | 0.0 | +2.8097872029064774e-08 | +0.0575 |
| gate1p5-vel4p0-iou2p0-birth0p5 | post002 | 0.0 | 0 | 0.0 | +2.8072590252392615e-08 | −0.0043 |
| gate1p5-vel4p0-iou2p0-birth0p7 | post003 | 0.0 | 0 | 0.0 | +2.8476372593289057e-08 | −0.0016 |

**float − double Δ = 0.0 on MOTA, IDS, and AMOTA for all four reference
configs.** AMOTP differs only at the ~1e-8 level — consistent with float's
24-bit significand imprinting on the AMOTP distance sums; no association
decision or recall-slot outcome changes. **Determinism: 8/8 PASS** (4 configs ×
2 precisions; per-scene track bytes sha256-identical between the two runs at
each precision).

## Caveats — what this does *not* claim

1. **Innovation arithmetic runs in double.** The measurement is double
   (`Detection`, `types.hpp:29-39`) and the `Real` state promotes to double in
   the gate's innovation subtraction `det.x - track.x` before narrowing back
   into the `Real` vector (`ekf.cpp:89`). The float result is therefore best
   read as *"float filter, double-precision innovation arithmetic"* — this sweep
   does not exercise a pure single-precision math path end to end.
2. **`p99_ms` is wall-clock jitter, not a speed claim.** The run-to-run and
   double-vs-float p99 spread (measured range 0.118–0.510 ms/frame; e.g. post001
   double 0.2030 vs float 0.2606, Δ +0.0575) is single-run wall-clock jitter.
   Precision makes **no measurable latency difference** at ~0.1–0.5 ms/frame;
   nothing here says float is faster *or* slower.
3. **fp16 is out of scope, deliberately.** x86-64 CPUs have no native fp16 ALU
   — `half` math is software-emulated and *slower*, so fp16 would only matter on
   ARM/GPU targets this project does not host. The honest lower bound measured
   here is **float**.

## Conclusion

**Precision is not an accuracy or latency lever at this scale and on this
platform.** float ≡ double on MOTA/IDS/AMOTA across all four reference configs,
AMOTP differs only in ~1e-8 summation noise, and both precisions are fully
deterministic. Keep `double` as the default (free, zero risk, byte-identical to
the committed Phase 4/5 outputs); the float build stays available as a
CI-checked configuration (`ctest -E golden` + determinism smoke) for future
targets. All figures are as measured on the 10-scene mini set; no significance
claims.

## What I'd do next

1. If the tracker ever targets ARM/GPU hardware (or needs to run embedded with
   half-width memory traffic), re-run this sweep there — fp16 becomes a real
   lever only on those hosts.
2. Add a CI guard so the `Real` default cannot silently drift from `double`
   (e.g. a byte-identity check of the double build against committed cell
   outputs, as Task 1's gate already proves).
3. Nothing else: no accuracy or latency argument here justifies touching the
   filter precision.
