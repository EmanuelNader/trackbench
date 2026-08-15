# Phase 1–3 Performance Rigor Upgrade Plan

> STATUS: DONE — implemented; results recorded in `docs/findings/001` (velocity
> gate), `002` (BEV IoU), and `bench/` (timing rig, `bench/machine.json`,
> `scripts/capture_machine.py`). Superseded where noted by the phase 4–5 plans.

## Global Constraints (binding)

1. **Measure before optimizing** — no optimization without profiler-identified hotspot
2. **One change per commit** — commit message: `perf: <change> — p99 <before> → <after> (N=<frames>)`
3. **Accuracy hard constraint** — after every change: `make eval-fixture` + `make core-test` (golden byte-identical). Any regression → revert.
4. **Report negative results** — null optimizations stay as commits with findings written up
5. **No style refactors** — touch only what measurements justify
6. **No fabricated numbers** — if a benchmark didn't run, say so
7. **Ask before large structural changes** — Phase 4+ are out of scope for this plan

---

## SESSION HANDOFF — read this first (updated 2026-08-10)

> A fresh session must read this section before doing anything. It supersedes
> task descriptions below where they are out of date.

### Overall status
Phase 1 (timing instrumentation) is COMPLETE. Phase 2 (profile) and Phase 3
(optimization) are COMPLETE. Tasks 1–15 all committed, reviewed, and pushed to
GitHub (`main`). Phase 3 landed two wins (scratch-buffer reuse, spatial
prefilter) and two documented negative results (assignment-algorithm switch,
intra-frame parallelism). The only uncommitted path forward is Phase 4+ (out of
scope for this plan). Final HEAD: `a271350`. Full gate run (ctest + golden +
eval-fixture MOTA 0.9/IDS 0) is green at HEAD.

### Process conventions (how we work)
- **SDD workflow**: for each task → write task brief via
  `.config/opencode/skills/_superpowers__skills__subagent-driven-development/scripts/task-brief PLAN N`
  → dispatch a fresh `general` implementer subagent → implementer commits locally →
  generate review package via `.../scripts/review-package PLAN BASE HEAD` → dispatch a
  reviewer subagent → on approval, append a line to the ledger
  `.superpowers/sdd/phase1-3-perf-rigor/progress.md` and continue. Minors are deferred
  to the final whole-branch review, never block.
- **Commits**: one logical change per commit. Message format `perf: <change> — <before> -> <after> (N=<frames>)`
  (Phases 2/3) or plain `perf: <description>` (Phase 1 tooling). **NEVER add a
  Co-authored-by trailer.** Never amend prior commits.
- **GitHub**: after each completed task (or every few), `git push origin main`.
  Commits are authored as the local git user (Emanuel Nader).
- **Important state to preserve**: `docs/superpowers/` is intentionally untracked
  (gitignored at `.superpowers/sdd/`); the plan lives under `docs/superpowers/plans/`.
  Do NOT commit `.superpowers/` artifacts. `package-lock.json` (root) and `web/.vite/`
  are pre-existing untracked — leave them.

