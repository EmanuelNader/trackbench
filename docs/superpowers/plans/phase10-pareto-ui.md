# Phase 10 — Pareto chart in the triage UI

> STATUS: DONE — commit 473d295.
> Result in `docs/findings/009`: interactive Pareto chart (AMOTA-vs-latency
> scatter) in the React triage UI. write_run.py persists AMOTA/p99_ms to
> Postgres; new /api/runs/pareto endpoint; hand-rolled SVG scatter with
> hover tooltips and metric selector.

## Why

The AMOTA-vs-latency Pareto chart currently lives as a static SVG on disk
(`bench/ablation/pareto.svg`). Making it interactive in the React triage UI
lets the operator visually explore the accuracy-vs-latency trade-off across
all configs, select a Pareto-optimal point, and navigate to the run detail
for that config. This closes the loop between the offline benchmark pipeline
and the online triage workflow.

The current data architecture has a "split-brain": CLEAR metrics (MOTA, IDS)
flow through Postgres → API → UI, while AMOTA and latency stay on disk. This
phase unifies the data paths.

## Decisions

- **Chart type:** hand-rolled SVG scatter (no external chart library),
  consistent with the existing `bench/pareto.py` approach and the project's
  zero-external-chart-dep convention.
- **Data source:** new `GET /api/runs/pareto` endpoint that reads all runs
  with their AMOTA + p99 metrics from Postgres.
- **Backend extension:** `eval/write_run.py` persists AMOTA + p99_ms as
  `RunMetric` entries (alongside MOTA, IDS, etc.) so they flow through the
  existing API.
- **Frontend:** new `/pareto` page with an SVG scatter plot. X = p99 latency,
  Y = selectable metric (AMOTA default, MOTA, IDS). Dots = runs. Tooltip on
  hover. Reference configs highlighted.
- **No schema migration needed** — `RunMetric` is already a key-value store;
  adding new metric names is a data change, not a DDL change.

## Files to touch

- `eval/write_run.py`: after computing per-frame timing, write p99_ms and
  AMOTA as RunMetric entries.
- `api/src/index.ts`: add `GET /api/runs/pareto` endpoint.
- `web/src/App.tsx`: add `/pareto` route.
- `web/src/pages/ParetoChart.tsx` (new): scatter plot page.
- `web/src/components/ScatterPlot.tsx` (new): reusable SVG scatter component.
- `web/src/styles.css`: add Pareto chart styles.
- `web/src/api.ts`: add `fetchPareto()` helper.

## Tasks

### Task 1: Backend — persist AMOTA + p99 to Postgres
- Extend `write_run.py` to compute AMOTA and p99_ms and write them as
  RunMetric entries.
- Gate: `python -m eval.write_run --help` still works; schema compatible.
- Commit: `feat(api): persist AMOTA + p99_ms in RunMetric (write_run.py)`

### Task 2: Backend — Pareto API endpoint
- Add `GET /api/runs/pareto` to `api/src/index.ts`.
- Returns: `[{runId, runKey, commitSha, mota, ids, amota, amotp, p99_ms}]`.
- Gate: `curl localhost:3001/api/runs/pareto` returns `[]` (empty DB).
- Commit: `feat(api): /runs/pareto endpoint (scatter data)`

### Task 3: Frontend — ScatterPlot component + ParetoChart page
- Hand-rolled SVG scatter: axes, dots, labels, tooltip, metric selector.
- ParetoChart page: fetches from /api/runs/pareto, renders ScatterPlot.
- Add route + nav link in App.tsx.
- Gate: `cd web && npm run build` succeeds.
- Commit: `feat(web): interactive Pareto chart (AMOTA-vs-latency scatter)`

### Task 4: Finding 009
- `docs/findings/009-pareto-ui.md`: documents the interactive Pareto chart.
- Commit: `docs: finding 009 (interactive Pareto chart in triage UI)`

## Out of scope

- Full val split data, the 24-cell grid re-run, any C++ changes, AMOTA
  implementation changes, or the ablation/CTRV/precision pipelines.

## Gate

`npm run build` succeeds. No schema migration. Existing pages unaffected.
The Pareto page renders an empty scatter when no runs are in the DB.
