# trackbench

A miniature AV data engine: run a tracker over logged driving data, automatically find where it fails, cluster those failures into real bugs, and gate every future change on regression.

> **Status (M0–M5 early):** End-to-end loop on a synthetic fixture — ingest → deterministic C++ tracker → CLEAR MOT → failure mining → rule clusters → triage UI → CI regression gate. Real nuScenes mini + Megvii detections are wired in ingest but not required to demo. M6 finding writeup still ahead.

## Quick start

```bash
cp .env.example .env

# Tracker + tests
make core && make core-test

# Synthetic scene (no 4GB download)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ingest.nuscenes_ingest --synthetic --force
cat data/fixtures/synthetic_scene_001/detections.jsonl | head

# Metrics + mine
PYTHONPATH=. python -m eval.run_eval \
  --gt data/fixtures/synthetic_scene_001/gt.jsonl \
  --tracks data/fixtures/synthetic_scene_001/tracks_expected.jsonl \
  --scene-meta data/fixtures/synthetic_scene_001/scene_meta.json \
  --scene-id synthetic_scene_001 --mine

# Regression gate
PYTHONPATH=. python -m eval.gate

# API + UI (Postgres: docker compose up -d && make migrate)
cd api && npm ci && npx prisma migrate deploy && npm run build
DATABASE_URL=postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public \
  FIXTURES_ROOT=$PWD/../data/fixtures node dist/index.js &
curl -s localhost:3001/demo/bootstrap
cd ../web && npm ci && npm run dev
# open http://localhost:5173
```

Real nuScenes mini + Megvii detections: [docs/data.md](docs/data.md).

## Synthetic fixture metrics

| metric | baseline (`tracks_expected`) | demo bundle (intentionally degraded) |
|--------|------------------------------|--------------------------------------|
| MOTA   | 0.90                         | 0.625                                |
| IDS    | 0                            | 2                                    |
| FP     | 0                            | 7                                    |
| FN     | 4                            | 6                                    |

FN=4 on the golden path is tentative-track warmup (promote at 3 hits).

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
docs/findings/            M6 writeups (empty until a real bug fix)
```

## Locked decisions

See [docs/decisions.md](docs/decisions.md): Megvii detections, Mahalanobis association, global params, 2D BEV state.

## Milestones

| Milestone | Status |
|-----------|--------|
| M0 Skeleton | done |
| M1 Tracker v0 | done (golden byte-identical) |
| M2 Metrics | done |
| M3 Failure mining | done (rule clusters) |
| M4 Triage UI | done (demo bootstrap) |
| M5 CI gate | done (synthetic fixture floor) |
| M6 Finding writeup | next — needs real mini data |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).