### Committed work (all on origin/main)
| Task | Commit | What |
|------|--------|------|
| 1 | `c0e979d` | `core/include/trackbench/timing.hpp` — `StageTimings` enum (DT=0..TOTAL=10, COUNT=11) + `ScopedTimer`, gated by `TRACKBENCH_STAGE_TIMING` |
| 4 | `0d3cf1c` | `core/CMakeLists.txt` — `option(TRACKBENCH_STAGE_TIMING ... OFF)`; adds the define PUBLIC to `trackbench`, PRIVATE to `trackbench_tests` |
| 2 | `642aee6` | Instrumented `Tracker::step()` with 11 non-overlapping stage timers; `frame_timings_` member + `frame_timings()` getter (macro-only); `associate()` gained `timings` param (`= nullptr` default); cost-matrix build + solve timed inside `association.cpp` |
| 3 | `5e83707` | `core/src/main.cpp` `--timing-csv PATH` flag. CSV header: `frame,scene_id,n_active,n_dets,dt_ns,predict_ns,build_active_ns,cost_matrix_construct_ns,association_solve_ns,update_ns,birth_ns,coast_kill_ns,compact_ns,sort_emit_ns,total_ns`. Non-macro build prints warning + exit 0 |
| 5 | `bb4eb81` | `scripts/bench_latency.py` `--timing-csv` passthrough; JSON `timing_csv` key |
| 6 | `031f419` | `scripts/capture_machine.py` — emits `bench/machine.json` (CPU, cores, RAM, compiler, cmake_flags, os, timestamp) |
| 7 | `dc171f5` | `bench/timing_summary.py` — p50/p95/p99/max per stage, discards warmup (default 5/scene); handles the placeholder-scene_id degenerate encoding |
| 8 | `273beba` | `core/tests/test_timed_smoke.cpp` — `TimedSmoke.StageTimingsPartitionTotal`; asserts sum(non-TOTAL stages) ≈ TOTAL (5%), TOTAL>0, sizes match; "each stage fired" uses max-across-30-frames (sub-tick stages read 0 ns on Apple Silicon mach clock) |

### In-flight (do this next)
**Task 8 review is PENDING.** Review package exists:
`.superpowers/sdd/phase1-3-perf-rigor/review-dc171f5..273beba.diff` (Base `dc171f5`,
Head `273beba`). Dispatch the reviewer using the standard template. The key thing the
reviewer must scrutinize: the implementer's deviation from the brief — "each stage > 0
on the last frame" was changed to "max across 30 frames" because sub-tick stages
(DT/BIRTH/COAST_KILL) read 0 ns on Apple Silicon. Confirm that is sound; if the
reviewer wants fixes, loop back.

### Next tasks after the pending review
- **Task 9** (Verification + measurement, the real Phase 1 deliverable): golden test
  (`make core-test`) + `make eval-fixture` must PASS unchanged; build timed vs untimed
  Release binaries; measure instrumentation overhead (<1% of p99 target) by running
  `bench_latency.py` 3× each; generate `bench/timing.csv` (use `--dets-per-frame 40
  --frames 200` dense + a low-N run), `bench/machine.json`
  (`python3 scripts/capture_machine.py --out bench/machine.json`),
  `bench/timing_summary.md`; create first `RESULTS.md` with the Phase 1 table. Commit
  the artifacts. NOTE: real per-scene results need `scene_id` wired from the scene
  (currently a placeholder = frame number, see Task 3 ambiguity resolution) — decide
  whether to fix that or proceed with the placeholder and label it.
- **Task 10** (Phase 2 profiling): macOS `xcrun xctrace` Time Profiler + CPU Counters on
  dense synthetic (100×40); CI `perf stat` job on ubuntu-latest; commit raw outputs;
  write `PROFILE.md`.
- **Tasks 11–15** (Phase 3): 3d scratch-buffer reuse → 3c SoA covariance → 3a spatial
  prefilter → 3b JV/auction benchmark → 3e intra-frame parallelism. One commit each,
  before/after numbers in the message, accuracy gate after every change, negative
  results kept.

### Key decisions already made (do not re-litigate)
- **1a**: ablation grid (Phase 4) runs on REAL nuScenes mini — the user has
  `data/raw/nuscenes/v1.0-mini/` + Megvii detections downloaded locally.
- **2b**: AMOTA (Phase 5) via the nuscenes-devkit `TrackingEvaluation` adapter, plus a
  C++ `Track::score` field (needed either way).
- Optimization order (3d→3c→3a→3b→3e) reflects expected payoff from the Phase 0 audit:
  the per-frame path allocates fresh every step (cost matrix, munkres working arrays,
  IoU polygon clip vectors, deep Track copies); AoS `Track` ≈ 320 B with a 200 B Eigen
  `P` member spans ~5 cache lines; association is O(n³) Munkres on a dense padded matrix
  with no spatial index.

