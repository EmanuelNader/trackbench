"""Postgres helpers for persisting eval runs (Prisma schema).

Uses ``psycopg`` lazily so the light CI dependency set (numpy + pytest) still
imports without ``requirements-full.txt``. ``--write-db`` needs the full deps.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Matches .env.example / docker-compose local defaults (Prisma ``schema`` param
# is stripped before connecting — see ``normalize_database_url``).
DEFAULT_DATABASE_URL = (
    "postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public"
)


def get_database_url() -> str:
    """Read ``DATABASE_URL`` from the environment, falling back to local default."""
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def normalize_database_url(url: str) -> str:
    """Drop Prisma-only query params (e.g. ``schema=public``) for psycopg."""
    parsed = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "schema"]
    return urlunparse(parsed._replace(query=urlencode(qs)))


def sha_run_key(commit_sha: str, config: dict[str, Any]) -> str:
    """Deterministic run key: sha256 of commit + canonical JSON config."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload = f"{commit_sha}\n{canonical}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _new_id() -> str:
    return str(uuid.uuid4())


def _json_safe(value: Any) -> Any:
    """Coerce values to JSON-serializable forms (numpy scalars, etc.)."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    # numpy scalars / Path-like
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    return str(value)


def _as_scene_metrics_map(
    scene_id: str,
    scene_metrics: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    """Normalize flat (single-scene) or nested (multi-scene) metrics maps."""
    if not scene_metrics:
        if not scene_id:
            return {}
        return {scene_id: {}}
    first = next(iter(scene_metrics.values()))
    if isinstance(first, Mapping):
        out: dict[str, dict[str, float]] = {}
        for sid, metrics in scene_metrics.items():
            if not isinstance(metrics, Mapping):
                raise TypeError(
                    f"scene_metrics[{sid!r}] must be a mapping of metric name → value"
                )
            out[str(sid)] = {str(k): float(v) for k, v in metrics.items()}
        return out
    if not scene_id:
        raise ValueError("scene_id is required when scene_metrics is a flat metrics dict")
    return {scene_id: {str(k): float(v) for k, v in scene_metrics.items()}}


def connect(database_url: str | None = None):
    """Open a psycopg connection (lazy import)."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised via CLI message
        raise ImportError(
            "psycopg is required for --write-db; install with: "
            "pip install -r requirements-full.txt"
        ) from exc

    url = normalize_database_url(database_url or get_database_url())
    return psycopg.connect(url)


def upsert_scene(
    conn,
    scene_id: str,
    name: str,
    num_frames: int,
    weather: str | None,
    time_of_day: str | None,
) -> None:
    """Insert or update a Scene row (id is the natural key)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO "Scene" (id, name, "numFrames", weather, "timeOfDay")
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name,
              "numFrames" = EXCLUDED."numFrames",
              weather = EXCLUDED.weather,
              "timeOfDay" = EXCLUDED."timeOfDay"
            """,
            (scene_id, name, int(num_frames), weather, time_of_day),
        )


def write_run(
    conn,
    *,
    commit_sha: str,
    config_json: dict[str, Any],
    notes: str | None,
    run_metrics: dict[str, float],
    scene_id: str,
    scene_metrics: Mapping[str, Any],
    failures: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    run_key: str | None = None,
) -> str:
    """Create/replace a Run and children; return the new run id.

    Idempotent by ``runKey``: any prior run with the same key is deleted
    (CASCADE removes metrics / events / clusters / tags), then re-inserted.

    ``scene_metrics`` may be a flat metric map for ``scene_id``, or a nested
    ``{scene_id: {metric: value}}`` map for multi-scene aggregation.
    Clusters must use ``event_indices`` into ``failures`` (same as demo.ts).
    """
    try:
        from psycopg.types.json import Jsonb
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "psycopg is required for --write-db; install with: "
            "pip install -r requirements-full.txt"
        ) from exc

    key = run_key or sha_run_key(commit_sha, config_json)
    by_scene = _as_scene_metrics_map(scene_id, scene_metrics)
    run_id = _new_id()
    safe_config = _json_safe(config_json)

    with conn.cursor() as cur:
        cur.execute('SELECT id FROM "Run" WHERE "runKey" = %s', (key,))
        existing = cur.fetchone()
        if existing:
            cur.execute('DELETE FROM "Run" WHERE id = %s', (existing[0],))

        cur.execute(
            """
            INSERT INTO "Run" (id, "commitSha", "createdAt", "configJson", "runKey", notes)
            VALUES (%s, %s, NOW(), %s, %s, %s)
            """,
            (run_id, commit_sha, Jsonb(safe_config), key, notes),
        )

        for name, value in run_metrics.items():
            cur.execute(
                """
                INSERT INTO "RunMetric" (id, "runId", name, value)
                VALUES (%s, %s, %s, %s)
                """,
                (_new_id(), run_id, str(name), float(value)),
            )

        for sid, metrics in by_scene.items():
            for name, value in metrics.items():
                cur.execute(
                    """
                    INSERT INTO "SceneMetric" (id, "runId", "sceneId", name, value)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (_new_id(), run_id, sid, str(name), float(value)),
                )

        # Clusters first, then failure events with clusterId via event_indices
        # (mirrors api/src/demo.ts bootstrapDemo).
        cluster_id_by_event_index: dict[int, str] = {}
        for cluster in clusters:
            cluster_id = _new_id()
            summary = cluster.get("summary") or {}
            if not isinstance(summary, Mapping):
                summary = {}
            centroid: dict[str, Any] = {"bucket": cluster.get("bucket"), **dict(summary)}
            cur.execute(
                """
                INSERT INTO "Cluster" (id, "runId", label, size, "centroidJson")
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    cluster_id,
                    run_id,
                    cluster.get("label"),
                    int(cluster.get("size") or 0),
                    Jsonb(_json_safe(centroid)),
                ),
            )
            for idx in cluster.get("event_indices") or []:
                cluster_id_by_event_index[int(idx)] = cluster_id

        for i, failure in enumerate(failures):
            sid = str(failure.get("scene_id") or scene_id)
            track_id = failure.get("track_id")
            gt_id = failure.get("gt_id")
            features = failure.get("features") or {}
            if not isinstance(features, Mapping):
                features = {}
            cur.execute(
                """
                INSERT INTO "FailureEvent" (
                  id, "runId", "sceneId", frame, t, kind,
                  "trackId", "gtId", severity, "featuresJson", "clusterId"
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    _new_id(),
                    run_id,
                    sid,
                    int(failure["frame"]),
                    float(failure["t"]),
                    str(failure["kind"]),
                    None if track_id is None else int(track_id),
                    None if gt_id is None else str(gt_id),
                    float(failure.get("severity") or 0.0),
                    Jsonb(_json_safe(dict(features))),
                    cluster_id_by_event_index.get(i),
                ),
            )

    conn.commit()
    return run_id


def postgres_available(database_url: str | None = None) -> bool:
    """Return True if a short connection probe succeeds."""
    try:
        with connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:
        return False
