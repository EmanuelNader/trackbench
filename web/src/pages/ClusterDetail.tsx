import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ClusterEventsResponse } from "../api";

export function ClusterDetail() {
  const { clusterId } = useParams<{ clusterId: string }>();
  const nav = useNavigate();
  const [data, setData] = useState<ClusterEventsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!clusterId) return;
    setError(null);
    api
      .getClusterEvents(clusterId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [clusterId]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <p className="muted">Loading cluster…</p>;

  const { cluster, events, total } = data;

  return (
    <div className="fade-in">
      <h1>{cluster.label || "Cluster"}</h1>
      <p className="subhead">
        <Link to={`/runs/${cluster.runId}`}>Back to run</Link>
        {" · "}
        <span className="mono">{total}</span> events
        {cluster.centroidJson?.bucket
          ? ` · bucket ${String(cluster.centroidJson.bucket)}`
          : null}
      </p>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Kind</th>
              <th>Scene</th>
              <th>Frame</th>
              <th>Track</th>
              <th>GT</th>
              <th>Severity</th>
              <th>Tags</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr
                key={e.id}
                onClick={() =>
                  nav(
                    `/player/${e.runId}/${e.sceneId}?frame=${e.frame}&event=${e.id}`,
                  )
                }
              >
                <td>
                  <span className="kind-badge">{e.kind}</span>
                </td>
                <td className="mono muted">{e.sceneId}</td>
                <td className="mono">{e.frame}</td>
                <td className="mono">{e.trackId ?? "—"}</td>
                <td className="mono">{e.gtId ?? "—"}</td>
                <td className="mono">{e.severity.toFixed(2)}</td>
                <td className="muted">
                  {e.tags.length
                    ? e.tags.map((t) => t.name).join(", ")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