### Deferred review minors (DONE — Task 16, commits 99f1c26..fc27be5)
- Task 1: trailing newline `timing.hpp` — done (`99f1c26`).
- Task 2: `stage_ns` guarded to macro builds + `nullptr` call site in non-macro (`d3f9628`);
  `frame_timings_` capped at 4096 recent tail (`81b9a2a`); `StageNs` alias added and used
  across 5 files (`c3f93e9`). `#ifdef` style unification SKIPPED — both patterns load-bearing
  (null-`timings` fallback avoids UB in non-macro builds; per-timer `#ifdef`s keep the hot
  path free of no-op timer objects). Reviewer-approved skip.
- Task 3: flush-state check after `csv.close()` + `ft[i]` bounds guard (`34e25d2`); tail/head
  pairing aligned after the cap engages (`fc27be5`, verified at 5000 frames).
- Task 7: CSV row shape + int validation with `path:line` context (`7fef565`); `EXPECTED_HEADER`
  byte-match vs `core/src/main.cpp:141-144` verified and documented (`73a4b6c`).
- Task 8: review was completed and approved (see ledger) before this batch.

### Useful facts for the next session
- Repo: macOS (darwin), `make core` = Release (-O3 default, no explicit flags, no
  LTO, no -march=native), `make core-test` = Debug + GoogleTest, golden byte-identical
  test is `Golden.SyntheticScene001ByteIdentical` in `core/tests/test_golden.cpp`.
- Synthetic fixture: `data/fixtures/synthetic_scene_001/` (20 frames, single scene,
  golden `tracks_expected.jsonl`). Dense synthetic generator: `scripts/bench_latency.py`
  `--tracker BIN --frames N --dets-per-frame N` (flag is `--tracker`, not `--binary`).
- The 11 stage indices: `DT=0, PREDICT=1, BUILD_ACTIVE=2, COST_MATRIX_CONSTRUCT=3,
  ASSOCIATION_SOLVE=4, UPDATE=5, BIRTH=6, COAST_KILL=7, COMPACT=8, SORT_EMIT=9,
  TOTAL=10, COUNT=11`.
- Env: GitHub MCP configured at `~/.config/opencode/mcp.json`; `perf` is unavailable on
  macOS — use Instruments/`sample`/`xctrace`.

---

## Task 1: Create timing.hpp with ScopedTimer and StageTimings enum

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to create/modify:
- `core/include/trackbench/timing.hpp` — `ScopedTimer`, `StageTimings` enum, macro-gated

### Requirements:
- `StageTimings` enum with values: `DT`, `PREDICT`, `BUILD_ACTIVE`, `COST_MATRIX_CONSTRUCT`, `ASSOCIATION_SOLVE`, `UPDATE`, `BIRTH`, `COAST_KILL`, `COMPACT`, `SORT_EMIT`, `TOTAL`, `COUNT`
- `ScopedTimer` class using `std::chrono::steady_clock` that accumulates nanoseconds into a provided `std::array<uint64_t, COUNT>` by stage index
- All timing code gated by `#ifdef TRACKBENCH_STAGE_TIMING` — when macro is not defined, `ScopedTimer` is a no-op zero-size struct (compile-time removed)
- Header-only, self-contained, no external dependencies beyond `<chrono>`, `<array>`, `<cstdint>`
- Namespace: `trackbench::timing`

### Verification:
- Compiles cleanly with and without `-DTRACKBENCH_STAGE_TIMING`
- When disabled, zero overhead (no symbols, no code)

---

## Task 2: Instrument tracker.cpp step() with 11 stage timers

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to modify:
- `core/src/tracker.cpp` — instrument 11 stages in `step()` (dt, predict, build_active, cost_matrix_construct, association_solve, update, birth, coast_kill, compact, sort_emit, total)

