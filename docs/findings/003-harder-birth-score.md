# 003 — Harder birth score cuts residual ID churn

## What the system surfaced

After [001](001-dense-id-switch-velocity-gate.md) (soft velocity + `gate_m=1.5` +
`min_birth_score=0.5`) and a null [002](002-bev-iou-association.md) (BEV IoU),
triage on `scene-0655` / `scene-0916` still showed dense `ID_SWITCH` clusters.
UI review pointed at **birth/steal churn** more than parallel-box swaps: new
tracks appear and briefly claim a GT, then drift.

## Hypothesis

`min_birth_score=0.5` still lets medium-confidence unmatched dets birth
tentative tracks in dense frames. Those tentatives compete in Hungarian and
steal identities. Raising the birth floor should cut churn without a hard
association reject (hard gates previously hurt IDS).

## Experiment

Single knob: `min_birth_score` **0.5 → 0.7** in `core/config/default.json`.
Retrack with a clean `tracks.jsonl` wipe (or `./scripts/eval_all_scenes.sh --force`).

## Before / after (10-scene mini CLEAR MOT)

| | post-002 (0.5) | post-003 (0.7) | Δ |
|--|----------------|----------------|---|
| Total IDS | 619 | **415** | **−204 (−33%)** |
| Total n_failures | 1399 | **1062** | −337 |
| scene-0655 IDS | 327 | **216** | −111 |
| scene-0916 IDS | 287 | **197** | −90 |

### Per-scene after 0.7

| scene | MOTA | IDS | n_failures |
|-------|------|-----|------------|
| scene-0061 | 0.123 | 0 | 26 |
| scene-0103 | 0.084 | 0 | 79 |
| scene-0553 | 0.176 | 0 | 24 |
| scene-0655 | -0.080 | 216 | 383 |
| scene-0757 | 0.131 | 1 | 27 |
| scene-0796 | 0.102 | 0 | 38 |
| scene-0916 | -0.126 | 197 | 365 |
| scene-1077 | 0.048 | 0 | 55 |
| scene-1094 | 0.093 | 1 | 39 |
| scene-1100 | 0.115 | 0 | 26 |

MOTA improved on several scenes (including 0655/0916/1100) — not just an
IDS-only tradeoff.

## Cumulative vs pre-001

| stage | Total IDS |
|-------|-----------|
| Pre-001 (class filter only) | 890 |
| Post-001 (`min_birth_score=0.5` + vel soft) | ~618 |
| Post-002 (IoU) | 619 |
| **Post-003 (`min_birth_score=0.7`)** | **415** |

Overall **890 → 415 (−53%)** on mini CLEAR-MOT IDS.

## Conclusion

**Ship `min_birth_score=0.7`.** Matches the triage hypothesis that residual
switches were birth-driven. Use `--force` (or delete `tracks.jsonl`) when
ablating config so eval does not re-score stale tracks.

## What I'd do next

1. Per-class birth / coast (ped vs car) for remaining LATE_INIT / FN.
2. Optional: exclude tentatives from Hungarian until `promote_hits`.
3. Re-`write_run --mine --write-db` and spot-check 0655 switches in the UI.
