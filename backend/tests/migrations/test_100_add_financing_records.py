"""Tests for migration 100 — financing_records table (lease/loan/upfront-fee costs).

Parameterized over SQLite *and* PostgreSQL via the ``engine_for_migration``
fixture (PG runs skip when ``TEST_DATABASE_URL`` is unset).
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import app.migrations as _m


def _load(name):
    path = Path(_m.__file__).parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_deps(engine):
    """Create minimal vehicles + vendors tables for the FK targets."""
    is_pg = engine.dialect.name == "postgresql"
    pk = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE vehicles (vin VARCHAR(17) PRIMARY KEY)"))
        conn.execute(text(f"CREATE TABLE vendors (id {pk}, name VARCHAR(200))"))
        conn.execute(text("INSERT INTO vehicles (vin) VALUES ('1FT0000000000000X')"))
        conn.execute(text("INSERT INTO vendors (name) VALUES ('Test Bank')"))


def test_100_creates_table(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)
    _load("100_add_financing_records").upgrade(engine)

    insp = inspect(engine)
    assert insp.has_table("financing_records")
    cols = {c["name"] for c in insp.get_columns("financing_records")}
    assert {
        "id",
        "vin",
        "vendor_id",
        "date",
        "amount",
        "tax_amount",
        "category",
        "notes",
        "created_at",
        "updated_at",
    } <= cols

    index_cols = {tuple(ix["column_names"]) for ix in insp.get_indexes("financing_records")}
    assert ("vin",) in index_cols
    assert ("date",) in index_cols
    assert ("vendor_id",) in index_cols

    fk_targets = {fk["referred_table"] for fk in insp.get_foreign_keys("financing_records")}
    assert {"vehicles", "vendors"} <= fk_targets


def test_100_category_check_accepts_valid_values(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)
    _load("100_add_financing_records").upgrade(engine)

    with engine.begin() as conn:
        for category in ("lease_payment", "loan_payment", "upfront_fee"):
            conn.execute(
                text(
                    "INSERT INTO financing_records (vin, date, amount, category) "
                    "VALUES (:vin, '2026-01-01', 100.00, :category)"
                ),
                {"vin": "1FT0000000000000X", "category": category},
            )

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM financing_records")).scalar()
    assert count == 3


def test_100_category_check_rejects_invalid_value(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)
    _load("100_add_financing_records").upgrade(engine)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO financing_records (vin, date, amount, category) "
                    "VALUES (:vin, '2026-01-01', 100.00, 'other')"
                ),
                {"vin": "1FT0000000000000X"},
            )


def test_100_tax_amount_is_nullable(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)
    _load("100_add_financing_records").upgrade(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO financing_records (vin, date, amount, category) "
                "VALUES (:vin, '2026-01-01', 250.00, 'lease_payment')"
            ),
            {"vin": "1FT0000000000000X"},
        )

    with engine.connect() as conn:
        tax_amount = conn.execute(text("SELECT tax_amount FROM financing_records")).scalar()
    assert tax_amount is None


def test_100_idempotent(engine_for_migration):
    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)
    mod = _load("100_add_financing_records")
    mod.upgrade(engine)
    mod.upgrade(engine)  # second run must not raise
    assert inspect(engine).has_table("financing_records")


def test_100_missing_vehicles_table_skips(engine_for_migration):
    """A bare DB without the ``vehicles`` table must skip, not raise."""
    _dialect, engine, _url = engine_for_migration
    _load("100_add_financing_records").upgrade(engine)
    assert not inspect(engine).has_table("financing_records")


def test_100_model_create_all_matches_migration_shape(engine_for_migration):
    """``FinancingRecord``'s ORM-declared table must carry the same columns,
    FKs, and category CHECK as the hand-written migration DDL — the two are
    meant to converge (see test_schema_parity's create_all vs. migration
    parity guard)."""
    from app.models.financing import FinancingRecord

    _dialect, engine, _url = engine_for_migration
    _make_deps(engine)

    FinancingRecord.metadata.create_all(engine, tables=[FinancingRecord.__table__])

    insp = inspect(engine)
    assert insp.has_table("financing_records")
    cols = {c["name"] for c in insp.get_columns("financing_records")}
    assert {
        "id",
        "vin",
        "vendor_id",
        "date",
        "amount",
        "tax_amount",
        "category",
        "notes",
        "created_at",
        "updated_at",
    } <= cols

    fk_targets = {fk["referred_table"] for fk in insp.get_foreign_keys("financing_records")}
    assert {"vehicles", "vendors"} <= fk_targets

    # The CHECK constraint declared on the model must actually be enforced.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO financing_records (vin, date, amount, category) "
                    "VALUES (:vin, '2026-01-01', 100.00, 'other')"
                ),
                {"vin": "1FT0000000000000X"},
            )