### Requirements:
- Include `trackbench/timing.hpp`
- At top of `step()`, declare `std::array<uint64_t, trackbench::timing::StageTimings::COUNT> stage_ns{};` and `trackbench::timing::ScopedTimer timer(stage_ns);` (only when macro enabled)
- Wrap each logical stage in `timer.stage(trackbench::timing::StageTimings::<STAGE>)` calls
- Stage boundaries (matching the audit):
  1. `DT` — lines 16-24 (dt computation)
  2. `PREDICT` — lines 30-35 (EKF predict loop)
  3. `BUILD_ACTIVE` — lines 37-47 (active subset deep copy)
  4. `COST_MATRIX_CONSTRUCT` — lines 50-51 (call to `associate()` up to cost matrix build)
  5. `ASSOCIATION_SOLVE` — the Hungarian solve inside `associate()` 
  6. `UPDATE` — lines 56-65 (EKF update + mark_hit)
  7. `BIRTH` — lines 67-79 (new track creation)
  8. `COAST_KILL` — lines 81-87 (mark_miss loop)
  9. `COMPACT` — lines 90-94 (erase-remove)
  10. `SORT_EMIT` — lines 97-109 (sort + output deep copy)
  11. `TOTAL` — entire step (outermost)
- Store per-frame stage timings in a new member `std::vector<std::array<uint64_t, COUNT>> frame_timings_` on `Tracker` class (only when macro enabled)
- Provide a getter `const auto& frame_timings() const` for the main.cpp to access

### Verification:
- `make core` (timing OFF) → `make core-test` → golden test byte-identical PASS
- When enabled, each `frame_timings()` entry has COUNT elements summing to approximately total step time

---

## Task 3: Add --timing-csv flag to main.cpp

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to modify:
- `core/src/main.cpp` — `--timing-csv PATH` flag; when `TRACKBENCH_STAGE_TIMING=ON` and flag present, emit per-frame CSV rows

### Requirements:
- Add `--timing-csv PATH` to usage/help and argument parsing
- When flag provided AND `TRACKBENCH_STAGE_TIMING` is defined:
  - After tracking loop, open CSV file at PATH
  - Write header: `frame,scene_id,n_active,n_dets,dt_ns,predict_ns,build_active_ns,cost_matrix_construct_ns,association_solve_ns,update_ns,birth_ns,coast_kill_ns,compact_ns,sort_emit_ns,total_ns`
  - For each frame, write one row with frame index, scene_id (use frame number as scene_id for now), active track count, detection count, and each stage's nanoseconds from `tracker.frame_timings()`
  - Use `uint64_t` values, no decimal points
- When flag provided but `TRACKBENCH_STAGE_TIMING` is NOT defined:
  - Print warning to stderr: `"--timing-csv requires rebuild with -DTRACKBENCH_STAGE_TIMING=ON; no CSV emitted"`
  - Exit 0 (do not fail the run)
- Scene ID: for now use the frame's `frame` field; later can be enhanced

### Verification:
- Build without macro: `--timing-csv` prints warning, produces no file, exit 0
- Build with macro: `--timing-csv out.csv` produces valid CSV with correct columns

---

## Task 4: Add TRACKBENCH_STAGE_TIMING CMake option

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to modify:
- `core/CMakeLists.txt` — option `TRACKBENCH_STAGE_TIMING` default OFF; when ON, adds `-DTRACKBENCH_STAGE_TIMING` to compile defs

### Requirements:
- Add `option(TRACKBENCH_STAGE_TIMING "Enable per-stage timing instrumentation" OFF)` after `TRACKBENCH_BUILD_TESTS` option
- When ON, add `target_compile_definitions(trackbench PUBLIC TRACKBENCH_STAGE_TIMING)` and same for `trackbench_run` and `trackbench_tests`
- Ensure the option works with both Release and Debug builds

### Verification:
- `cmake -DTRACKBENCH_STAGE_TIMING=OFF` → builds without timing code
- `cmake -DTRACKBENCH_STAGE_TIMING=ON` → builds with timing code enabled

---

## Task 5: Add --timing-csv passthrough to bench_latency.py

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to modify:
- `scripts/bench_latency.py` — optional `--timing-csv` passthrough, keep existing `timing.json` behavior

