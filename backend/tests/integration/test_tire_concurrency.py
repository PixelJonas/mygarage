"""Two tire writes racing on one vehicle serialise instead of colliding.

Before this file, two simultaneous mounts at one corner both read the corner
as free and both wrote. `uq_tires_vin_position` failed the loser's whole
transaction, so the data stayed correct and the user got a 500. With the
vehicle write lock the loser waits, re-reads under the lock, and gets the
409 the code already had for that case.

Lives in `tests/integration/` so CI runs it under PostgreSQL as well as SQLite,
and it means something under both: on SQLite the lock is `BEGIN IMMEDIATE`,
on PostgreSQL it is `SELECT ... FOR UPDATE` on the vehicle row. Two real
connections, so it builds its own sessions rather than using `client`, which
hands ONE session to every request and therefore cannot race.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select, text

import app.services.tire_service as tire_service_module
import app.services.tire_set_service as tire_set_service_module
from app.models.tire import Tire, TireMountPeriod
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.tire import TireMountRequest
from app.services.tire_service import TireService
from app.services.vehicle_lock import LOCK_CONTRACT, lock_vehicle_for_write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed(db_session) -> tuple[str, User, int, int]:
    """A committed admin, vehicle and two stored tires every racer can see."""
    prefix = f"race{uuid.uuid4().hex[:6]}"
    user = User(
        username=f"{prefix}_user",
        email=f"{prefix}@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    vin = f"{prefix.upper()}00000000000"[:17]
    db_session.add(Vehicle(vin=vin, user_id=user.id, nickname=prefix, vehicle_type="Car"))
    await db_session.flush()
    a = Tire(vin=vin, brand=f"{prefix}-a")
    b = Tire(vin=vin, brand=f"{prefix}-b")
    db_session.add_all([a, b])
    await db_session.commit()
    return vin, user, a.id, b.id


async def _mount(sessionmaker, user: User, vin: str, tire_id: int):
    async with sessionmaker() as db:
        return await TireService(db).mount_tire(vin, tire_id, TireMountRequest(position="FL"), user)


class TestCornerRace:
    async def test_two_racing_mounts_yield_one_success_and_one_409(
        self, db_session, test_sessionmaker, monkeypatch
    ):
        vin, user, a_id, b_id = await _seed(db_session)

        # Hold each racer for a second after it has loaded its tire, so both
        # read before either writes. A hold rather than a barrier: with the
        # lock in place the loser blocks INSIDE the driver and never reaches a
        # barrier, which would deadlock the winner.
        original = TireService._get_tire_for_update

        async def slow(self, vin_, tire_id):
            tire = await original(self, vin_, tire_id)
            await asyncio.sleep(1.0)
            return tire

        monkeypatch.setattr(TireService, "_get_tire_for_update", slow)

        results = await asyncio.gather(
            _mount(test_sessionmaker, user, vin, a_id),
            _mount(test_sessionmaker, user, vin, b_id),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, BaseException)]
        refusals = [r for r in results if isinstance(r, HTTPException)]
        others = [
            r for r in results if isinstance(r, BaseException) and not isinstance(r, HTTPException)
        ]
        # Without the lock the loser raises IntegrityError here, not a 409.
        assert others == [], f"unexpected exception types: {others!r}"
        assert len(successes) == 1
        assert len(refusals) == 1 and refusals[0].status_code == 409

        async with test_sessionmaker() as db:
            at_fl = (
                await db.execute(
                    select(func.count(Tire.id)).where(Tire.vin == vin, Tire.position == "FL")
                )
            ).scalar()
            open_at_fl = (
                await db.execute(
                    select(func.count(TireMountPeriod.id))
                    .join(Tire, Tire.id == TireMountPeriod.tire_id)
                    .where(
                        Tire.vin == vin,
                        TireMountPeriod.position == "FL",
                        TireMountPeriod.dismounted_on.is_(None),
                    )
                )
            ).scalar()
        assert at_fl == 1
        assert open_at_fl == 1


class TestLockHelper:
    async def test_helper_refuses_to_nest_inside_an_open_transaction(self, test_sessionmaker):
        """SQLite only: a call made after a write has begun is a contract violation.

        Pins the guard. Without it the second BEGIN surfaces as a driver error
        mapped to a 503, which is the wrong diagnosis for a programming mistake.
        """
        async with test_sessionmaker() as db:
            if db.get_bind().dialect.name != "sqlite":
                pytest.skip("the nesting guard exists for SQLite's BEGIN IMMEDIATE only")
            await db.execute(text("BEGIN IMMEDIATE"))
            with pytest.raises(RuntimeError, match=LOCK_CONTRACT[:40]):
                await lock_vehicle_for_write(db, "X" * 17)
            await db.rollback()

    async def test_helper_succeeds_after_a_plain_read(self, test_sessionmaker):
        """Pins the driver mode the helper depends on.

        The pysqlite driver runs a SELECT in autocommit, so the permission check
        that precedes every writer leaves no transaction open. If the driver
        ever moves to the non-legacy mode, this is the test that fails first,
        by name.
        """
        async with test_sessionmaker() as db:
            await db.execute(select(Vehicle).limit(1))
            await lock_vehicle_for_write(db, "X" * 17)
            await db.rollback()


@pytest.fixture
def lock_calls(monkeypatch) -> list[str]:
    """Record every VIN the lock is taken for, without changing what it does."""
    calls: list[str] = []
    real = lock_vehicle_for_write

    async def recording(db, vin):
        calls.append(vin)
        await real(db, vin)

    monkeypatch.setattr(tire_service_module, "lock_vehicle_for_write", recording)
    monkeypatch.setattr(tire_set_service_module, "lock_vehicle_for_write", recording)
    return calls


class TestEveryWriterTakesTheLock:
    async def test_each_position_or_period_writer_locks_once(
        self, client: AsyncClient, auth_headers, db_session, test_user, lock_calls
    ):
        vin = f"LOCK{uuid.uuid4().hex[:9].upper()}"[:17]
        db_session.add(
            Vehicle(vin=vin, user_id=test_user["id"], nickname="Lock", vehicle_type="Car")
        )
        await db_session.commit()
        h = auth_headers
        base = f"/api/vehicles/{vin}/tires"

        # 1. create-and-mount
        r = await client.post(
            f"{base}/create-and-mount", headers=h, json={"vin": vin, "position": "FL", "brand": "A"}
        )
        assert r.status_code == 201, r.text
        fl = r.json()["id"]
        # a stored tire, through the unlocked create (not a position writer)
        r = await client.post(base, headers=h, json={"vin": vin, "brand": "B"})
        assert r.status_code == 201, r.text
        stored = r.json()["id"]
        # 2. mount
        r = await client.post(f"{base}/{stored}/mount", headers=h, json={"position": "FR"})
        assert r.status_code == 200, r.text
        # 3. rotate: a two-tire swap
        r = await client.post(
            f"{base}/rotate",
            headers=h,
            json={
                "moves": [{"tire_id": fl, "position": "FR"}, {"tire_id": stored, "position": "FL"}]
            },
        )
        assert r.status_code == 200, r.text
        # 4. dismount
        r = await client.post(f"{base}/{stored}/dismount", headers=h, json={})
        assert r.status_code == 200, r.text
        # 4b. edit a period (needs the id of fl's open period)
        listed = await client.get(base, headers=h)
        fl_open = next(
            p
            for t in listed.json()["tires"]
            if t["id"] == fl
            for p in t["mount_periods"]
            if p["dismounted_on"] is None
        )
        r = await client.put(
            f"{base}/{fl}/mount-periods/{fl_open['id']}", headers=h, json={"notes": "edited"}
        )
        assert r.status_code == 200, r.text
        # 5. set fit: file the stored tire into a set, then fit the set
        r = await client.post(f"/api/vehicles/{vin}/tire-sets", headers=h, json={"name": "Set"})
        assert r.status_code == 201, r.text
        set_id = r.json()["id"]
        r = await client.put(f"{base}/{stored}", headers=h, json={"set_id": set_id})
        assert r.status_code == 200, r.text
        r = await client.post(f"/api/vehicles/{vin}/tire-sets/{set_id}/mount", headers=h, json={})
        assert r.status_code == 200, r.text
        # 6. retire
        r = await client.post(f"{base}/{fl}/retire", headers=h, json={})
        assert r.status_code == 200, r.text
        # 6b. restore
        r = await client.post(f"{base}/{fl}/restore", headers=h)
        assert r.status_code == 200, r.text
        # 7. delete
        r = await client.delete(f"{base}/{stored}", headers=h)
        assert r.status_code == 204, r.text

        assert lock_calls == [vin] * 9, lock_calls
