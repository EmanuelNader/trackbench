# trackbench

Run a deterministic CV-EKF tracker on logged driving data, mine failures, cluster them into bugs, and gate every change on regression.

**Loop:** ingest → C++ tracker → CLEAR MOT → failure mining → triage UI → CI gate.  
**Result on nuScenes mini:** CLEAR-MOT IDS **890 → 415 (−53%)** across findings [001](docs/findings/001-dense-id-switch-velocity-gate.md)–[003](docs/findings/003-harder-birth-score.md) (honest null on [002](docs/findings/002-bev-iou-association.md)).

<p align="center">
  <img src="docs/assets/triage-bev.png" alt="trackbench BEV triage player: scene-0655 with selected ID_SWITCH and was→now explain panel" width="900" />
</p>

<p align="center"><em>Triage UI — <code>scene-0655</code>, selected <code>ID_SWITCH</code> with was→now explain panel.</em></p>

## Metrics (nuScenes `v1.0-mini`)

Megvii train∪val detections, 7 tracking classes, det score ≥ 0.3.

| metric | pre-001 | post-001 | post-003 (`min_birth_score=0.7`) |
|--------|---------|----------|----------------------------------|
| Total CLEAR-MOT IDS | 890 | ~618 | **415** (−53% vs pre-001) |
| scene-0655 IDS | 471 | ~326 | **216** |
| scene-0916 IDS | 384 | ~287 | **197** |

| Finding | Change | Outcome |
|---------|--------|---------|
| [001](docs/findings/001-dense-id-switch-velocity-gate.md) | Soft lateral velocity cost + `gate_m=1.5` + birth 0.5 | **IDS 890 → ~618** |
| [002](docs/findings/002-bev-iou-association.md) | Soft BEV IoU association term | **Null** (618 → 619) |
| [003](docs/findings/003-harder-birth-score.md) | `min_birth_score` 0.5 → 0.7 | **IDS 619 → 415** |

MOTA stays mid/weak on dense scenes — expected for a simple classical CV tracker. The deliverable is the **mined ID-switch cut**, not a leaderboard score.

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

### Real mini

```bash
python scripts/merge_megvii_mini.py
PYTHONPATH=. python -m ingest.nuscenes_ingest --force
make core
./scripts/eval_all_scenes.sh --force   # retrack after config changes

PYTHONPATH=. python -m eval.write_run --mine --write-db --notes "mini after finding 003"
# start API with NORMALIZED_ROOT + TRACKS_ROOT — docs/mini-ui.md
```

Details: [docs/data.md](docs/data.md).

## Latency

`trackbench_run --timing PATH` writes per-frame wall ms. Reference numbers from a **dense synthetic** association load (100 frames × 40 dets) via `scripts/bench_latency.py`:

| | p50 | p99 | hardware |
|--|-----|-----|----------|
| Dense synthetic | **~0.032 ms/frame** | **~0.047 ms/frame** | Linux x86_64 Xeon (cloud VM) |

Raw report: [docs/bench/latency_dense.json](docs/bench/latency_dense.json).

```bash
make bench-latency
# or on a real scene:
core/build/trackbench_run \
  --dets data/normalized/scene-0655/detections.jsonl \
  --config core/config/default.json \
  --out /tmp/tracks.jsonl \
  --timing /tmp/timing.json
```

Re-run on your machine for Apple Silicon / laptop numbers; CI can gate on p99 when a host-specific baseline is set (`baselines/baseline.json`).

## What I'd do next

1. **Per-class coast / birth** — pedestrians vs cars (LATE_INIT / FN residual).
2. **Optional:** keep tentatives out of Hungarian until `promote_hits`.
3. **Optional:** host-specific latency on Apple Silicon via `make bench-latency`.

## Layout

```
core/       C++17 CV-EKF tracker (Hungarian + lifecycle), GoogleTest + golden
ingest/     nuScenes → ego-frame JSONL (--synthetic for offline demo)
eval/       CLEAR MOT, failure mining, rule clustering, CI gate
api/        Express + Prisma
web/        React triage UI + Canvas 2D BEV player
scripts/    eval_all_scenes.sh (--force), merge_megvii_mini.py, bench_latency.py
data/fixtures/   committed synthetic scene + demo_bundle.json
baselines/baseline.json   CI metric floor
docs/findings/            001–003 writeups
docs/bench/               latency reference JSON
docs/assets/              triage UI diagram / screenshots
```

## Milestones

| Milestone | Status |
|-----------|--------|
| M0 Skeleton | done |
| M1 Tracker v0 | done (golden byte-identical) |
| M2 Metrics | done |
| M3 Failure mining | done (rule clusters) |
| M4 Triage UI | done (demo + mini via NORMALIZED_ROOT) |
| M5 CI gate | done (synthetic fixture floor) |
| M6 Findings | done — [001](docs/findings/001-dense-id-switch-velocity-gate.md) win, [002](docs/findings/002-bev-iou-association.md) null, [003](docs/findings/003-harder-birth-score.md) win |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).