### Requirements:
- Add `--timing-csv` argument to argparse (optional, default None)
- When provided, pass `--timing-csv <path>` to the `trackbench_run` subprocess
- The CSV file should be written alongside the existing `timing.json` in the temp directory
- After run, if `--json-out` is also specified, include the CSV path in the output JSON under a new key `timing_csv`
- Keep all existing behavior (p50/p99 from timing.json) unchanged

### Verification:
- `python3 scripts/bench_latency.py --timing-csv /tmp/test.csv` works
- JSON output still contains p50/p99/max from timing.json

---

## Task 6: Create capture_machine.py for machine.json

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to create:
- `scripts/capture_machine.py` — emits `bench/machine.json` (CPU, cores, RAM, compiler, CMake flags, OS)

### Requirements:
- Single script, no external deps beyond stdlib
- Outputs JSON to stdout or `--out PATH`
- Fields:
  - `cpu_model`: `sysctl -n machdep.cpu.brand_string` (macOS) or `/proc/cpuinfo` "model name" (Linux)
  - `cpu_cores_physical`: `sysctl -n hw.physicalcpu` (macOS) or `lscpu -p | grep -c '^[0-9]'` (Linux)
  - `cpu_cores_logical`: `sysctl -n hw.logicalcpu` (macOS) or `nproc` (Linux)
  - `ram_gb`: `sysctl -n hw.memsize` / 1e9 (macOS) or `grep MemTotal /proc/meminfo` (Linux)
  - `compiler`: `clang --version` first line (or `c++ --version`)
  - `cmake_flags`: read from `core/build/CMakeCache.txt` if exists, else empty
  - `os`: `platform.platform()`
  - `timestamp_iso`: `datetime.now().isoformat()`
- Handle missing commands gracefully (field = null with note)

### Verification:
- `python3 scripts/capture_machine.py --out bench/machine.json` produces valid JSON
- All fields populated on macOS

---

## Task 7: Create timing_summary.py for CSV analysis

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to create:
- `bench/timing_summary.py` — reads CSV, **discards first 5 frames per scene as warmup (explicit)**, computes p50/p95/p99/max per stage, outputs `bench/timing_summary.md` table

### Requirements:
- Input: CSV file from `--timing-csv` (path as arg)
- Group by `scene_id` (for now single scene)
- **Discard first 5 frames per scene as warmup** — explicitly state N=5 in output
- Compute percentiles using nearest-rank method: p50 = sorted[N/2], p95 = sorted[ceil(0.95*N)], p99 = sorted[ceil(0.99*N)], max = sorted[-1]
- Output markdown table to stdout and `--out PATH`:
  ```
  | Stage | p50_ns | p95_ns | p99_ns | max_ns |
  |-------|--------|--------|--------|--------|
  | DT | ... | ... | ... | ... |
  ...
  | TOTAL | ... | ... | ... | ... |
  ```
- Also output a summary line: `Warmup frames discarded: 5 per scene`

### Verification:
- Runs on the CSV from Task 3+5
- Produces correct percentiles matching manual check

---

## Task 8: Create test_timed_smoke.cpp for instrumentation test

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Files to create:
- `core/tests/test_timed_smoke.cpp` — runs 1 frame, asserts CSV row sum ≈ total_ns (5% tolerance), built only when `TRACKBENCH_STAGE_TIMING=ON`

### Requirements:
- Include `trackbench/tracker.hpp`, `trackbench/timing.hpp`, `trackbench/io.hpp`
- Only compiled when `TRACKBENCH_STAGE_TIMING` is defined (use `#ifdef` guard around entire test)
- Create a minimal synthetic frame with 5 detections
- Run `tracker.step(frame)`
- Get `frame_timings()` — should have 1 entry
- Sum all stage_ns except TOTAL, compare to TOTAL: `abs(sum - total) / total < 0.05`
- Also verify each stage_ns > 0 (timer actually fired)
- Use GoogleTest assertions

### Verification:
- `cmake -DTRACKBENCH_STAGE_TIMING=ON -DTRACKBENCH_BUILD_TESTS=ON` → `ctest` runs the test and passes
- Without the macro, test is not compiled (no error)

