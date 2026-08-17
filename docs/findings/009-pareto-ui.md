# 009 — Interactive Pareto chart in the triage UI

## What the system surfaced

Phase 10 added an **interactive Pareto chart** to the React triage UI. The
chart is a hand-rolled SVG scatter plot (no external chart library) that
displays AMOTA-vs-latency (or MOTA-vs-latency, IDS-vs-latency) for every eval
run persisted to Postgres. The operator can:

1. Navigate to `/pareto` from the runs list (new "Pareto chart" button).
2. Toggle the Y-axis between AMOTA, MOTA, and IDS.
3. Hover over any dot to see the run's commit SHA, p99 latency, AMOTA, MOTA,
   IDS, and notes.
4. The scatter plot auto-scales with nice tick marks.

The backend now persists AMOTA, AMOTP, and p99_ms as `RunMetric` entries
(through `write_run.py`), so these metrics flow through the existing
Postgres → API → UI data path alongside MOTA, IDS, FP, FN, FRAG, MOTP.

## What changed

### Backend
- `eval/write_run.py`: after computing per-frame CLEAR MOT metrics, also
  computes AMOTA/AMOTP (via `eval.amota.compute_amota`) and pooled nearest-
  rank p99 (from `*_timing.json` files) and writes them as RunMetric entries.
- `api/src/index.ts`: new `GET /api/runs/pareto` endpoint that returns all
  runs with their AMOTA, AMOTP, p99_ms, MOTA, IDS, and other metrics.

### Frontend
- `web/src/api.ts`: new `ParetoPoint` type and `getPareto()` helper.
- `web/src/components/ScatterPlot.tsx` (new): reusable SVG scatter component
  with auto-scaling axes, nice tick marks, hover tooltips, metric selector.
- `web/src/pages/ParetoChart.tsx` (new): page that fetches from
  `/api/runs/pareto` and renders the ScatterPlot.
- `web/src/App.tsx`: new `/pareto` route; Crumbs breadcrumb updated.
- `web/src/pages/RunsList.tsx`: "Pareto chart" link in the toolbar.
- `web/src/styles.css`: scatter plot styles (dots, tooltip, axes, metric
  toggle, empty state).

## How it works

1. `write_run.py` is run after the tracker completes (manually or via CI).
   It evaluates all scenes, computes AMOTA/AMOTP and p99, and persists
   everything to Postgres.
2. The API's `/runs/pareto` endpoint reads all runs and returns the
   scatter-plot data in a single response.
3. The ParetoChart page fetches the data on mount, renders the ScatterPlot
   component, and updates the chart when the user toggles the Y-axis metric.

## Caveats

1. **Empty DB.** The Pareto chart is empty when no runs are in Postgres.
   The page shows a helpful message pointing to `write_run.py`.
2. **No AMOTA on old runs.** Runs written before Phase 10 won't have
   AMOTA/p99_ms metrics — they'll appear as null dots. Re-running
   `write_run.py` with `--write-db` will add the missing metrics.
3. **No latency accuracy.** The p99 latency is measured on the user's
   machine and may differ across hardware/OS configurations.
4. **Hand-rolled SVG.** The scatter plot is intentionally simple — no zoom,
   pan, or click-to-drill-down. These could be added in a future phase.
5. **No schema migration.** The AMOTA/p99_ms metrics are stored as
   RunMetric key-value entries — no DDL change was needed.

## Recommendation

The Pareto chart closes the loop between the offline benchmark pipeline
(sweep scripts → bench/*.json) and the online triage workflow (Postgres →
API → UI). Running `write_run.py --write-db` after each sweep populates
the chart with all historical data.

**What I'd do next:**
1. Add click-to-drill-down on dots (navigate to RunDetail).
2. Add Pareto frontier line (connecting the optimal points).
3. Add a config label overlay (show which config each dot corresponds to).
