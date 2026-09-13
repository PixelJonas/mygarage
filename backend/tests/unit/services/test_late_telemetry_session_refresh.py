"""Telemetry that arrives after a session closes must update that session.

A WiCAN only reaches the broker on home WiFi. Off WiFi it buffers readings and
replays them on reconnect, through the ingest path's optional device timestamp,
so a reading taken at 10:48 can land at 11:42.

Session aggregates were computed once, in `end_session`, from whatever had
arrived by then. On Diamond that meant a drive whose only in-range samples were
the ones taken pulling out of the driveway: the session recorded max_speed
20 km/h while the replayed buffer held 85 km/h, and nothing ever revisited it.

The session's own window is the arbiter. A replayed reading whose timestamp
falls inside a closed session belongs to that session, however late it lands.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.drive_session import DriveSession
from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_parameter import LiveLinkParameter
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_telemetry import VehicleTelemetry
from app.services.telemetry_service import TelemetryService
from app.utils.datetime_utils import utc_now


@pytest_asyncio.fixture
async def make_closed_session(db_session, make_closed_drive_session):
    """Async factory: (suffix) -> (vin, device_id, session). See conftest."""

    async def _factory(suffix: str) -> tuple[str, str, DriveSession]:
        now = utc_now().replace(tzinfo=None)
        vin, device_id, session = await make_closed_drive_session(
            "latetel",
            suffix,
            started_at=now - timedelta(minutes=10),
            ended_at=now - timedelta(minutes=5),
            duration_seconds=300,
        )

        # A sample inside the window that the stored max_speed (20) does NOT
        # reflect. Without this, a session refreshed BY MISTAKE recomputes to
        # the same numbers and the negative tests below cannot fail: verified
        # by mutation, both survived until this row existed.
        db_session.add(
            VehicleTelemetry(
                vin=vin,
                device_id=device_id,
                param_key="0D-VEHICLESPEED",
                value=50.0,
                timestamp=session.started_at + timedelta(minutes=1),
                received_at=now,
            )
        )
        await db_session.flush()
        return vin, device_id, session

    return _factory


@pytest.mark.asyncio
class TestLateTelemetrySessionRefresh:
    """A replayed reading inside a closed session's window updates it."""

    async def test_replayed_reading_updates_the_closed_session_max_speed(
        self, db_session, make_closed_session
    ):
        """The buffered 85 km/h sample must reach the session it belongs to."""
        vin, device_id, session = await make_closed_session("1")
        inside = session.started_at + timedelta(minutes=2)

        await TelemetryService(db_session).store_telemetry(
            vin=vin,
            device_id=device_id,
            autopid_data={"0D-VEHICLESPEED": 85.0},
            config={},
            timestamp=inside,
        )
        await db_session.flush()
        await db_session.refresh(session)

        assert session.max_speed == 85.0, "late reading never reached the closed session"

    async def test_reading_outside_every_session_changes_nothing(
        self, db_session, make_closed_session
    ):
        """A reading in the gap between sessions must not be adopted by one.

        Sessions end on device connectivity, so there is real telemetry that
        belongs to no session. Attributing it to the nearest one would invent
        a drive the vehicle did not make.
        """
        vin, device_id, session = await make_closed_session("2")
        after = session.ended_at + timedelta(minutes=1)

        await TelemetryService(db_session).store_telemetry(
            vin=vin,
            device_id=device_id,
            autopid_data={"0D-VEHICLESPEED": 200.0},
            config={},
            timestamp=after,
        )
        await db_session.flush()
        await db_session.refresh(session)

        # 20.0 means untouched. A wrongly-matched session would recompute from
        # the 50 km/h sample seeded inside its window and read 50.0.
        assert session.max_speed == 20.0, "a reading outside the window was adopted"

    async def test_another_vehicles_reading_does_not_touch_the_session(
        self, db_session, make_closed_session
    ):
        """Window matching must be scoped by VIN, not by time alone."""
        vin_a, _dev_a, session_a = await make_closed_session("3")
        _vin_b, dev_b, _session_b = await make_closed_session("4")
        inside_a = session_a.started_at + timedelta(minutes=2)

        # Device B reports at a time that falls inside vehicle A's session too.
        await TelemetryService(db_session).store_telemetry(
            vin=_vin_b,
            device_id=dev_b,
            autopid_data={"0D-VEHICLESPEED": 150.0},
            config={},
            timestamp=inside_a,
        )
        await db_session.flush()
        await db_session.refresh(session_a)

        # 20.0 means untouched; a VIN-blind match would recompute A from its own
        # seeded 50 km/h sample and read 50.0.
        assert session_a.max_speed == 20.0, "another vehicle's reading leaked into this session"


