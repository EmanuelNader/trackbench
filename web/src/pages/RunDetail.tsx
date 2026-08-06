import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ClusterSummary, type RunDetail as RunDetailT } from "../api";

function fmt(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const nav = useNavigate();
  const [run, setRun] = useState<RunDetailT | null>(null);
  const [clusters, setClusters] = useState<ClusterSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setError(null);
    Promise.all([api.getRun(runId), api.listClusters(runId)])
      .then(([r, c]) => {
        setRun(r);
        setClusters(c);
      })
      .catch((e: Error) => setError(e.message));
  }, [runId]);

  if (error) {
    return <div className="error-banner">{error}</div>;
  }
  if (!run) {
    return <p className="muted">Loading run…</p>;
  }

  const m = run.metrics;

  return (
    <div className="fade-in">
      <h1 className="mono">{run.runKey}</h1>
      <p className="subhead">
        commit <span className="mono">{run.commitSha}</span>
        {run.notes ? ` — ${run.notes}` : null}
      </p>

      <div className="metric-row">
        <div>
          <span className="label">MOTA</span>
          <span className="value">{fmt(m.mota)}</span>
        </div>
        <div>
          <span className="label">MOTP</span>
          <span className="value">{fmt(m.motp)}</span>
        </div>
        <div>
          <span className="label">IDS</span>
          <span className="value">{m.ids ?? "—"}</span>
        </div>
        <div>
          <span className="label">FP / FN</span>
          <span className="value">
            {m.fp ?? "—"} / {m.fn ?? "—"}
          </span>
        </div>
        <div>
          <span className="label">FRAG</span>
          <span className="value">{m.frag ?? "—"}</span>
        </div>
        <div>
          <span className="label">Failures</span>
          <span className="value">{run.nFailures}</span>
        </div>
      </div>

      <section className="section">
        <h2>Scenes</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Scene</th>
                <th>Frames</th>
                <th>MOTA</th>
                <th>IDS</th>
                <th>Weather</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {run.scenes.map((s) => (
                <tr key={s.sceneId}>
                  <td className="mono">{s.sceneId}</td>
                  <td className="mono">{s.numFrames}</td>
                  <td className="mono">{fmt(s.metrics.mota)}</td>
                  <td className="mono">{s.metrics.ids ?? "—"}</td>
                  <td className="muted">
                    {[s.weather, s.timeOfDay].filter(Boolean).join(" / ") || "—"}
                  </td>
                  <td>
                    <Link
                      to={`/player/${run.id}/${s.sceneId}?frame=0`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      Open player
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Failure clusters</h2>
        {clusters.length === 0 ? (
          <p className="muted">No clusters for this run.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Size</th>
                  <th>Bucket</th>
                  <th>Mean range</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((c) => {
                  const centroid = c.centroidJson || {};
                  return (
                    <tr
                      key={c.id}
                      onClick={() => nav(`/clusters/${c.id}`)}
                    >
                      <td>{c.label || "—"}</td>
                      <td className="mono">{c.size}</td>
                      <td className="mono muted">
                        {String(centroid.bucket ?? "—")}
                      </td>
                      <td className="mono">
                        {typeof centroid.mean_range_m === "number"
                          ? `${(centroid.mean_range_m as number).toFixed(1)} m`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
