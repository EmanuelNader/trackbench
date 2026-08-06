# trackbench

A miniature AV data engine: run a tracker over logged driving data, automatically find where it fails, cluster those failures into real bugs, and gate every future change on regression.

> **Status (M0–M4):** Skeleton + deterministic C++ tracker + CLEAR MOT + failure mining/clustering + triage UI with Canvas BEV player. Synthetic fixture demo works without the 4GB download.

## Quick start — triage UI demo

```bash
# 1. Infra + DB
cp .env.example .env
docker compose up -d          # or use local Postgres on :5432
cd api && npm install && npx prisma migrate deploy && cd ..

# 2. (Re)generate fixture demo bundle if needed
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m eval.write_demo_run

# 3. API + load demo run
cd api && npm run dev         # http://localhost:3001
curl -s http://localhost:3001/demo/bootstrap | jq

# 4. Web
cd web && npm install && npm run dev   # http://localhost:5173 (proxies /api → :3001)
```

Click **Load demo run** on the runs page if you skipped the curl, then open a scene player.

## Tracker / ingest

```bash
make core
./core/build/trackbench_run --help

python -m ingest.nuscenes_ingest --synthetic --force
cat data/normalized/synthetic_scene_001/detections.jsonl | head
```

For real nuScenes mini + Megvii detections, see [docs/data.md](docs/data.md).

## Layout

```
core/       C++17 tracker (EKF + Hungarian + lifecycle) — stub CLI in M0
ingest/     nuScenes → ego-frame detections.jsonl / gt.jsonl
eval/       CLEAR MOT, failure mining, clustering, demo bundle writer
api/        Express + Prisma (Postgres) + fixture bootstrap
web/        React triage UI (runs / clusters / Canvas BEV player)
data/       gitignored raw/normalized; fixtures committed for CI
baselines/  metric floor for the regression gate (M5)
docs/       decisions + findings
```

## Locked decisions (M0)

See [docs/decisions.md](docs/decisions.md):

1. **Megvii (CBGS)** published detections
2. **Mahalanobis** association (GIoU noted as alternative)
3. **Global** tracker params first
4. **2D BEV** state `[x, y, vx, vy, yaw]`

## Milestones

| Milestone | Deliverable |
|-----------|-------------|
| M0 | Skeleton, synthetic ingest, Prisma, hello binary |
| M1 | EKF + Hungarian + lifecycle, golden byte-identical tracks |
| M2 | CLEAR MOT → Postgres `Run` |
| M3 | Failure mining + rule clustering |
| **M4** (this PR) | Triage UI + Canvas BEV player + fixture demo bootstrap |
| M5 | CI regression gate |
| M6 | One written finding with before/after metrics |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).
