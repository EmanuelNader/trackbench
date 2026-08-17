# Phase 8 — Greedy Association (latency Pareto point)

> STATUS: DONE — commits 46315c1, cfb19e7, 5443d3b.
> Result in `docs/findings/007` and `bench/assoc/sweep.{json,md}`: greedy
> solver delivers 6.6–19× p99 speedup with negligible accuracy trade-off.
> The `assoc_mode` knob ("hungarian" default, "greedy" option) lives in
> `TrackerConfig`; `default.json` unchanged; 24-cell grid untouched.

## Why

The current association is an O(n³) Hungarian (Munkres) solver over the full
gated cost matrix. On the 10-scene mini the Hungarian is already fast
(~0.5 ms/frame), but the solver's latency is measurable and dominates the
association stage. A **greedy matcher** (sort all finite-cost pairs, greedily
assign the cheapest) runs in O(n² log n) for the sort + O(n²) for the greedy
pass — and on small grids (30–60 active tracks × 30–60 detections) the constant
factor is much lower than Munkres. This phase tests: **does the greedy matcher
trade accuracy for a measurable latency speedup?** — and plots the Pareto
point on the AMOTA-vs-p99 chart.

The null (greedy ≈ Hungarian accuracy) is as interesting as a positive result,
because it would mean the tracker can switch to the cheaper solver without
losing anything.

## Decisions

- **Config-driven toggle**: `TrackerConfig.assoc_mode` (`"hungarian"` default,
  `"greedy"` option). Loader tolerates missing keys → default.json unchanged,
  no committed cell configs touched, 24-cell grid unchanged.
- **Cost matrix build is shared** between modes (lines 406–521 of
  `association.cpp`); only the solver call changes. This means the
  `COST_MATRIX_CONSTRUCT` timing is identical for both modes.
- **Greedy algorithm** (deterministic, reproducible):
  1. Collect all (i,j) with finite cost (cost[i][j] < kCostInf * 0.5).
  2. Sort by cost ascending (ties broken by track index, then detection index —
     matching the existing `stable_sort` convention at line 551).
  3. Iterate: assign (i,j) if both track i and detection j are still unassigned.
  4. Result stored in `scratch.assignment` (same format as Hungarian output).
- **Same post-processing** (Inf rejection, stable sort of matches) applies to
  both modes — no downstream changes.
- **Per-stage timing**: the greedy solver is timed into `ASSOCIATION_SOLVE`
  (same stage as Hungarian), so p99 latency is directly comparable.
- **Binding gate**: `"hungarian"` mode byte-identical (golden + post003 +
  summarize).

## Files to touch

- `core/include/trackbench/types.hpp` (TrackerConfig): add
  `std::string assoc_mode = "hungarian"`.
- `core/src/io.cpp` (load_config): add `extract_string(body, "assoc_mode", cfg.assoc_mode)`.
- `core/src/association.cpp`: new `greedy_solve(AssociateScratch&)` function;
  branch in `associate_to()` after the cost-matrix timer block — call
  `greedy_solve(scratch)` when `cfg.assoc_mode == "greedy"`, else
  `munkres_scratch(scratch)` (current code, verbatim).
- `core/tests/test_association.cpp` (new): greedy assignment on a simple
  cost matrix, determinism check.
- `core/config/default.json`: unchanged.

## Tasks

### Task 1: Greedy association solver (core)
- Implement: TrackerConfig `assoc_mode`, `extract_string`, `greedy_solve()`,
  branch in `associate_to()`.
- Tests: greedy assignment correctness (small cost matrix with known optimal),
  greedy determinism, golden byte-identical (hungarian mode).
- **Gate**: `make core-test` all pass; post003 re-run → eval/summary/amota
  byte-identical; summarize byte-identity; one greedy scene-0655 end-to-end.
- Commit: `feat(core): greedy association solver (config toggle, Hungarian default byte-identical)`

### Task 2: Greedy vs Hungarian experiment
- `scripts/ablate_assoc.py`: 5 configs × {hungarian, greedy} × 2 runs; MOTA/IDS/AMOTA/AMOTP + pooled p99; determinism audit; bench/assoc/sweep.json + SWEEP.md.
- **Gate**: determinism 10/10 PASS; Hungarian matches committed cells; honest accuracy/latency deltas.
- Commit: `bench: greedy vs Hungarian association (solver ablation)`

### Task 3: Finding 007
- `docs/findings/007-greedy-association.md`: honest measurement story (greedy is faster? accuracy trade-off?); config knob documented; Pareto point on AMOTA-vs-p99.
- Commit: `docs: association finding 007 (greedy vs Hungarian)`

## Out of scope

- Full nuScenes val, triage UI, any change to the 24-cell grid, CTRRV, the EKF, eval scripts, or committed cell outputs.

## Gate

Default ("hungarian") byte-identical. Greedy configs are ad-hoc. Sweep never writes into data/normalized. All sweep numbers machine-derived.
