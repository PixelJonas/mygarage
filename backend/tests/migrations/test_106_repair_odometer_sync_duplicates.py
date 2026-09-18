"""Tests for migration 106 — collapse duplicated auto-sync odometer rows.

Parameterized over SQLite *and* PostgreSQL via ``engine_for_migration``.
Seeds the pre-fix corruption shapes (issue #171): a stranded old-date row
beside the moved one, both rows stranded, an orphaned group, a vin-mismatched
source, and tire rows that must never be touched.
"""

import importlib.util
from pathlib import Path

from sqlalchemy import text

import app.migrations as _m

VIN = "MIG106VIN00000001"
OTHER_VIN = "MIG106VIN00000002"


def _load(name):
    path = Path(_m.__file__).parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_tables(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE odometer_records ("
                "id INTEGER PRIMARY KEY, vin VARCHAR(17), date DATE, "
                "odometer_km DECIMAL(10,2), notes TEXT, source VARCHAR(20))"
            )
        )
        conn.execute(
            text("CREATE TABLE fuel_records (id INTEGER PRIMARY KEY, vin VARCHAR(17), date DATE)")
        )
        conn.execute(
            text("CREATE TABLE service_visits (id INTEGER PRIMARY KEY, vin VARCHAR(17), date DATE)")
        )
        conn.execute(
            text("CREATE TABLE def_records (id INTEGER PRIMARY KEY, vin VARCHAR(17), date DATE)")
        )


def _odo(conn, rid, vin, day, km, notes):
    conn.execute(
        text(
            "INSERT INTO odometer_records (id, vin, date, odometer_km, notes, source) "
            "VALUES (:id, :vin, :date, :km, :notes, 'fuel')"
        ),
        {"id": rid, "vin": vin, "date": day, "km": km, "notes": notes},
    )


def _rows(engine):
    with engine.begin() as conn:
        got = conn.execute(
            text("SELECT id, vin, date, notes FROM odometer_records ORDER BY id")
        ).fetchall()
    return {r.id: (r.vin, str(r.date)[:10], r.notes) for r in got}


def test_106_repairs_every_corruption_shape(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_tables(engine)
    with engine.begin() as conn:
        # Group 1: live fuel source dated 2026-08-03; the stranded old-date
        # row (id 1) plus the moved row (id 2). Keep 2, drop 1.
        conn.execute(
            text("INSERT INTO fuel_records (id, vin, date) VALUES (25, :vin, '2026-08-03')"),
            {"vin": VIN},
        )
        _odo(conn, 1, VIN, "2026-08-06", 166111, "[AUTO-SYNC from fuel #25]")
        _odo(conn, 2, VIN, "2026-08-03", 166111, "[AUTO-SYNC from fuel #25]")

        # Group 2: live fuel source dated 2026-09-01, but every member is
        # stranded elsewhere. Keep the newest (id 4) and move it there.
        conn.execute(
            text("INSERT INTO fuel_records (id, vin, date) VALUES (26, :vin, '2026-09-01')"),
            {"vin": VIN},
        )
        _odo(conn, 3, VIN, "2026-08-20", 500, "[AUTO-SYNC from fuel #26]")
        _odo(conn, 4, VIN, "2026-08-25", 500, "[AUTO-SYNC from fuel #26]")

        # Group 3: the service visit is gone. Keep the newest (id 6) as-is.
        _odo(conn, 5, VIN, "2026-07-01", 400, "[AUTO-SYNC from service_visit #9]")
        _odo(conn, 6, VIN, "2026-07-05", 400, "[AUTO-SYNC from service_visit #9]")

        # Group 4: the fuel source exists but belongs to ANOTHER vin, so it
        # cannot arbitrate. Keep the newest (id 8), do not move it.
        conn.execute(
            text("INSERT INTO fuel_records (id, vin, date) VALUES (27, :vin, '2026-06-01')"),
            {"vin": OTHER_VIN},
        )
        _odo(conn, 7, VIN, "2026-06-10", 300, "[AUTO-SYNC from fuel #27]")
        _odo(conn, 8, VIN, "2026-06-12", 300, "[AUTO-SYNC from fuel #27]")

        # Tire rows repeat their prefix legitimately and are never touched.
        _odo(conn, 9, VIN, "2026-05-01", 200, "[AUTO-SYNC from tire_mount #3]")
        _odo(conn, 10, VIN, "2026-05-02", 210, "[AUTO-SYNC from tire_mount #3]")

        # A healthy singleton stays.
        _odo(conn, 11, VIN, "2026-04-01", 100, "[AUTO-SYNC from fuel #12]")

    _load("106_repair_odometer_sync_duplicates").upgrade(engine)

    rows = _rows(engine)
    assert set(rows) == {2, 4, 6, 8, 9, 10, 11}, rows
    assert rows[2][1] == "2026-08-03"
    assert rows[4][1] == "2026-09-01", "the survivor moves to the live source's date"
    assert rows[6][1] == "2026-07-05", "an orphaned survivor keeps its own date"
    assert rows[8][1] == "2026-06-12", "a vin-mismatched source cannot move the survivor"


def test_106_is_idempotent_and_quiet_on_clean_data(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO fuel_records (id, vin, date) VALUES (25, :vin, '2026-08-03')"),
            {"vin": VIN},
        )
        _odo(conn, 1, VIN, "2026-08-06", 166111, "[AUTO-SYNC from fuel #25]")
        _odo(conn, 2, VIN, "2026-08-03", 166111, "[AUTO-SYNC from fuel #25]")

    mod = _load("106_repair_odometer_sync_duplicates")
    mod.upgrade(engine)
    first = _rows(engine)
    mod.upgrade(engine)
    assert _rows(engine) == first


def test_106_survives_a_missing_table(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _load("106_repair_odometer_sync_duplicates").upgrade(engine)
