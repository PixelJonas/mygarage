"""Migration 115: name an EXISTING Mopeka install's readings.

Apply-time naming cannot reach a device that already exists: applying the
preset again to the same device id is a 409.
"""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text

_MIG = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "migrations"
    / "115_livelink_preset_display_names.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mig115", _MIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seeded(tmp_path, *, preset_device: bool):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE livelink_devices ("
                "  device_id VARCHAR(20) PRIMARY KEY,"
                "  kind VARCHAR(20) NOT NULL DEFAULT 'wican',"
                "  preset_key VARCHAR(50)"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE livelink_parameters ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  param_key VARCHAR(100) NOT NULL UNIQUE,"
                "  display_name VARCHAR(100)"
                ")"
            )
        )
        if preset_device:
            conn.execute(
                text(
                    "INSERT INTO livelink_devices (device_id, kind, preset_key) "
                    "VALUES ('rvgateway', 'generic_mqtt', 'mopeka_two_tank')"
                )
            )
        conn.execute(
            text(
                "INSERT INTO livelink_parameters (param_key, display_name) VALUES "
                "('PROPANE_T1_LEVEL_PCT', 'Propane T1 Level Pct'),"
                "('PROPANE_T1_TEMP_C', NULL),"
                "('PROPANE_T2_TEMP_C', 'Rear bottle temp')"
            )
        )
    return engine


def _names(engine):
    with engine.connect() as conn:
        return dict(
            conn.execute(text("SELECT param_key, display_name FROM livelink_parameters")).all()
        )


def test_is_not_fatal():
    """A skipped rename costs a friendlier label, not correctness."""
    assert _load().FATAL is False


def test_names_auto_and_unnamed_readings_and_keeps_a_chosen_name(tmp_path):
    engine = _seeded(tmp_path, preset_device=True)

    _load().upgrade(engine)

    assert _names(engine) == {
        "PROPANE_T1_LEVEL_PCT": "Tank 1 level",
        "PROPANE_T1_TEMP_C": "Tank 1 temperature",
        "PROPANE_T2_TEMP_C": "Rear bottle temp",
    }


def test_renames_nothing_without_a_preset_device(tmp_path):
    """A database that never applied the preset may own these keys from some
    other source, named however that source named them."""
    engine = _seeded(tmp_path, preset_device=False)
    before = _names(engine)

    _load().upgrade(engine)

    assert _names(engine) == before


def test_is_idempotent(tmp_path):
    engine = _seeded(tmp_path, preset_device=True)
    migration = _load()

    migration.upgrade(engine)
    first = _names(engine)
    migration.upgrade(engine)

    assert _names(engine) == first


def test_missing_tables_are_a_no_op(tmp_path):
    _load().upgrade(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))