---

## Task 9: Verify: golden test + eval-fixture + overhead < 1%

**Phase 1 — Timing Instrumentation (compile-time removable)**

### Verification steps:
1. `make core` (default, timing OFF) → `make core-test` → golden test `Golden.SyntheticScene001ByteIdentical` PASS
2. `make eval-fixture` → gate PASS
3. `cmake -B core/build_timed -DTRACKBENCH_STAGE_TIMING=ON -DCMAKE_BUILD_TYPE=Release` → build
4. Run `bench-latency` with both builds (3 runs each), compare p99:
   - Baseline (no timing): `core/build/trackbench_run`
   - Instrumented: `core/build_timed/trackbench_run`
   - Overhead = (timed_p99 - baseline_p99) / baseline_p99
   - **Requirement: overhead < 1%** (report actual delta)
5. Commit `bench/timing.csv`, `bench/timing_summary.md`, `bench/machine.json` from the timed run
6. Update `RESULTS.md` with Phase 1 table (create if missing)

### Commit message format:
```
perf: add per-stage timing instrumentation — overhead <1% (N=100)
```

---

## Task 10: Phase 2 profiling (macOS xctrace + CI perf stat)

**Phase 2 — Profiling Baseline (macOS + CI Linux)**

### macOS (this machine):
- Run `xcrun xctrace record --instrument "Time Profiler" --launch -- ./core/build/trackbench_run --dets <dense_synthetic> --config core/config/default.json --out /dev/null --timing /dev/null`
- Run `xcrun xctrace record --instrument "CPU Counters" --launch -- ./core/build/trackbench_run ...` for cache refs/misses on predict + cost-matrix stages
- Export text trace → commit to `docs/bench/profile_synthetic_dense.txt`

### Linux (CI ubuntu-latest):
- Add a `profile` job to `.github/workflows/ci.yml` that runs `perf stat -e cycles,instructions,cache-references,cache-misses,branch-misses ./core/build/trackbench_run ...` on the dense synthetic, commits `docs/bench/perf_stat_synthetic.txt`

### Deliverable: `PROFILE.md` with ranked hotspots + hypotheses:
- Expected: `munkres` (n³ padded), `bev_oriented_iou` (5 allocs × gated pairs), `active` deep copies, `predict` AoS cache traffic
- Each with hypothesis: algorithmic / cache / allocation / branch

### Commit message format:
```
perf: add profiling baseline — top hotspot munkres (N=100)
```

---

## Task 11: Phase 3d - scratch buffer reuse (allocations)

**Phase 3 — Optimization (one commit each, gated by Phase 2)**

### Target: Per-frame allocations

### Method:
- Convert `active`, `active_idx`, `cost`, munkres arrays, matched flags, `matches`, output `FrameTracks` → `Tracker` member scratch buffers
- `reserve()` in `Tracker` constructor, `clear()` per frame
- Re-measure Phase-1 CSV; golden test PASS

### Gate:
- Re-measure Phase-1 CSV; golden test PASS

### Commit message format:
```
perf: reuse scratch buffers for active/cost/munkres — p99 14.2ms → 9.1ms (N=100)
```

---

## Task 12: Phase 3c - SoA covariance split

**Phase 3 — Optimization (one commit each, gated by Phase 2)**

### Target: AoS → SoA covariance

### Method:
- Split `Track::P` (200 B) into parallel `vector<StateMatrix, Eigen::aligned_allocator<...>>` 
- Predict/update operate on SoA buffer

### Gate:
- **Cache-miss rate before/after required**; if no material change → revert, document null

### Commit message format:
```
perf: SoA covariance split — p99 9.1ms → 7.8ms, cache-miss -23% (N=100)
```

---

## Task 13: Phase 3a - spatial prefilter

**Phase 3 — Optimization (one commit each, gated by Phase 2)**

### Target: Spatial prefilter

