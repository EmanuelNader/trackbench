# TrackBench Profiling Baseline (Phase 2)

Captured on the machine in `bench/machine.json` (Apple M5 Pro, macOS 26.5.1, Apple
clang 21, Release `-O3 -DNDEBUG`, no LTO, no `-march=native`). Tools: `sample`
(macOS built-in sampler) + `xctrace` Time Profiler/CPU Counters. Raw artifacts:
`docs/bench/profile_tracking_n40_sample.txt` (tracking-loop-only window) and
`docs/bench/profile_fullprocess_n300_sample.txt` (whole process at N=300).

**Method note (honest limits):** wall-clock comparisons on this laptop are noisy
(run-to-run variance up to 2.5x on identical work — see the same workload take
23.4 s then 59.5 s). Where a number matters, prefer the per-stage CSV
(`bench/timing.csv`), which is measured in-process per frame, over wall-clock
sampling. macOS `xctrace` "CPU Counters" data is not CLI-exportable on this
xctrace version (Swift-table limitation), so cache-miss counters come from the CI
`perf-stat` job (Linux) instead — see below.

## Hot spots, ranked

### 1. Association solve — `hungarian_minimize` (O(n^3) Munkres) — dominant at high N
At N=300 dets/frame, `Tracker::step` is 2830 samples; `associate` is 1744 (62%),
and `hungarian_minimize` alone is **1639 samples (~58% of step time)**.

```
trackbench::Tracker::step           2830
+ trackbench::associate             1744
  + trackbench::hungarian_minimize  1639   <- the solve
```

- **Hypothesis (algorithmic):** classic O(n^3) Munkres over a **padded square**
  matrix. At N=300 that is ~2.7e7 ops/frame in the inner loop. Growth is cubic.
- **Hypothesis (allocation):** `hungarian_minimize` also re-copies the entire
  cost matrix per call — 89 samples in `__uninitialized_allocator_copy_impl`
  (53 memmove + 31 `operator new`): every frame, every solve, a fresh padded
  square matrix is heap-allocated and memcpy'd.
- Falsifiable in Phase 3: (3b) a JV/auction or sparse solver; (3d) scratch-buffer
  reuse for the matrix copy.

### 2. Cost-matrix construction — `associate` matrix build (O(n^2) cells) — dominant at realistic N
At the realistic N=40 workload the per-stage CSV (`bench/timing.csv`,
`bench/timing_summary.md`) shows cost-matrix construction at **14.0 us/frame,
44% of frame time** — the single largest stage at N=40.

- **Hypothesis (allocation):** the matrix is `std::vector<std::vector<double>>`
  allocated fresh every frame; every cell is pre-filled with `kCostInf`; the
  per-cell cost for gated-in pairs runs `bev_oriented_iou` which allocates up to
  5 `std::vector<Vec2>`s (polygon clipping) per pair. In the N=300 profile,
  `bev_oriented_iou` appears with `operator new` + `malloc`/`free` children.
- Falsifiable in Phase 3: (3d) scratch buffer for the matrix + IoU clip polygons;
  (3a) a spatial grid to avoid visiting O(n^2) pairs.

### 3. Track update — `Ekf::update` — secondary
At N=40, UPDATE is ~4.6 us/frame (14.5%). Eigen fixed-size 5x5 math with a full
3x3 `S.inverse()` per matched track; no allocation (heap-free). Mild.

### 4. Predict — `Ekf::predict` — secondary
At N=40, ~3.0 us/frame (9.3%). Cache hypothesis: AoS `Track` (~320 B, of which
the 200 B Eigen `P` covariance), so streaming predict touches ~5 cache lines per
track, dragging `cls`/`id`/`l`/`w` along. Falsifiable in Phase 3: (3c) SoA
covariance split — report cache-miss rate before/after.

### 5. Track lifecycle + sorting — small
BIRTH/COAST_KILL/COMPACT < 1% combined. SORT_EMIT ~8% at p50 (two `stable_sort`s
of full 320 B `Track` objects + output deep-copy), spiking at p99 to ~16 us on
dense frames (vector growth during emit).

## Process-level finding: the JSONL reader is the wall-clock bottleneck on big inputs

For the dense bench workload the input/output path dwarfs tracking. Same 100k-frame
input: wall 23.4 s vs tracking 4.15 s in one run (load+write ~82% of wall), and in a
second run wall 59.5 s vs tracking 7.9 s. `read_detections_jsonl` +
`extract_number` (per-line string scanning, `memchr`/`memcmp`, `std::stod`,
temporary `std::string`s) parse at roughly **7.5 us/line** on this host. The output
writer (`write_tracks_jsonl`, `snprintf` + `std::ostream` per value) is similarly
expensive.

- **Impact:** the bench harness (Phase 3 scaling curves) must either use smaller
  inputs, accept parse-dominated wall time, or the reader/writer need their own
  optimization pass (out of Phase 3's tracker-focused scope, but a candidate for a
  follow-up).
- This is why the N=40 tracking-only profile (`profile_tracking_n40_sample.txt`)
  was captured by sampling past the load phase, and the N=300 profile samples the
  whole process (at N=300 tracking becomes the majority of wall time, so the
  process-level profile is tracking-dominated).

## Cache counters

macOS `xctrace` CPU Counters was captured (`/tmp` trace, 292 MB, not committed) but
its per-thread counter tables are not CLI-exportable on xctrace 16.0. The CI
`perf-stat` job (`.github/workflows/ci.yml`) runs Linux `perf stat -e
cycles,instructions,cache-references,cache-misses,branches,branch-misses,
context-switches` over the tracker on the dense synthetic (400 frames x 40 dets)
and is the source of instruction/cache telemetry for Phase 3 (3c before/after
cache-miss comparison). It is informational (continue-on-error), not a CI gate.

## Phase 3 targeting summary

| Rank | Hot spot | Evidence | Phase 3 lever |
|------|----------|----------|---------------|
| 1 | Munkres solve (O(n^3) + per-call matrix copy) | N=300: 58% of step | 3b JV/auction, 3d scratch buffers |
| 2 | Cost-matrix build (O(n^2) + per-cell IoU allocs) | N=40: 44% of frame | 3d scratch buffers, 3a spatial gate |
| 3 | Track update | N=40: 14.5% | (leave; heap-free already) |
| 4 | Predict (AoS cache traffic) | N=40: 9.3% | 3c SoA covariance |
| — | JSONL reader/writer | wall ~80% at 100k frames | out of scope; follow-up |
