# trackbench

A miniature AV data engine: run a tracker over logged driving data, automatically find where it fails, cluster those failures into real bugs, and gate every future change on regression.

> **Status (M0–M2 early):** Skeleton + working deterministic C++ tracker (EKF/Hungarian/lifecycle) + CLEAR MOT metrics. Synthetic ingest demos without the 4GB download. Failure mining / UI / CI gate still ahead.

## Quick start

```bash
# 1. Infra
cp .env.example .env
docker compose up -d

# 2. DB
cd api && npm install && npx prisma migrate deploy && cd ..

# 3. C++ binary
make core
./core/build/trackbench_run --help

# 4. Synthetic ingest (no 4GB download required)
python3 -m venv .venv && source .venv/bin/activate
pip install numpy pyquaternion pytest python-dotenv
python -m ingest.nuscenes_ingest --synthetic --force
cat data/normalized/synthetic_scene_001/detections.jsonl | head
```

For real nuScenes mini + Megvii detections, see [docs/data.md](docs/data.md).

## Layout

```
core/       C++17 tracker (EKF + Hungarian + lifecycle) — stub CLI in M0
ingest/     nuScenes → ego-frame detections.jsonl / gt.jsonl
eval/       CLEAR MOT, failure mining, clustering (stubs → M2/M3)
api/        Express + Prisma (Postgres)
web/        React triage UI (stub → M4)
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
| **M0** (this PR) | Skeleton, synthetic ingest, Prisma, hello binary |
| M1 | EKF + Hungarian + lifecycle, golden byte-identical tracks |
| M2 | CLEAR MOT → Postgres `Run` |
| M3 | Failure mining + rule clustering |
| M4 | Triage UI + Canvas BEV player |
| M5 | CI regression gate |
| M6 | One written finding with before/after metrics |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).
