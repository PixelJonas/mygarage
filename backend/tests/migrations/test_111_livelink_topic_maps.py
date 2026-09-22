"""Migration 111: the topic mapping table.

ORM-backed tests live in tests/unit/services/test_livelink_topic_map.py, NOT
here. The `engine_for_migration` fixture runs `DROP SCHEMA public CASCADE` for
its PostgreSQL parametrization, which destroys the tables `create_all` built
for any `db_session` test sharing this file. That is why test_098 uses raw
engines exclusively. A `db_session` test here passes alone and fails in the
full run.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

import app.migrations as _m
from app.models.livelink_topic_map import LiveLinkTopicMap

pytestmark = pytest.mark.migrations


def _load(name: str):
    """Load a migration module by number-name, as test_098 does."""
    path = Path(_m.__file__).parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_offset_column_avoids_the_reserved_word():
    cols = set(LiveLinkTopicMap.__table__.c.keys())
    assert "value_offset" in cols, "OFFSET is reserved in SQL"
    assert "offset" not in cols


def test_defaults_are_the_identity_transform():
    col = LiveLinkTopicMap.__table__.c
    assert col.scale.default.arg == 1
    assert col.value_offset.default.arg == 0


@pytest.mark.parametrize("engine_for_migration", ["sqlite", "pg"], indirect=True)
def test_the_table_is_created_and_the_migration_is_idempotent(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    mod = _load("111_livelink_topic_maps")
    mod.upgrade(engine)
    mod.upgrade(engine)
    assert "livelink_topic_maps" in set(inspect(engine).get_table_names())


@pytest.mark.parametrize("engine_for_migration", ["sqlite", "pg"], indirect=True)
def test_the_boolean_default_is_accepted_by_both_dialects(engine_for_migration):
    """PostgreSQL rejects `DEFAULT 1` on a boolean column; SQLite accepts it.

    A SQLite-only run cannot see this, which is what the sidecar is for.
    """
    from sqlalchemy import text

    _dialect, engine, _url = engine_for_migration
    _load("111_livelink_topic_maps").upgrade(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO livelink_topic_maps (device_id, topic, param_key) "
                "VALUES ('d1', 't/1', 'P')"
            )
        )
        enabled = conn.execute(
            text("SELECT enabled FROM livelink_topic_maps WHERE device_id = 'd1'")
        ).scalar_one()
    assert bool(enabled) is True
