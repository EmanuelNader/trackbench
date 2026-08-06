import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ClusterDetail } from "./pages/ClusterDetail";
import { RunDetail } from "./pages/RunDetail";
import { RunsList } from "./pages/RunsList";
import { ScenePlayer } from "./pages/ScenePlayer";

function Crumbs() {
  const loc = useLocation();
  const parts = loc.pathname.split("/").filter(Boolean);

  if (parts.length === 0 || (parts[0] === "runs" && parts.length === 1)) {
    return <span className="nav-crumb muted">triage</span>;
  }

  if (parts[0] === "player") {
    const runId = parts[1];
    const sceneId = parts[2];
    return (
      <nav className="nav-crumb">
        <NavLink to={runId ? `/runs/${runId}` : "/"}>runs</NavLink>
        <span className="sep">/</span>
        <span>player</span>
        {sceneId ? (
          <>
            <span className="sep">/</span>
            <span className="mono">{sceneId}</span>
          </>
        ) : null}
      </nav>
    );
  }

  return (
    <nav className="nav-crumb">
      <NavLink to="/">runs</NavLink>
      {parts[0] === "runs" && parts[1] ? (
        <>
          <span className="sep">/</span>
          <span className="mono">{parts[1].slice(0, 10)}…</span>
        </>
      ) : null}
      {parts[0] === "clusters" ? (
        <>
          <span className="sep">/</span>
          <span>cluster</span>
        </>
      ) : null}
    </nav>
  );
}

export default function App() {
  const loc = useLocation();
  const isPlayer = loc.pathname.startsWith("/player");

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          track<span>bench</span>
        </NavLink>
        <Crumbs />
      </header>
      <main className={isPlayer ? "main player-main" : "main"}>
        <Routes>
          <Route path="/" element={<RunsList />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/clusters/:clusterId" element={<ClusterDetail />} />
          <Route path="/player/:runId/:sceneId" element={<ScenePlayer />} />
        </Routes>
      </main>
    </div>
  );
}
