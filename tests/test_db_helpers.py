"""Unit tests for eval.db helpers (no Postgres required for core cases)."""

from __future__ import annotations

import pytest

from eval.db import (
    DEFAULT_DATABASE_URL,
    get_database_url,
    normalize_database_url,
    postgres_available,
    sha_run_key,
)
from eval.write_run import aggregate_run_metrics


def test_sha_run_key_deterministic():
    cfg = {"gate_m": 1.5, "seed": 0, "nested": {"b": 2, "a": 1}}
    a = sha_run_key("abc1234", cfg)
    b = sha_run_key("abc1234", {"nested": {"a": 1, "b": 2}, "seed": 0, "gate_m": 1.5})
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_sha_run_key_changes_with_commit_or_config():
    cfg = {"x": 1}
    base = sha_run_key("aaaa", cfg)
    assert sha_run_key("bbbb", cfg) != base
    assert sha_run_key("aaaa", {"x": 2}) != base


def test_normalize_database_url_strips_schema():
    raw = "postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public"
    assert "schema=" not in normalize_database_url(raw)
    assert "trackbench" in normalize_database_url(raw)


def test_get_database_url_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_get_database_url_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/x")
    assert get_database_url() == "postgresql://user:pass@db:5432/x"


def test_aggregate_run_metrics_mota_and_weighted_motp():
    scene_metrics = {
        "a": {"mota": 0.5, "motp": 1.0, "fp": 1, "fn": 1, "ids": 0, "frag": 0, "gt_count": 10},
        "b": {"mota": 0.0, "motp": 3.0, "fp": 2, "fn": 2, "ids": 1, "frag": 1, "gt_count": 10},
    }
    agg = aggregate_run_metrics(scene_metrics)
    # fp+fn+ids = 1+1+0 + 2+2+1 = 7; gt=20 → mota = 1 - 7/20
    assert agg["fp"] == 3
    assert agg["fn"] == 3
    assert agg["ids"] == 1
    assert agg["frag"] == 1
    assert agg["gt_count"] == 20
    assert agg["mota"] == pytest.approx(1.0 - 7.0 / 20.0)
    # matches: a=9, b=8 → weighted motp = (1*9 + 3*8) / 17
    assert agg["motp"] == pytest.approx((9.0 + 24.0) / 17.0)


@pytest.mark.skipif(
    not postgres_available(),
    reason="Postgres not available (set DATABASE_URL / start docker compose)",
)
def test_write_run_roundtrip_optional():
    """Optional integration: upsert scene + write_run when Postgres is up."""
    pytest.importorskip("psycopg")
    from eval.db import connect, upsert_scene, write_run

    scene_id = "test_db_helpers_scene"
    failures = [
        {
            "scene_id": scene_id,
            "frame": 1,
            "t": 0.5,
            "kind": "ID_SWITCH",
            "track_id": 2,
            "gt_id": "g1",
            "severity": 1.0,
            "features": {"range_bin": "far", "cls": "car"},
        },
        {
            "scene_id": scene_id,
            "frame": 2,
            "t": 1.0,
            "kind": "GHOST_TRACK",
            "track_id": 9,
            "gt_id": None,
            "severity": 0.4,
            "features": {"range_bin": "mid"},
        },
    ]
    clusters = [
        {
            "bucket": "ghost_any",
            "label": "Ghost tracks",
            "size": 1,
            "event_indices": [1],
            "summary": {"n": 1, "kind_mode": "GHOST_TRACK"},
        }
    ]
    config = {"test": True, "seed": 0}

    with connect() as conn:
        upsert_scene(conn, scene_id, "Test Scene", 2, "clear", "day")
        run_id = write_run(
            conn,
            commit_sha="testhat",
            config_json=config,
            notes="test_db_helpers",
            run_metrics={"mota": 0.5, "fp": 1.0},
            scene_id=scene_id,
            scene_metrics={"mota": 0.5, "fp": 1.0},
            failures=failures,
            clusters=clusters,
            run_key="test-db-helpers-run",
        )
        assert run_id

        with conn.cursor() as cur:
            cur.execute('SELECT "runKey", notes FROM "Run" WHERE id = %s', (run_id,))
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "test-db-helpers-run"
            assert row[1] == "test_db_helpers"

            cur.execute(
                'SELECT count(*) FROM "FailureEvent" WHERE "runId" = %s', (run_id,)
            )
            assert cur.fetchone()[0] == 2

            cur.execute(
                'SELECT "clusterId" FROM "FailureEvent" WHERE "runId" = %s ORDER BY frame',
                (run_id,),
            )
            cluster_ids = [r[0] for r in cur.fetchall()]
            assert cluster_ids[0] is None
            assert cluster_ids[1] is not None

            # Idempotent replace
            run_id2 = write_run(
                conn,
                commit_sha="testhat",
                config_json=config,
                notes="test_db_helpers_v2",
                run_metrics={"mota": 0.6},
                scene_id=scene_id,
                scene_metrics={"mota": 0.6},
                failures=[],
                clusters=[],
                run_key="test-db-helpers-run",
            )
            cur.execute('SELECT count(*) FROM "Run" WHERE "runKey" = %s', ("test-db-helpers-run",))
            assert cur.fetchone()[0] == 1
            cur.execute('SELECT notes FROM "Run" WHERE id = %s', (run_id2,))
            assert cur.fetchone()[0] == "test_db_helpers_v2"
            cur.execute('SELECT count(*) FROM "Run" WHERE id = %s', (run_id,))
            assert cur.fetchone()[0] == 0
