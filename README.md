# trackbench

**A small system for debugging multi-object tracking on real driving logs.**

Self-driving stacks need to know not only *what* is around the car, but *which* object is which over time. That second job is **tracking**: give each car/pedestrian a stable ID as frames roll by. When tracking fails, IDs swap, objects appear late, or ghost tracks show up — and a single score like “MOTA” rarely tells you *why*.

trackbench is an end-to-end loop that:

1. Takes **public** driving data + published detector boxes  
2. Runs a **classical** (non-neural) tracker in C++  
3. Scores it with standard MOT metrics  
4. **Mines** concrete failures (especially identity switches)  
5. Shows them in a **bird’s-eye triage UI** so you can see the bug  
6. Lets you change the tracker, re-measure, and keep only real wins  
7. Gates regressions in CI  

**Headline result** on nuScenes mini: identity switches **890 → 415 (−53%)** via findings [001](docs/findings/001-dense-id-switch-velocity-gate.md)–[003](docs/findings/003-harder-birth-score.md) (with an honest null on [002](docs/findings/002-bev-iou-association.md)).

<p align="center">
  <img src="docs/assets/triage-bev.png" alt="trackbench bird's-eye triage UI on a dense scene with an ID switch selected" width="900" />
</p>

<p align="center"><em>Bird’s-eye triage UI — blue = ground truth, orange = tracker IDs. Selected failure explains <code>was track 3 → now track 2</code>.</em></p>

## What this is (for someone new)

| Term | Plain meaning |
|------|----------------|
| **Detection** | “In this frame, there is a car *here*.” |
| **Tracking** | “That car is the *same* one as last frame — still ID 7.” |
| **Ground truth (GT)** | The dataset’s answer key for where objects really were. |
| **ID switch** | The answer-key object suddenly got a *different* tracker ID. |
| **CLEAR MOT / MOTA / IDS** | Standard scoring: how often you’re wrong, including ID swaps. |

This repo focuses on **tracking + evaluation + triage**. It does **not** train a neural detector.

Instead it uses **[Megvii / CBGS](https://www.nuscenes.org/data/detection-megvii.zip)** detections — a public zip of precomputed boxes released as an official [nuScenes](https://www.nuscenes.org/) tracking baseline. Think: someone else’s “eyes,” your “memory” (the tracker).

| Piece | Role |
|-------|------|
| **nuScenes `v1.0-mini`** | ~10 public driving scenes + ground-truth boxes |
| **Megvii detections** | Precomputed boxes + confidence scores (tracker inputs) |
| **Ingest** | Filter to tracking classes (score ≥ 0.3), merge Megvii train∪val for mini, write simple ego-frame JSONL |
| **C++ tracker** | Constant-velocity EKF + Hungarian matching — assigns IDs over time |
| **Eval / mine / UI** | Score, list failures, cluster them, inspect in a top-down player |

Why Megvii: public, stable format, no detector training (project anti-goal). More detail: [docs/data.md](docs/data.md), [docs/decisions.md](docs/decisions.md).

**Data not included.** This repo ships code + tiny synthetic fixtures only. Download nuScenes mini and Megvii yourself under their terms; `data/raw/` and real normalized scenes are gitignored.

## How the loop works

```text
public data  →  ingest (JSONL)  →  C++ tracker  →  scores + failure list
                                                      ↓
                              CI gate ←  triage UI  ←  Postgres
```

Typical workflow after a tracker change:

```bash
make core
./scripts/eval_all_scenes.sh --force   # must retrack; don’t reuse old tracks.jsonl
# compare IDS / open UI on the new run
```

## Metrics (nuScenes `v1.0-mini`)

Same public setup for every finding: Megvii train∪val, 7 tracking classes, det score ≥ 0.3.

| metric | before findings | after 001 | after 003 (birth score 0.7) |
|--------|-----------------|-----------|------------------------------|
| Total identity switches (IDS) | 890 | ~618 | **415** (−53% vs start) |
| densest scene `0655` IDS | 471 | ~326 | **216** |
| densest scene `0916` IDS | 384 | ~287 | **197** |

| Finding | What we changed | Outcome |
|---------|-----------------|---------|
| [001](docs/findings/001-dense-id-switch-velocity-gate.md) | Prefer motion-consistent matches; tighter gate; don’t birth tracks from weak dets | **Win** — IDS 890 → ~618 |
| [002](docs/findings/002-bev-iou-association.md) | Also use box-overlap (IoU) in matching cost | **Null** — IDS unchanged (~619) |
| [003](docs/findings/003-harder-birth-score.md) | Require higher confidence before starting a new ID (`0.5 → 0.7`) | **Win** — IDS 619 → 415 |

Overall accuracy (MOTA) is still mid/weak on crowded scenes — expected for a simple classical tracker. The point of this project is the **mined ID-switch cut** and the triage loop, not topping a leaderboard.

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

1. **Per-class coast / birth** — pedestrians vs cars (late starts / misses that remain).
2. **Optional:** don’t let brand-new tracks compete in matching until they’re confirmed.
3. **Optional:** host-specific latency on Apple Silicon via `make bench-latency`.

## Layout

```
core/       C++17 tracker (EKF + Hungarian + lifecycle), GoogleTest + golden
ingest/     nuScenes → ego-frame JSONL (--synthetic for offline demo)
eval/       MOT scores, failure mining, clustering, CI gate
api/        Express + Prisma
web/        React triage UI + Canvas 2D bird’s-eye player
scripts/    eval_all_scenes.sh (--force), merge_megvii_mini.py, bench_latency.py
data/fixtures/   tiny synthetic scene for CI / demo (not the full dataset)
baselines/baseline.json   CI metric floor
docs/findings/            experiment writeups 001–003
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
| M6 Findings | done — [001](docs/findings/001-dense-id-switch-velocity-gate.md) win, [002](docs/findings/002-bev-iou-association.md) null, [003](docs/findings/003-harder-birth-score.md) win |

## Constraints

Public data and knowledge only. Deterministic outputs. Eval before features. Small first (`v1.0-mini`).

## License

Code and docs in this repository are [MIT](LICENSE). nuScenes and Megvii data remain under their upstream licenses/terms — obtain them from the official sources; they are not redistributed here.
