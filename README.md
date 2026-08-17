# trackbench

**A small system for debugging multi-object tracking on real driving logs.**

Self-driving stacks need to know not only *what* is around the car, but *which* object is which over time. That second job is **tracking**: give each car/pedestrian a stable ID as frames roll by. When tracking fails, IDs swap, objects appear late, or ghost tracks show up — and a single score like "MOTA" rarely tells you *why*.

trackbench is an end-to-end loop that:

1. Takes **public** driving data + published detector boxes  
2. Runs a **classical** (non-neural) tracker in C++  
3. Scores it with standard MOT metrics (MOTA + AMOTA)  
4. **Mines** concrete failures (especially identity switches)  
5. Shows them in a **bird's-eye triage UI** with an interactive Pareto chart  
6. Lets you change the tracker, re-measure, and keep only real wins  
7. Gates regressions in CI  

**Headline results** on nuScenes mini (10 scenes):

| Metric | Baseline | Post003 (current) | Delta |
|--------|----------|-------------------|-------|
| IDS (identity switches) | 890 | **415** | **−53%** |
| MOTA | −1.351 | **+0.666** | +2.017 |
| AMOTA | 0.179 | **0.220** | +0.041 |
| p99 latency (Hungarian) | 0.531 ms | 0.132 ms | 4× faster |
| p99 latency (greedy) | — | **0.018 ms** | 29× faster |

12 findings across 13 phases — 5 wins, 7 honest nulls. No inflated claims.

<p align="center">
  <img src="docs/assets/triage-bev.png" alt="trackbench bird's-eye triage UI on a dense scene with an ID switch selected" width="900" />
</p>

<p align="center"><em>Bird's-eye triage UI — blue = ground truth, orange = tracker IDs. Selected failure explains <code>was track 3 → now track 2</code>.</em></p>

## What this is (for someone new)

| Term | Plain meaning |
|------|----------------|
| **Detection** | "In this frame, there is a car *here*." |
| **Tracking** | "That car is the *same* one as last frame — still ID 7." |
| **Ground truth (GT)** | The dataset's answer key for where objects really were. |
| **ID switch** | The answer-key object suddenly got a *different* tracker ID. |
| **MOTA** | Standard score: how often you're wrong (misses + false positives + ID swaps). |
| **AMOTA** | nuScenes metric: MOTA averaged over recall thresholds — better for ranking. |

This repo focuses on **tracking + evaluation + triage**. It does **not** train a neural detector.