@pytest_asyncio.fixture
async def no_autoflush_sessionmaker(test_engine, init_test_db) -> async_sessionmaker[AsyncSession]:
    """A sessionmaker matching production's autoflush=False (`app/database.py`).

    `test_sessionmaker` in `conftest.py` still autoflushes, which is exactly
    what let `test_replayed_reading_updates_the_closed_session_max_speed`
    above pass: the SELECT inside `refresh_aggregates` triggered an autoflush
    of the still-pending reading before it ran, standing in for the flush
    production never gets. `test_engine` alone never creates the schema, so
    this depends on `init_test_db` too, to keep this module runnable when it
    is the only file selected.
    """
    return async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def _seed_closed_session_no_autoflush(
    db: AsyncSession, prefix: str, suffix: str
) -> tuple[str, str, DriveSession]:
    """Build a closed session with a seeded 50 km/h sample, on the given session.

    Mirrors `make_closed_session` above, but takes its `AsyncSession` directly
    instead of the (autoflushing) `db_session` fixture, since
    `make_closed_drive_session` is bound to that fixture.
    """
    now = utc_now().replace(tzinfo=None)

    user = User(
        username=f"{prefix}_user_{suffix}",
        email=f"{prefix}_{suffix}@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    await db.flush()

    vin = f"{prefix.upper()}{suffix:0>6}"[-17:]
    db.add(Vehicle(vin=vin, user_id=user.id, nickname=f"{prefix} {suffix}", vehicle_type="Car"))
    await db.flush()

    device_id = f"{prefix}dev{suffix:0>4}"[-20:]
    db.add(LiveLinkDevice(device_id=device_id, vin=vin, enabled=True, kind="wican"))
    await db.flush()

    started_at = now - timedelta(minutes=10)
    session = DriveSession(
        vin=vin,
        device_id=device_id,
        started_at=started_at,
        ended_at=now - timedelta(minutes=5),
        duration_seconds=300,
        max_speed=20.0,
        avg_speed=10.0,
    )
    db.add(session)
    await db.flush()

    # A sample inside the window that the stored max_speed (20) does NOT
    # reflect, matching `make_closed_session` above.
    db.add(
        VehicleTelemetry(
            vin=vin,
            device_id=device_id,
            param_key="0D-VEHICLESPEED",
            value=50.0,
            timestamp=started_at + timedelta(minutes=1),
            received_at=now,
        )
    )
    await db.flush()
    return vin, device_id, session


@pytest.mark.asyncio
class TestLateTelemetrySessionRefreshWithoutAutoflush:
    """The same repair, proven on a session that does not autoflush for it.

    Production sessions never autoflush (`app/database.py`), so the class
    above proves nothing about whether `_refresh_closed_session` sees a
    reading this same call just added. These tests build their own session
    over `test_engine` to remove that autoflush safety net.
    """

    async def test_replayed_reading_raises_the_closed_session_max_speed_without_autoflush(
        self, no_autoflush_sessionmaker
    ):
        """The buffered 85 km/h sample must reach the session even unflushed."""
        async with no_autoflush_sessionmaker() as db:
            vin, device_id, session = await _seed_closed_session_no_autoflush(db, "latenoaf", "1")
            inside = session.started_at + timedelta(minutes=2)

            await TelemetryService(db).store_telemetry(
                vin=vin,
                device_id=device_id,
                autopid_data={"0D-VEHICLESPEED": 85.0},
                config={},
                timestamp=inside,
            )
            await db.flush()
            await db.refresh(session)

            assert session.max_speed == 85.0, "late reading never reached the closed session"

    async def test_the_same_reading_replayed_twice_is_stored_once_and_does_not_fail(
        self, no_autoflush_sessionmaker
    ):
        """A reading replayed twice in one unit of work must not raise, or duplicate.

        `storage_interval_seconds` is set explicitly to 0 (the model default
        and what auto-registration assigns a new parameter): a positive
        interval makes `_should_store_historical` skip the second insert
        outright and would hide the duplicate-key case this test is for.
        """
        async with no_autoflush_sessionmaker() as db:
            vin, device_id, session = await _seed_closed_session_no_autoflush(db, "latedup", "1")
            db.add(LiveLinkParameter(param_key="0D-VEHICLESPEED", storage_interval_seconds=0))
            await db.flush()
            inside = session.started_at + timedelta(minutes=2)

            first = await TelemetryService(db).store_telemetry(
                vin=vin,
                device_id=device_id,
                autopid_data={"0D-VEHICLESPEED": 85.0},
                config={},
                timestamp=inside,
            )
            second = await TelemetryService(db).store_telemetry(
                vin=vin,
                device_id=device_id,
                autopid_data={"0D-VEHICLESPEED": 85.0},
                config={},
                timestamp=inside,
            )
            await db.commit()

            assert first.stored_count == 1, "the first replay must be stored"
            assert second.stored_count == 0, "the duplicate replay must not count as stored"

            rows = (
                (
                    await db.execute(
                        select(VehicleTelemetry).where(
                            VehicleTelemetry.vin == vin,
                            VehicleTelemetry.device_id == device_id,
                            VehicleTelemetry.param_key == "0D-VEHICLESPEED",
                            VehicleTelemetry.timestamp == inside,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1, "the duplicate replay must not create a second row"

            await db.refresh(session)
            assert session.max_speed == 85.0, "the closed session must still see the reading"
