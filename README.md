# trackbench

Run a deterministic CV-EKF tracker on logged driving data, mine failures, cluster them into bugs, and gate every change on regression.

> **Status (M0–M6 complete):** End-to-end loop — ingest → C++ tracker → CLEAR MOT → failure mining → rule clusters → triage UI → CI gate. Real nuScenes mini + Megvii detections supported. Findings [001](docs/findings/001-dense-id-switch-velocity-gate.md) + [003](docs/findings/003-harder-birth-score.md) cut mini IDS **890 → 415**.

Scene player screenshots: see PR / [docs/architecture.md](docs/architecture.md). No demo GIF checked in yet.

## Metrics (mini — stacked findings)

nuScenes `v1.0-mini` (10 scenes), Megvii train∪val, tracking classes, det score ≥ 0.3.

| metric | pre-001 | post-001 | post-003 (`min_birth_score=0.7`) |
|--------|---------|----------|----------------------------------|
| Total CLEAR-MOT IDS | 890 | ~618 | **415** (−53% vs pre-001) |
| scene-0655 IDS | 471 | ~326 | **216** |
| scene-0916 IDS | 384 | ~287 | **197** |

Writeups: [001](docs/findings/001-dense-id-switch-velocity-gate.md) (velocity + birth 0.5), [002](docs/findings/002-bev-iou-association.md) (IoU null), [003](docs/findings/003-harder-birth-score.md) (birth 0.7). MOTA still weak on dense scenes; deliverable is the mined ID-switch cut.

## Architecture

```mermaid
flowchart LR
  ingest[ingest JSONL] --> core[core CV-EKF tracker]
  core --> eval[eval CLEAR MOT]
  eval --> mine[mine + cluster]
  mine --> pg[(Postgres)]
  pg --> api[API]
  api --> web[web BEV triage]
  eval --> ci[CI gate]
  core --> ci
```

Components: [docs/architecture.md](docs/architecture.md). Locked choices: [docs/decisions.md](docs/decisions.md).

## Quick start

```bash
cp .env.example .env

# Tracker + tests
make core && make core-test

# Synthetic scene (no 4GB download)
make demo
# or: python -m ingest.nuscenes_ingest --synthetic --force

# Metrics + mine
PYTHONPATH=. python -m eval.run_eval \
  --gt data/fixtures/synthetic_scene_001/gt.jsonl \
  --tracks data/fixtures/synthetic_scene_001/tracks_expected.jsonl \
  --scene-meta data/fixtures/synthetic_scene_001/scene_meta.json \
  --scene-id synthetic_scene_001 --mine

# Regression gate
PYTHONPATH=. python -m eval.gate

# API + UI
make up && make migrate
cd api && npm ci && npm run build
DATABASE_URL=postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public \
  FIXTURES_ROOT=$PWD/../data/fixtures node dist/index.js &
curl -s localhost:3001/demo/bootstrap
cd ../web && npm ci && npm run dev
# open http://localhost:5173
```

### Real mini

Download nuScenes mini + Megvii detections, merge train∪val, ingest, track, eval:

```bash
python scripts/merge_megvii_mini.py
PYTHONPATH=. python -m ingest.nuscenes_ingest --force
./scripts/eval_all_scenes.sh

# Load into triage UI (Postgres)
PYTHONPATH=. python -m eval.write_run --mine --write-db --notes "mini M6"
# see docs/mini-ui.md for NORMALIZED_ROOT / TRACKS_ROOT when starting the API
```

Details: [docs/data.md](docs/data.md), [docs/mini-ui.md](docs/mini-ui.md).

## Latency

`trackbench_run --timing PATH` emits per-frame wall ms in `timing.json`. Measure on your machine (p50 / p99 from `ms_per_frame`); no reference hardware numbers checked in yet. CI can gate on p99 when a baseline is set (`baselines/baseline.json`).

## What I'd do next

1. **Finding [003](docs/findings/003-harder-birth-score.md) shipped** — `min_birth_score` 0.5→0.7 cut IDS 619→415; re-load UI via `write_run --mine --write-db`.
2. **Per-class coast / birth** — pedestrians vs cars; LATE_INIT / FN residual.
3. **Optional:** tentatives out of Hungarian until `promote_hits` (if dense IDS remain after triage).

## Layout

```
core/       C++17 CV-EKF tracker (Hungarian + lifecycle), GoogleTest + golden
ingest/     nuScenes → ego-frame JSONL (--synthetic for offline demo)
eval/       CLEAR MOT, failure mining, rule clustering, CI gate
api/        Express + Prisma
web/        React triage UI + Canvas 2D BEV player
data/fixtures/   committed synthetic scene + demo_bundle.json
baselines/baseline.json   CI metric floor
docs/decisions.md         locked design choices
docs/findings/            M6 writeups
docs/architecture.md      component map
docs/data.md              real mini + Megvii merge
```

## Milestones

| Milestone | Status |
|-----------|--------|
| M0 Skeleton | done |
| M1 Tracker v0 | done (golden byte-identical) |
| M2 Metrics | done |
| M3 Failure mining | done (rule clusters) |
| M4 Triage UI | done (demo bootstrap) |
| M5 CI gate | done (synthetic fixture floor) |
| M6 Finding writeup | done — [001](docs/findings/001-dense-id-switch-velocity-gate.md) |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).
