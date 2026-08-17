import { useEffect, useState } from "react";
import { api, type ParetoPoint } from "../api";
import { ScatterPlot } from "../components/ScatterPlot";

type MetricKey = "amota" | "mota" | "ids";

export function ParetoChart() {
  const [points, setPoints] = useState<ParetoPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [yMetric, setYMetric] = useState<MetricKey>("amota");

  useEffect(() => {
    setLoading(true);
    api
      .getPareto()
      .then(setPoints)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const validCount = points.filter(
    (p) =>
      p.p99_ms != null &&
      p[yMetric] != null &&
      Number.isFinite(p.p99_ms!) &&
      Number.isFinite(p[yMetric]!),
  ).length;

  return (
    <div className="fade-in">
      <h1>Pareto Chart</h1>
      <p className="subhead">
        Accuracy vs latency scatter. Each dot = one eval run. Hover for detail.
      </p>

      <div className="toolbar">
        <label className="metric-toggle">
          Y-axis:
          {(["amota", "mota", "ids"] as MetricKey[]).map((key) => (
            <button
              key={key}
              className={`btn small ${yMetric === key ? "primary" : "ghost"}`}
              onClick={() => setYMetric(key)}
            >
              {key.toUpperCase()}
            </button>
          ))}
        </label>
        <span className="muted" style={{ marginLeft: "auto" }}>
          {validCount} data point{validCount !== 1 ? "s" : ""}
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : points.length === 0 ? (
        <div className="empty">
          No runs yet. Write a run to Postgres with{" "}
          <code>python -m eval.write_run --write-db</code> to populate the
          Pareto chart.
        </div>
      ) : (
        <ScatterPlot points={points} yKey={yMetric} />
      )}
    </div>
  );
}