### Method:
- Uniform grid on predicted positions; gate candidate (i,j) before Mahalanobis
- **Bit-identical association outcomes mandatory**

### Gate:
- Scaling curve N=10/40/100/200 with/without; if outcomes differ → widen/revert

### Commit message format:
```
perf: spatial grid prefilter — p99 7.8ms → 5.2ms (N=200)
```

---

## Task 14: Phase 3b - assignment algorithm benchmark

**Phase 3 — Optimization (one commit each, gated by Phase 2)**

### Target: Assignment algorithm

### Method:
- JV/auction (`lap` or self-contained `lapjv`) vs current Munkres at N=10/40/100/200

### Gate:
- Only switch if ≥1.5× speedup at typical N (20–60) without output change

### Commit message format:
```
perf: benchmark JV vs Munkres — Munkres wins at N≤60, no switch (N=100)
```

---

## Task 15: Phase 3e - intra-frame parallelism

**Phase 3 — Optimization (one commit each, gated by Phase 2)**

### Target: Intra-frame parallelism

### Method:
- Thread pool for predict + cost-matrix construction; gated behind object-count threshold

### Gate:
- Speedup curve N vs serial; if never wins at typical N → leave out, document

### Commit message format:
```
perf: thread pool for predict/cost — p99 5.2ms → 3.8ms at N=200, no win at N≤60 (N=100)
```

---

## Phase 4–6 — Out of scope for this plan

Will be a separate plan after Phase 3 review, with the locked decisions:
- Phase 4: Ablation grid on **real nuScenes mini (1a)** — decompose 53% per finding
- Phase 5: AMOTA via **nuscenes-devkit adapter (2b)** + Pareto chart
- Phase 6: fp32/fp16 precision sweep (no fixed-point), determinism audit after 3e if it lands
## Task 16: Deferred review minors (polish batch)

**Phase 3 — Post-plan polish (user-authorized; one commit per item, gates still apply)**

The "Deferred review minors" list above, converted to code items. Line refs
verified at HEAD a271350:

1. `core/include/trackbench/timing.hpp` — add trailing newline (file currently
   ends without one; last byte is `h`).
2. `core/src/tracker.cpp:36` — `stage_ns` declared unconditionally but only used
   under `#ifdef TRACKBENCH_STAGE_TIMING`; guard the declaration and the `&stage_ns`
   call site (line 93) consistently.
3. `core/include/trackbench/tracker.hpp:43` / `core/src/tracker.cpp:179` —
   `frame_timings_` grows unbounded; cap it (keep a fixed recent window, e.g.
   last 4096 frames) with a comment.
4. `std::array<uint64_t, static_cast<size_t>(timing::StageTimings::COUNT)>`
   spelled ~7× across tracker.hpp/tracker.cpp/association.cpp — add a `StageNs`
   alias in `timing.hpp` and use it everywhere.
5. `core/src/main.cpp:136-155` — after `csv.close()` check the stream state for
   flush errors; bounds-guard `ft[i]` against `ft.size()` (loop to `ft.size()`).
6. `#ifdef` style: tracker.cpp wraps each timer in its own `#ifdef`, association.cpp
   uses a null-`timings` pointer pattern — make consistent where cheap, no behavior
   change. (Lowest priority; skip if it would be churn.)
7. `bench/timing_summary.py:91-95,111` — malformed/short CSV rows can raise a raw
   IndexError (sampled window) or be swallowed (warmup window). Validate row
   column count + int-parse all stage columns; raise a clear error naming the row.
8. `bench/timing_summary.py:14` — `EXPECTED_HEADER` vs the Task 3 producer
   (`core/src/main.cpp:138-144`): verify byte-match (verified by controller:
   they match) and add a comment stating the producer contract.

**Gate (unchanged):** after each commit, `make core-test` (golden byte-identical
must stay green) + `make eval-fixture` MOTA 0.9/IDS 0. Commit messages follow
repo style (`fix:`/`refactor:`/`chore:`, no `perf:` claims). No behavior change
to association output. Push when the batch is reviewed.
