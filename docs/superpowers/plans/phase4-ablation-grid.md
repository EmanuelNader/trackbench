# Phase 4 — Ablation Grid on Real nuScenes mini

> STATUS: DONE — merged via PR #10 (commits f7f3db2, aebc041, 0117919, 2a1dbce,
> 2e8c013). The 24-cell grid, `scripts/ablate.py`, `bench/ablation/summarize.py`,
> and the landmark gate all live in `bench/ablation/`; results in
> `bench/ablation/RESULTS.md` and `docs/findings/003`.

Decompose the headline **IDS 890 → 415 (−53%)** into per-component contributions
via a config-file-driven ablation grid on the real nuScenes mini scenes, with
one command that reruns everything and auto-regenerates the results table.

Supersedes `phase1-3-perf-rigor.md`'s "Phase 4–6" note. Phase 3's constraints
still bind for everything here (no fabricated numbers, one change per commit,
report negative results, no style refactors, ask before large structural
changes).

## Global Constraints (binding)

1. **All ablation numbers come from real runs** — the committed results table is
   machine-generated output, never hand-edited. If a config didn't run, say so.
2. **One command reproduces the whole grid** — `python scripts/ablate.py` runs
   every config in the manifest across all scenes and regenerates RESULTS.md.
3. **Configurations declared in a manifest file (TOML)**, never hardcoded in
   scripts.
4. **Identical conditions across the matrix**: single Release tracker binary,
   `seed: 0` constant, same `NORMALIZED_ROOT`, pinned Python deps, explicit
   split recorded in the manifest header.
5. **Determinism check** — the tracker is deterministic (no RNG); each config's
   tracks must be bit-identical across reruns. Reuse the existing synthetic
   golden gate for the tracker; the sweep adds a real-data determinism check.
6. **Report negative results** — null components (expected: BEV IoU) stay in the
   table with their measured Δ.
7. **Accuracy hard constraint** — the stacked sequence must reproduce the
   documented landmarks (≈890 → ≈618/619 → ≈415). If a landmark drifts, the
   sweep must stop and report the drift (data/manifest mismatch), not paper over
   it.
8. **Scope guard** — implementing new tracker features to add sweep dimensions
   (greedy/JV association, CTRV) is OUT of scope here; the grid covers the
   implemented knobs only.

---

## Current state (verified at plan time, HEAD a271350)

- Real data fully ingested locally: `data/raw/nuscenes/v1.0-mini/` (10 scenes),
  Megvii detections `data/raw/detections/megvii_mini_merged.json`
  (+ megvii_train/val/test splits), normalized scenes under `data/normalized/`
  (scene-0061 … scene-1100, each with `detections.jsonl`, `gt.jsonl`,
  `scene_meta.json`), prior run artifacts under `data/tracks/`.
- **Baseline reproduces exactly**: current `data/tracks/*_eval.json` sum to
  TOTAL IDS = 415 and match the per-scene table in
  `docs/findings/003-harder-birth-score.md` (0655 = 216, 0916 = 197). So the
  existing normalized data was produced from the right detections and the
  post-003 config.
- Per-config runner exists: `scripts/eval_all_scenes.sh` (`CONFIG`,
  `NORMALIZED_ROOT`, `TRACKS_OUT_ROOT`, `TRACKER_BIN`, `PYTHON` env vars; runs
  tracker + CLEAR-MOT eval + failure mining per scene; prints per-scene +
  TOTAL IDS/MOTA summary). Per-scene metrics land in `data/tracks/<scene>_eval.json`.
- Tracker config is a single JSON read at runtime (`--config`), keys:
  `promote_hits`, `coast_frames`, `gate_m`, `gate_mahalanobis`,
  `vel_cost_weight`, `vel_gate_min_speed`, `vel_gate_lateral_m`, `iou_weight`,
  `min_birth_score`, `process_*`, `meas_var_*`, `seed`. Current default.json is
  the post-003 state.
