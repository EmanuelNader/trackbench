import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type RunSummary } from "../api";

function fmt(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function RunsList() {
  const nav = useNavigate();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapping, setBootstrapping] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .listRuns()
      .then(setRuns)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const onBootstrap = async () => {
    setBootstrapping(true);
    setError(null);
    try {
      const result = await api.bootstrapDemo();
      await load();
      nav(`/runs/${result.runId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBootstrapping(false);
    }
  };

  return (
    <div className="fade-in">
      <h1>Runs</h1>
      <p className="subhead">
        Eval runs newest-first. Load the synthetic demo if the table is empty.
      </p>

      <div className="toolbar">
        <button
          className="btn primary"
          onClick={onBootstrap}
          disabled={bootstrapping}
        >
          {bootstrapping ? "Loading demo…" : "Load demo run"}
        </button>
        <button className="btn ghost" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && runs.length === 0 ? (
        <p className="muted">Loading…</p>
      ) : runs.length === 0 ? (
        <div className="empty">
          No runs yet. Click <strong>Load demo run</strong> to bootstrap the
          fixture.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Run key</th>
                <th>Commit</th>
                <th>MOTA</th>
                <th>IDS</th>
                <th>Failures</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} onClick={() => nav(`/runs/${r.id}`)}>
                  <td>
                    <Link
                      className="mono"
                      to={`/runs/${r.id}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {r.runKey}
                    </Link>
                  </td>
                  <td className="mono muted">{r.commitSha.slice(0, 8)}</td>
                  <td className="mono">{fmt(r.mota)}</td>
                  <td className="mono">{r.ids ?? "—"}</td>
                  <td className="mono">{r.nFailures}</td>
                  <td className="muted">
                    {new Date(r.createdAt).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
