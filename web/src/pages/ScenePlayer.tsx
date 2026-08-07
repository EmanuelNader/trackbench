import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  TAG_OPTIONS,
  type FailureEvent,
  type FramePayload,
  type TagName,
} from "../api";
import { BevCanvas } from "../components/BevCanvas";

const PLAY_MS = 280;

export function ScenePlayer() {
  const { runId, sceneId } = useParams<{ runId: string; sceneId: string }>();
  const [params, setParams] = useSearchParams();
  const initialFrame = Number(params.get("frame") || 0) || 0;
  const initialEvent = params.get("event");

  const [numFrames, setNumFrames] = useState(20);
  const [frameIdx, setFrameIdx] = useState(initialFrame);
  const [frame, setFrame] = useState<FramePayload | null>(null);
  const [events, setEvents] = useState<FailureEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(
    initialEvent,
  );
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tagBusy, setTagBusy] = useState(false);
  const playRef = useRef<number | null>(null);

  const selected = events.find((e) => e.id === selectedEventId) ?? null;

  useEffect(() => {
    if (!runId || !sceneId) return;
    setError(null);
    Promise.all([
      api.getRun(runId),
      api.listRunEvents(runId, sceneId),
    ])
      .then(([run, evs]) => {
        const scene = run.scenes.find((s) => s.sceneId === sceneId);
        if (scene) setNumFrames(scene.numFrames);
        setEvents(evs);
      })
      .catch((e: Error) => setError(e.message));
  }, [runId, sceneId]);

  useEffect(() => {
    if (!sceneId) return;
    let cancelled = false;
    api
      .getFrame(sceneId, frameIdx)
      .then((f) => {
        if (!cancelled) setFrame(f);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [sceneId, frameIdx]);

  useEffect(() => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("frame", String(frameIdx));
        if (selectedEventId) next.set("event", selectedEventId);
        else next.delete("event");
        return next;
      },
      { replace: true },
    );
  }, [frameIdx, selectedEventId, setParams]);

  useEffect(() => {
    if (!playing) {
      if (playRef.current != null) window.clearInterval(playRef.current);
      playRef.current = null;
      return;
    }
    playRef.current = window.setInterval(() => {
      setFrameIdx((f) => {
        if (f >= numFrames - 1) {
          setPlaying(false);
          return f;
        }
        return f + 1;
      });
    }, PLAY_MS);
    return () => {
      if (playRef.current != null) window.clearInterval(playRef.current);
    };
  }, [playing, numFrames]);

  const jumpToEvent = (e: FailureEvent) => {
    setSelectedEventId(e.id);
    setFrameIdx(e.frame);
    setPlaying(false);
  };

  const toggleTag = async (name: TagName) => {
    if (!selected) return;
    setTagBusy(true);
    setError(null);
    try {
      const has = selected.tags.some((t) => t.name === name);
      if (has) {
        await api.removeTag(selected.id, name);
      } else {
        await api.addTag(selected.id, name);
      }
      const refreshed = await api.listRunEvents(runId!, sceneId!);
      setEvents(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTagBusy(false);
    }
  };

  const maxFrame = Math.max(0, numFrames - 1);

  return (
    <div className="player-layout fade-in">
      <BevCanvas frame={frame} />

      <aside className="side-panel">
        <div>
          <h2>Scene</h2>
          <div className="mono" style={{ fontSize: "0.9rem" }}>
            {sceneId}
          </div>
          <div className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>
            <Link to={`/runs/${runId}`}>← run</Link>
            {" · "}
            t={frame?.t?.toFixed(2) ?? "—"}s
          </div>
        </div>

        <div>
          <h2>Failure events</h2>
          {events.length === 0 ? (
            <p className="muted" style={{ fontSize: "0.8rem" }}>
              No mined failures on this scene.
            </p>
          ) : (
            <ul className="event-list">
              {events.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    className={e.id === selectedEventId ? "selected" : ""}
                    onClick={() => jumpToEvent(e)}
                  >
                    <span className="kind-badge">{e.kind}</span>
                    <span className="mono muted" style={{ marginLeft: 8 }}>
                      f{e.frame}
                    </span>
                    <div className="muted" style={{ marginTop: 2, fontSize: "0.72rem" }}>
                      tr {e.trackId ?? "—"} · gt {e.gtId ?? "—"}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h2>Tags</h2>
          {!selected ? (
            <p className="muted" style={{ fontSize: "0.8rem" }}>
              Select an event to tag.
            </p>
          ) : (
            <>
              <p className="muted" style={{ fontSize: "0.75rem", margin: "0 0 0.5rem" }}>
                {selected.kind} @ frame {selected.frame}
              </p>
              <div className="tag-grid">
                {TAG_OPTIONS.map((name) => {
                  const on = selected.tags.some((t) => t.name === name);
                  return (
                    <button
                      key={name}
                      type="button"
                      className={`btn ${on ? "active" : ""}`}
                      disabled={tagBusy}
                      onClick={() => toggleTag(name)}
                    >
                      {name}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {error && (
          <div className="error-banner" style={{ margin: 0 }}>
            {error}
          </div>
        )}
      </aside>

      <div className="timeline">
        <div className="timeline-controls">
          <button
            type="button"
            className="btn pulse-play"
            data-playing={playing ? "true" : "false"}
            onClick={() => setPlaying((p) => !p)}
          >
            {playing ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setPlaying(false);
              setFrameIdx((f) => Math.max(0, f - 1));
            }}
            disabled={frameIdx <= 0}
          >
            −1
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setPlaying(false);
              setFrameIdx((f) => Math.min(maxFrame, f + 1));
            }}
            disabled={frameIdx >= maxFrame}
          >
            +1
          </button>
          <span className="frame-readout">
            frame {frameIdx} / {maxFrame}
            {frame ? ` · ${frame.gt.length} gt · ${frame.tracks.length} trk` : ""}
          </span>
        </div>

        <div className="scrubber-wrap">
          <div className="scrubber-ticks">
            {events.map((e) => {
              const pct = maxFrame === 0 ? 0 : (e.frame / maxFrame) * 100;
              return (
                <span
                  key={e.id}
                  title={`${e.kind} @ ${e.frame}`}
                  className={e.id === selectedEventId ? "active" : ""}
                  style={{ left: `${pct}%` }}
                />
              );
            })}
          </div>
          <input
            className="scrubber"
            type="range"
            min={0}
            max={maxFrame}
            value={frameIdx}
            onChange={(ev) => {
              setPlaying(false);
              setFrameIdx(Number(ev.target.value));
            }}
          />
        </div>
      </div>
    </div>
  );
}