- The findings stack (from the docs) — the sequence the grid must decompose:
  - **B0** (pre-001): gate_m 2.0, vel_cost 0, iou 0, min_birth_score 0 → IDS 890
  - **+001** (vel cost + gate_m 1.5 + birth 0.5) → IDS 618
  - **+002** (iou_weight 2.0) → IDS 619 (null, −1)
  - **+003** (birth 0.5 → 0.7) → IDS 415
- Python deps are un-pinned (ranges in `pyproject.toml`/`requirements.txt`).
  The eval stack (`eval/` + `scripts/`) imports stdlib + numpy + pyquaternion.
- Tracker has only the Hungarian association and CV motion model — the "association
  algorithm" and "motion model" sweep dimensions of the original Phase 4 spec are
  NOT implementable without new features → excluded, documented in the manifest.

## Grid definition (the manifest)

Full factorial over the four implemented knobs, everything else constant at
post-003 values (gate_mahalanobis 9.21, promote_hits 3, coast_frames 5,
vel_gate_min_speed 1.0, vel_gate_lateral_m 1.0, seed 0):

| knob | levels | meaning |
|------|--------|---------|
| `gate_m` | 2.0, 1.5 | gating tightness (001 component) |
| `vel_cost_weight` | 0.0, 4.0 | motion-consistency cost (001 component) |
| `iou_weight` | 0.0, 2.0 | BEV IoU association term (002, expected null) |
| `min_birth_score` | 0.0, 0.5, 0.7 | birth gating / lifecycle (001 + 003 components) |

24 config cells, each defined in the TOML manifest. Named reference cells
(decoded from the manifest, not hardcoded): `baseline` (2.0/0/0/0.0),
`post001` (1.5/4.0/0/0.5), `post002` (1.5/4.0/2.0/0.5), `post003`/`current`
(1.5/4.0/2.0/0.7).

The decomposition is read out two ways:
- **Marginal**: each knob flipped alone off `baseline` (its standalone Δ).
- **Stacked**: B0 → +vel → +gate_m → +birth0.5 → +iou → +birth0.7 in the
  finding order (attributes each finding's incremental Δ and surfaces
  interactions, e.g. birth behaving differently alone vs in the stack).

---

## Tasks

### Task 1: Reproducibility pinning (manifest + deps)
**Target:** the sweep runs on identical conditions every time.
**Method:**
- Pin the eval-stack Python deps to exact versions (the stack is stdlib +
  `numpy` only; `pyquaternion`/`scipy` are ingest/devkit concerns not imported
  by `eval/` or `scripts/`) in `requirements.lock` (or exact pins in
  `requirements.txt`), and record `python --version` in the manifest.
- Add a README-style header in the manifest recording the split: nuScenes
  v1.0-mini, detections = Megvii **train∪val merged**
  (`megvii_mini_merged.json`), 7 tracking classes, ingest score filter ≥ 0.3,
  `NORMALIZED_ROOT=data/normalized`, tracker build = Release
  (`TRACKBENCH_STAGE_TIMING=OFF`, `-O3`), `seed: 0`.
- Verify `.env`'s `DETECTIONS_JSON` points at the merged file (currently
  `megvii_val.json`) or document why val-only is the intended source; the
  normalized data demonstrably reproduces the 415 baseline, so resolve the
  discrepancy without re-ingesting unless the sweep fails to reproduce.
**Gate:** a fresh `pip install -r requirements.lock` in a clean venv runs the
sweep deterministically; the manifest records everything needed to identify the
exact inputs. No behavior change.
**Commit format:** `chore: pin eval deps + record Phase 4 sweep manifest header`

### Task 2: Ablation manifest (TOML)
**Target:** every grid config declared once, machine-readable.
**Method:** `bench/ablation/manifest.toml` with (a) header (split/det
source/classes/score/build/seed per Task 1), (b) named reference cells, (c) the
24-cell grid as knob-level combinations referencing a `defaults` block, (d)
expected landmarks (890/618/619/415) with their source finding doc.
**Gate:** the manifest parses and materializes exactly 24 unique configs; the
four named reference cells exist and map onto the expected knob levels.
**Commit format:** `feat: define Phase 4 ablation manifest (24-cell grid)`

