# TrackBench Results

Auto-generated where possible. Every number below comes from a real run; see the
commands in the Phase 1 section to reproduce.

## Phase 1 — Stage timing instrumentation

Instrumentation: 11 per-stage `steady_clock` timers inside `Tracker::step()`,
compile-time removable via `-DTRACKBENCH_STAGE_TIMING`. Timed and untimed builds
are both shipped. Per-frame times are emitted to `bench/timing.csv`.

### Workload
- Dense synthetic association load, 100 frames x 40 detections
  (`scripts/bench_latency.py --frames 100 --dets-per-frame 40`), all class `car`.
  Synthetic: exercises the association path only, not a MOT-accuracy bench.
- Release builds, `-O3 -DNDEBUG` (CMake generator default; no explicit flags,
  no LTO, no `-march=native`).

### Instrumentation overhead

Overhead is measured two ways: (1) wall-clock comparison of timed vs untimed
binaries; (2) an analytical estimate from the measured cost of
`steady_clock::now()`.

**Raw wall-clock runs** (all-frames p50/p99/max, ms, N=100):

| Build | Run 1 p50/p99 | Run 2 p50/p99 | Run 3 p50/p99 |
|-------|---------------|---------------|---------------|
| baseline (untimed) | 0.069 / 0.114 | 0.045 / 0.058 | 0.045 / 0.068 |
| timed | 0.041 / 0.059 | 0.040 / 0.056 | 0.033 / 0.048 |

Run-to-run variance (first run of each binary is cold-cache; the host is a laptop
under DVFS/thermal management) exceeds the instrumentation signal, so raw-run
comparison cannot resolve a <1% effect.

**Steady-state comparison** (frames 10+, single runs via `--json-out`):

| Metric | baseline (ms) | timed (ms) | delta |
|--------|---------------|------------|-------|
| p50 | 0.0311 | 0.0318 | +2.3% |
| p95 | 0.0337 | 0.0363 | +7.7% |
| p99 | 0.0561 | 0.0587 | +4.6% |

An interleaved A/B/A/B measurement (3 pairs) gave baseline p50 mean 0.0713 vs
timed 0.0813 (+14.0%) but p99 mean 0.1215 vs 0.1085 (−10.7%) — the sign reversal
on p99 is not physically possible for pure instrumentation overhead and is
attributed to host drift, confirming wall-clock noise exceeds the signal here.

**Analytical estimate** (measured, not assumed):
- `steady_clock::now()` cost measured at 59.7 / 67.0 ns per call
  (two runs of 2e7 calls, `-O3`).
- The timed build issues 22 such calls per frame (11 stage timers x ctor+dtor).
- Estimated instrumentation cost: ~1.4 µs/frame.
- At the measured steady-state p50 of ~31.8 µs that is **~4.4%**.

**Verdict:** instrumentation overhead is **~1.4 µs/frame (~2–4% of frame time at
this workload), which exceeds the <1% aspirational target**. The overhead is real,
not free, and the <1% target was not met. It is deterministic (~constant ns/frame)
and constant relative to frame size: it matters more at small N. The untimed
(default) build has zero instrumentation code and is unaffected. A future
optimization could cut it by sampling fewer `now()` calls (e.g. a single counter
per stage boundary).

### Per-stage timing (timed build, steady state)

Full distribution in `bench/timing_summary.md`; p50/p99 here (ns, warmup = first 5
frames per scene discarded):

| Stage | p50_ns | p99_ns | % of total (p50) |
|-------|--------|--------|------------------|
| DT | 0 | 84 | 0.0% |
| PREDICT | 2958 | 3250 | 9.3% |
| BUILD_ACTIVE | 333 | 1792 | 1.0% |
| COST_MATRIX_CONSTRUCT | 14000 | 15916 | 44.0% |
| ASSOCIATION_SOLVE | 4334 | 6334 | 13.6% |
| UPDATE | 4625 | 29000 | 14.5% |
| BIRTH | 0 | 42 | 0.0% |
| COAST_KILL | 41 | 42 | 0.1% |
| COMPACT | 41 | 84 | 0.1% |
| SORT_EMIT | 2542 | 15958 | 8.0% |
| TOTAL | 31792 | 58708 | 100.0% |

Note: `DT`, `BIRTH` read 0 at p50 because the mach clock tick (~41.7 ns) exceeds
their per-frame duration on this host; p99 shows they do fire. `UPDATE`/`SORT_EMIT`
p99 spikes reflect per-frame vector growth (allocation) on dense frames.

The dominant stage is **cost-matrix construction (44% of frame time at p50)**,
followed by update (14.5%) and association solve (13.6%). This matches the Phase 0
audit's allocation hypothesis: the per-frame path allocates a fresh cost matrix,
Munkres working arrays, and IoU polygon clip vectors every frame. Phase 3 targets
these first (scratch-buffer reuse, then SoA, then gating).

### Reproduce

```bash
cmake -S core -B build_timed -DCMAKE_BUILD_TYPE=Release -DTRACKBENCH_STAGE_TIMING=ON -DTRACKBENCH_BUILD_TESTS=OFF
cmake --build build_timed -j4
python3 scripts/bench_latency.py --tracker build_timed/trackbench_run --frames 100 --dets-per-frame 40 --timing-csv bench/timing.csv
python3 scripts/capture_machine.py --out bench/machine.json
python3 bench/timing_summary.py bench/timing.csv --out bench/timing_summary.md
```

## Machine

Captured in `bench/machine.json`:

| Field | Value |
|-------|-------|
| CPU | Apple M5 Pro |
| Cores | 18 (physical) / 18 (logical) |
| RAM | 25.8 GB |
| Compiler | Apple clang 21.0.0 (clang-2100.1.1.101) |
| Flags | Release = `-O3 -DNDEBUG` (default CMake flags) |
| OS | macOS-26.5.1-arm64-arm-64bit |
| Captured | 2026-08-10T13:05:00Z |

All Phase 1 timings on this host. Wall-clock numbers on a laptop under DVFS are
noisy at these frame times (see overhead section); the per-stage CSV and percentile
distributions are the stable artifact.

## Accuracy gates

After adding the instrumentation, both accuracy gates passed unchanged:
- `Golden.SyntheticScene001ByteIdentical` + `Golden.DeterministicAcrossTwoRuns` PASS
- `make eval-fixture`: MOTA 0.9000 (baseline 0.9000), IDS 0 (baseline 0) — PASS