Instead it uses **[Megvii / CBGS](https://www.nuscenes.org/data/detection-megvii.zip)** detections — a public zip of precomputed boxes released as an official [nuScenes](https://www.nuscenes.org/) tracking baseline. Think: someone else's "eyes," your "memory" (the tracker).

| Piece | Role |
|-------|------|
| **nuScenes `v1.0-mini`** | ~10 public driving scenes + ground-truth boxes |
| **Megvii detections** | Precomputed boxes + confidence scores (tracker inputs) |
| **Ingest** | Filter to tracking classes (score ≥ 0.3), merge Megvii train∪val for mini, write simple ego-frame JSONL |
| **C++ tracker** | Constant-velocity EKF + Hungarian/greedy matching — assigns IDs over time |
| **Eval / mine / UI** | Score (MOTA + AMOTA), list failures, cluster them, inspect in a top-down player |
| **Pareto chart** | Interactive AMOTA-vs-latency scatter in the triage UI |
| **Challenge export** | Convert tracker output to nuScenes tracking challenge CSV format |

Why Megvii: public, stable format, no detector training (project anti-goal). More detail: [docs/data.md](docs/data.md), [docs/decisions.md](docs/decisions.md).

**Data not included.** This repo ships code + tiny synthetic fixtures only. Download nuScenes mini and Megvii yourself under their terms; `data/raw/` and real normalized scenes are gitignored.

## How the loop works

```text
public data  →  ingest (JSONL)  →  C++ tracker  →  scores + failure list
                                                      ↓
                              CI gate ←  triage UI  ←  Postgres
                                   ↑
                           Pareto chart (AMOTA vs latency)
```

Typical workflow after a tracker change:

```bash
make core
./scripts/eval_all_scenes.sh --force   # must retrack; don't reuse old tracks.jsonl
# compare IDS / open UI on the new run
```

## Metrics (nuScenes `v1.0-mini`)

Same public setup for every finding: Megvii train∪val, 7 tracking classes, det score ≥ 0.3.

### CLEAR MOT metrics

| metric | baseline | after 001 | after 003 (current) |
|--------|----------|-----------|---------------------|
| Total IDS | 890 | ~618 | **415** (−53%) |
| MOTA | −1.351 | — | **+0.666** |
| densest scene `0655` IDS | 471 | ~326 | **216** |
| densest scene `0916` IDS | 384 | ~287 | **197** |

### AMOTA (nuScenes metric)

| config | AMOTA | AMOTP |
|--------|-------|-------|
| baseline | 0.179 | 1.645 |
| post001 | 0.225 | 1.582 |
| post003 (current) | **0.220** | 1.623 |

### Association solver (latency)

| solver | p99 ms (post003) | Accuracy vs Hungarian |
|--------|-------------------|----------------------|
| Hungarian (optimal) | 0.132 ms | baseline |
| Greedy | **0.018 ms** | identical on this data |
| Hybrid | 0.056 ms | identical on this data |

Greedy is the Pareto optimum: 7× faster than Hungarian with identical accuracy on the mini set.

### Per-class breakdown (post003)

| Class | GT count | IDS | FN | AMOTA |
|-------|----------|-----|----|-------|
| car | 3001 | 391 | 2759 | 0.215 |
| truck | 398 | 24 | 386 | 0.367 |
| pedestrian | 360 | 0 | 360 | n/a |
| bicycle | 2 | 0 | 2 | n/a |
| bus | 6 | 0 | 6 | n/a |

The tracker is effectively a **car tracker** — pedestrians, bicycles, and buses are 100% missed. This is honest and expected for a classical tracker with a single motion model.

## Findings

| # | Finding | Outcome | Details |
|---|---------|---------|---------|
| [001](docs/findings/001-dense-id-switch-velocity-gate.md) | Velocity gate cuts IDS | **Win** — IDS 890 → ~618 | Prefer motion-consistent matches |
| [002](docs/findings/002-bev-iou-association.md) | BEV IoU in matching cost | **Null** — IDS unchanged | Not a lever |
| [003](docs/findings/003-harder-birth-score.md) | Higher birth threshold (0.5 → 0.7) | **Win** — IDS 619 → 415 | Fewer weak tracks born |
| [004](docs/findings/004-amota-vs-mota-ranking.md) | AMOTA vs MOTA rank differently | **Honest** — different configs win | MOTA is car-dominated |
| [005](docs/findings/005-precision-not-a-lever.md) | double ≡ float precision | **Null** — no lever | float sufficient |
| [006](docs/findings/006-ctrv-motion-model.md) | CTRRV motion model | **Null** — CV better everywhere | Turn-rate doesn't help on mini |
| [007](docs/findings/007-greedy-association.md) | Greedy association solver | **Win** — 7–19× faster, ΔAMOTA ±0.001 | First Pareto point |
| [008](docs/findings/008-full-val-preliminary.md) | Full nuScenes val split | **Ready** — pipeline exists | Awaits ~850 GB download |
| [009](docs/findings/009-pareto-ui.md) | Interactive Pareto chart | **Win** — AMOTA-vs-latency scatter | In the triage UI |
| [010](docs/findings/010-hybrid-association.md) | Hybrid greedy+Hungarian | **Null** — hybrid = greedy | Can't fix committed mistakes |
| [011](docs/findings/011-per-class-breakdown.md) | Per-class AMOTA/IDS | **Honest** — car tracker only | Pedestrians invisible |
| [012](docs/findings/012-challenge-export.md) | Challenge CSV export | **Win** — production-ready output | Verifiable by anyone |

Overall accuracy (MOTA) is still mid/weak on crowded scenes — expected for a simple classical tracker. The point of this project is the **mined ID-switch cut**, the **honest ablations**, and the **triage loop**, not topping a leaderboard.

## Architecture

```mermaid
flowchart LR
  ingest[ingest JSONL] --> core[core CV-EKF tracker]
  core --> eval[eval CLEAR MOT + AMOTA]
  eval --> mine[mine + cluster]
  mine --> pg[(Postgres)]
  pg --> api[API]
  api --> web[web BEV triage]
  api --> pareto[pareto chart]
  eval --> ci[CI gate]
  core --> ci
  core --> export[challenge CSV]
```

<p align="center">
  <img src="bench/ablation/pareto.svg" alt="AMOTA vs latency Pareto chart across 24-cell ablation grid" width="700" />
</p>

<p align="center"><em>AMOTA-vs-latency Pareto chart — each dot is one config from the 24-cell ablation grid. Hover for details in the triage UI.</em></p>

Components: [docs/architecture.md](docs/architecture.md). Locked choices: [docs/decisions.md](docs/decisions.md).

## Quick start

```bash
cp .env.example .env

# Tracker + tests
make core && make core-test

# Synthetic scene (no 4GB download)
make demo

# Metrics + mine on golden fixture
make eval-fixture

# API + UI (needs Docker Postgres)
make up && make migrate
cd api && npm ci && npm run build
DATABASE_URL='postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public' \
  FIXTURES_ROOT=$PWD/../data/fixtures node dist/index.js &
curl -s localhost:3001/demo/bootstrap
cd ../web && npm ci && npm run dev
# open http://localhost:5173
```

If Homebrew Postgres already owns port 5432, stop it before `make up` (or remap Docker to 5433). See [docs/mini-ui.md](docs/mini-ui.md).

### Real mini (the numbers above)

```bash
python scripts/merge_megvii_mini.py
PYTHONPATH=. python -m ingest.nuscenes_ingest --force
make core
./scripts/eval_all_scenes.sh --force   # retrack after config changes

PYTHONPATH=. python -m eval.write_run --mine --write-db --notes "mini after finding 003"
# start API with NORMALIZED_ROOT + TRACKS_ROOT — docs/mini-ui.md
```

Details: [docs/data.md](docs/data.md).

### Association ablation sweep

```bash
# 5 configs × {hungarian, greedy, hybrid} × 2 runs
python3 scripts/ablate_assoc.py --force
# → bench/assoc/sweep.json, bench/assoc/SWEEP.md
```

### Per-class breakdown

Per-class AMOTA/IDS/FN are automatically persisted when running `write_run --write-db`. The RunDetail page shows the per-class table when data is available.

### Challenge CSV export

```bash
python3 scripts/export_challenge.py --all --out submission.csv
# → challenge-format CSV for all 10 scenes (7,340 rows)
```

## Latency

`trackbench_run --timing PATH` writes per-frame wall ms. Reference numbers:

| workload | p50 | p99 | hardware |
|----------|-----|-----|----------|
| Dense synthetic (100 frames × 40 dets) | ~0.032 ms | ~0.047 ms | Linux x86_64 Xeon |
| Real scene `0655` (Hungarian) | — | 0.132 ms | macOS Apple Silicon |
| Real scene `0655` (greedy) | — | **0.018 ms** | macOS Apple Silicon |

The greedy solver is the Pareto optimum: 7× faster than Hungarian with identical accuracy on the mini set.

```bash
make bench-latency
# or on a real scene:
core/build/trackbench_run \
  --dets data/normalized/scene-0655/detections.jsonl \
  --config core/config/default.json \
  --out /tmp/tracks.jsonl \
  --timing /tmp/timing.json
```

## What I'd do next

1. **Full nuScenes val split** — download v1.0-trainval (~850 GB), run `scripts/eval_val.py` on ~35 scenes for statistical power. Pipeline ready, awaits data.
2. **Adaptive birth score** — per-class or per-scene thresholds to improve pedestrian recall without degrading car IDS.
3. **Camera+LiDAR fusion** — the tracker is LiDAR-only; camera detections have higher recall for pedestrians/cyclists.

## Layout

```
core/       C++17 tracker (EKF + Hungarian/greedy/hybrid + lifecycle), GoogleTest + golden
ingest/     nuScenes → ego-frame JSONL (--synthetic for offline demo)
eval/       MOT scores (MOTA + AMOTA), failure mining, clustering, CI gate
api/        Express + Prisma (REST endpoints: runs, pareto, clusters)
web/        React triage UI + Canvas 2D bird's-eye player + interactive Pareto chart
scripts/    eval_all_scenes.sh, ablate_assoc.py, ablate_ctrv.py, eval_val.py,
            export_challenge.py, bench_latency.py, merge_megvii_mini.py
data/fixtures/   tiny synthetic scene for CI / demo (not the full dataset)
baselines/baseline.json   CI metric floor
docs/findings/            experiment writeups 001–012
docs/bench/               latency reference JSON
docs/assets/              README screenshot
```

## Milestones

| Milestone | Status |
|-----------|--------|
| M0 Skeleton | done |
| M1 Tracker v0 | done (golden byte-identical) |
| M2 Metrics | done |
| M3 Failure mining | done (rule clusters) |
| M4 Triage UI | done (demo + real mini scenes) |
| M5 CI gate | done (synthetic fixture floor) |
| M6 Findings 001–003 | done — velocity gate win, IoU null, birth score win |
| M7 AMOTA | done — nuScenes metric, 40-point recall curve |
| M8 CTRRV | done — honest null, CV better everywhere |
| M9 Greedy association | done — 7–19× faster, first Pareto point |
| M10 Full val pipeline | done — `eval_val.py` ready, awaits data download |
| M11 Pareto UI | done — interactive AMOTA-vs-latency scatter |
| M12 Per-class + export | done — car tracker revealed, challenge CSV ready |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`). Honest nulls published alongside wins.

## License

Code and docs in this repository are [MIT](LICENSE). nuScenes and Megvii data remain under their upstream licenses/terms — obtain them from the official sources; they are not redistributed here.