### Task 3: Sweep runner (`scripts/ablate.py`)
**Target:** one command runs the whole matrix on all 10 scenes.
**Method:** `python scripts/ablate.py [--config manifest] [--only <cell>...]`
- For each cell: write a temp `config.json` (from defaults + knobs), invoke the
  existing `scripts/eval_all_scenes.sh` with `CONFIG=...`,
  `TRACKS_OUT_ROOT=bench/ablation/out/<cell>/` (isolated per cell so cells
  never share track outputs), collect the per-scene `*_eval.json`.
- Determinism: rerun one cell twice and assert tracks bit-identical.
- Reuse (do not fork) the eval/aggregation already in `eval_all_scenes.sh`; the
  script orchestrates, it does not re-implement CLEAR-MOT.
- `--only` lets a single cell be rerun quickly during development.
**Gate:** running the full matrix on the 10 scenes completes end-to-end; outputs
land per-cell under `bench/ablation/out/`; per-cell TOTAL IDS matches the
eval_all_scenes summary.
**Commit format:** `feat: add ablation sweep runner (one command, full matrix)`

### Task 4: Attribution + RESULTS generator
**Target:** the decomposition table is auto-generated, never hand-edited.
**Method:** `bench/ablation/summarize.py` reads `bench/ablation/out/`, the
manifest landmarks, and writes:
- per-cell table (total + per-scene IDS, MOTA, n_failures),
- **marginal** table (each knob alone vs `baseline`: ΔIDS, ΔMOTA),
- **stacked** table (B0 → final in finding order with incremental Δ and
  expected-vs-measured column vs the landmarks),
- interaction notes computed by the script (e.g. the difference between a
  knob's marginal and in-stack contribution).
- Emits a regenerated `bench/ablation/RESULTS.md` section.
**Gate:** running `summarize.py` on a stale `out/` dir is reproducible (byte-
identical RESULTS.md); the table covers all 24 cells; every number traces to a
cell output file.
**Commit format:** `feat: auto-generate ablation attribution table (marginal + stacked)`

### Task 5: Run the grid and commit the decomposition
**Target:** the 53% decomposed per component, measured on real mini.
**Method:** run `scripts/ablate.py` (full 24 × 10), run `summarize.py`, verify
the stacked sequence reproduces the landmarks. Analysis text (the finding-style
writeup in `bench/ablation/RESULTS.md` §Analysis) must draw only from the table
and the failure clusters already produced per cell.
**Gate (binding):**
- Stacked sequence lands within tolerance of the documented landmarks
  (890 ±20 → ≈618/619 ±20 → 415 ±20). If a landmark is off, STOP and report
  (data/manifest mismatch) — do not adjust numbers.
- 002/IoU shows ~0 contribution (reproducing the null) — if it suddenly wins,
  report as a new finding, don't suppress.
- Commit the manifest, runner, summarizer, cell outputs (aggregate only, not
  240 intermediate track files), and RESULTS.md.
**Commit format:** `bench: 24-cell ablation grid on mini — IDS 890→415 decomposed per component (N=10 scenes)`

---

## Out of scope (explicit)

- Phase 5 (AMOTA via nuscenes-devkit `Track::score` + Pareto chart) — separate plan.
- Phase 6 (fp32/fp16 precision sweep) — separate plan.
- New tracker features as sweep dimensions: greedy/JV association, CTRV motion
  model. Adding them is a feature plan, not an ablation.
- Re-running the Megvii ingest unless Task 1's verification requires it.

## Risks / notes

- **Interaction non-linearity**: the findings stacked non-additively (001's
  three components were measured as one stack). The marginal-vs-stacked split is
  precisely why the full factorial (not just the finding sequence) is run.
- **Data drift**: if the normalized scenes ever get regenerated from a different
  det source, the landmarks will move; the manifest header + the landmark
  assertion in Task 5 catch it.
- **Cost**: 24 cells × 10 scenes ≈ minutes on a laptop (per-scene tracker run is
  sub-second; CLEAR-MOT eval dominates). The grid is host-local, not CI.
