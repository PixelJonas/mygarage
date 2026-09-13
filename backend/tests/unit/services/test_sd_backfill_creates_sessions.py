"""An SD-card backfill creates the sessions its rows describe. C10.

This is the motivating case for the whole boundary rework, and the case the
design's first revision did not fix.

``bulk_backfill`` called only ``_refresh_sessions_in_span``, which selects
``WHERE DriveSession.ended_at IS NOT NULL`` -- sessions that **already exist and
are already closed**. It had never created one. Every decision in that first
revision changed live ingest, and the SD card is the only path for anything
driven out of broker range: off home WiFi the WiCAN reaches no broker at all, so
a whole drive arrives here hours later. On 2026-09-01 the Ram drove 16.0 km and
was credited 3.0 across three sessions; the Mirage drove 10.0 km and was
credited 0.0 across fifteen, thirteen of which held no telemetry at all.

Two constraints shape the implementation and each has a test:

**Once per call, not once per row.** Running the live side-effects per row is
precisely what ``bulk_backfill`` exists to avoid, and a pull is tens of
thousands of rows.

**The span must not be narrowed to inserted rows.** It is built from all
*parsed* rows on purpose: the rows commit in batches here while
``SdBackfillService`` saves the file watermark only after this returns, so a
crash between the two leaves the rows imported and their sessions never
recomputed. The retry re-parses, every row conflicts, and a span built from
inserts would be empty -- losing the refresh permanently. An earlier design
revision described this as a "quadratic" defect and would have had an
implementer narrow exactly that.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.drive_session import DriveSession
from app.models.livelink_device import LiveLinkDevice
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.sd_log_parser import SdRow
from app.services.session_boundaries import group_drives
from app.services.telemetry_service import TelemetryService

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 9, 1, 8, 0, 0)
GAP = 15


async def _sessions(db: AsyncSession, device_id: str) -> list[DriveSession]:
    return list(
        (
            await db.execute(
                select(DriveSession)
                .where(DriveSession.device_id == device_id)
                .order_by(DriveSession.started_at)
            )
        )
        .scalars()
        .all()
    )


def _rows(*specs: tuple[int, str, float]) -> list[SdRow]:
    """`(minute_offset, param_key, value)` triples as SdRows."""
    return [
        SdRow(param_key=key, value=value, timestamp=T0 + timedelta(minutes=offset))
        for offset, key, value in specs
    ]


class TestItCreatesSessions:
    async def test_a_replayed_drive_creates_a_session(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """The Ram's missing kilometres, in the smallest form that shows them."""
        vin, device = await make_livelink_vehicle("sdcreate", "1")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "A6-ODOMETER", 50_000.0),
                (1, "SPEED", 45.0),
                (2, "SPEED", 62.0),
                (3, "A6-ODOMETER", 50_004.0),
                (4, "SPEED", 40.0),
            ),
        )

        sessions = await _sessions(db_session, device.device_id)
        assert len(sessions) == 1, "the SD path has never created a session before this"
        assert sessions[0].boundary_algorithm_version == 1
        assert sessions[0].effective_gap_minutes == GAP
        assert sessions[0].ended_at is not None, "a replayed drive is over; it must not be open"

    async def test_the_created_session_gets_its_distance(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """Creating the row is only half of it: the point is the credited distance."""
        vin, device = await make_livelink_vehicle("sdcreate", "2")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "A6-ODOMETER", 50_000.0),
                (1, "SPEED", 45.0),
                (5, "SPEED", 55.0),
                (9, "A6-ODOMETER", 50_013.0),
            ),
        )

        session = (await _sessions(db_session, device.device_id))[0]
        assert session.distance_km == pytest.approx(13.0)

    async def test_the_window_keeps_the_opening_odometer(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """C5 applies to replay too, or the two paths disagree about one drive."""
        vin, device = await make_livelink_vehicle("sdcreate", "3")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "ENGINE_RPM", 700.0),
                (0, "A6-ODOMETER", 60_000.0),
                (3, "SPEED", 50.0),
                (4, "SPEED", 50.0),
                (8, "A6-ODOMETER", 60_009.0),
            ),
        )

        session = (await _sessions(db_session, device.device_id))[0]
        assert session.started_at == T0, "the ignition-time burst must be in the window"
        assert session.start_odometer == 60_000.0

    async def test_two_drives_separated_by_the_gap_become_two_sessions(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        vin, device = await make_livelink_vehicle("sdcreate", "4")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "SPEED", 45.0),
                (1, "SPEED", 50.0),
                # 40 minutes parked, well past the 15-minute drive gap.
                (41, "SPEED", 48.0),
                (42, "SPEED", 52.0),
            ),
        )

        sessions = await _sessions(db_session, device.device_id)
        assert len(sessions) == 2

    async def test_a_stop_inside_the_gap_stays_one_session(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """The same rule the live path uses, so a drive is cut the same way
        whichever path it arrived by. Scoping the gap to reconstruction only --
        which an earlier revision did -- means one journey gets two different
        answers depending on how it reached the database."""
        vin, device = await make_livelink_vehicle("sdcreate", "5")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "SPEED", 45.0),
                (1, "SPEED", 50.0),
                (8, "SPEED", 48.0),  # 7 minutes later: inside the gap
                (9, "SPEED", 52.0),
            ),
        )

        assert len(await _sessions(db_session, device.device_id)) == 1


class TestItRefusesToInventDrives:
    async def test_a_parked_heartbeat_file_creates_nothing(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """A month of SD rows from a parked vehicle must stay a month of nothing.

        This is the assertion that makes the rest safe: a replay path that
        creates a session per contact burst would manufacture thousands of
        phantom drives from history, which is strictly worse than the bug being
        fixed because there is no upgrade that undoes it.
        """
        vin, device = await make_livelink_vehicle("sdrefuse", "1")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(*[(m * 95, "BATTERY_VOLTAGE", 12.4) for m in range(20)]),
        )

        assert await _sessions(db_session, device.device_id) == []

    async def test_an_idle_only_file_creates_nothing(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        vin, device = await make_livelink_vehicle("sdrefuse", "2")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(*[(m, "ENGINE_RPM", 750.0) for m in range(12)]),
        )

        assert await _sessions(db_session, device.device_id) == []

    async def test_a_single_speed_spike_creates_nothing(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """The same debounce the live path applies. One sample is not a drive."""
        vin, device = await make_livelink_vehicle("sdrefuse", "3")

        await TelemetryService(db_session).bulk_backfill(
            vin, device.device_id, _rows((0, "SPEED", 48.0))
        )

        assert await _sessions(db_session, device.device_id) == []

    async def test_an_unchanged_odometer_creates_nothing(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        vin, device = await make_livelink_vehicle("sdrefuse", "4")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows((0, "A6-ODOMETER", 70_000.0), (95, "A6-ODOMETER", 70_000.0)),
        )

        assert await _sessions(db_session, device.device_id) == []

    async def test_an_unlinked_device_creates_nothing(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        vin, device = await make_livelink_vehicle("sdrefuse", "5")
        device.vin = None
        await db_session.flush()

        await TelemetryService(db_session).bulk_backfill(
            vin, device.device_id, _rows((0, "SPEED", 45.0), (1, "SPEED", 50.0))
        )

        assert await _sessions(db_session, device.device_id) == []


class TestItDoesNotOverlapExistingSessions:
    async def test_a_drive_already_recorded_is_extended_not_duplicated(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """The common case on a device with intermittent WiFi.

        Part of the drive reached the broker live and opened a session; the rest
        arrives off the SD card. Creating a second session for the same journey
        would leave two overlapping windows, and every aggregate here is a
        window scan -- so both would claim the same samples and both report the
        same distance, doubling the vehicle's apparent mileage.
        """
        vin, device = await make_livelink_vehicle("sdoverlap", "1")
        live_part = DriveSession(
            vin=vin,
            device_id=device.device_id,
            started_at=T0,
            ended_at=T0 + timedelta(minutes=2),
            boundary_algorithm_version=1,
            effective_gap_minutes=GAP,
        )
        db_session.add(live_part)
        await db_session.flush()

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "A6-ODOMETER", 80_000.0),
                (1, "SPEED", 45.0),
                (2, "SPEED", 50.0),
                (6, "SPEED", 55.0),
                (7, "A6-ODOMETER", 80_011.0),
            ),
        )

        sessions = await _sessions(db_session, device.device_id)
        assert len(sessions) == 1, f"expected the session to be extended, got {len(sessions)}"
        assert sessions[0].id == live_part.id
        assert sessions[0].ended_at >= T0 + timedelta(minutes=6)
        assert sessions[0].distance_km == pytest.approx(11.0)

    async def test_a_torque_session_is_never_extended(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """Torque supplies an authoritative session id from the phone.

        Re-bounding it on a gap threshold replaces good evidence with inference.
        Excluded by `external_session_id`, not by heuristic.
        """
        vin, device = await make_livelink_vehicle("sdoverlap", "2")
        torque = DriveSession(
            vin=vin,
            device_id=device.device_id,
            started_at=T0,
            ended_at=T0 + timedelta(minutes=2),
            external_session_id="phone-1",
        )
        db_session.add(torque)
        await db_session.flush()
        original_end = torque.ended_at

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows((1, "SPEED", 45.0), (2, "SPEED", 50.0), (6, "SPEED", 55.0)),
        )

        await db_session.refresh(torque)
        assert torque.ended_at == original_end, "a phone-bounded session must not be re-bounded"

    async def test_no_two_output_sessions_overlap(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """Nothing in the schema forbids overlapping windows -- the time indexes
        are non-unique -- so this is asserted rather than assumed."""
        vin, device = await make_livelink_vehicle("sdoverlap", "3")

        await TelemetryService(db_session).bulk_backfill(
            vin,
            device.device_id,
            _rows(
                (0, "SPEED", 45.0),
                (1, "SPEED", 50.0),
                (40, "SPEED", 48.0),
                (41, "SPEED", 52.0),
                (90, "SPEED", 44.0),
                (91, "SPEED", 46.0),
            ),
        )

        sessions = await _sessions(db_session, device.device_id)
        assert len(sessions) == 3
        for earlier, later in zip(sessions, sessions[1:], strict=False):
            assert earlier.ended_at <= later.started_at, (
                f"session {earlier.id} ends {earlier.ended_at}, "
                f"session {later.id} starts {later.started_at}"
            )


class TestItRunsOncePerCall:
    async def test_reconstruction_runs_once_regardless_of_row_count(
        self, db_session: AsyncSession, make_livelink_vehicle, monkeypatch
    ):
        """Running the live side-effects per row is what this method exists to
        avoid, and a real pull is tens of thousands of rows."""
        vin, device = await make_livelink_vehicle("sdonce", "1")
        service = TelemetryService(db_session)

        calls = []
        original = service._reconstruct_sessions_from_batch

        async def counting(*args, **kwargs):
            calls.append(args)
            return await original(*args, **kwargs)

        monkeypatch.setattr(service, "_reconstruct_sessions_from_batch", counting)

        rows = _rows(*[(m, "SPEED", 45.0 + m) for m in range(60)])
        await service.bulk_backfill(vin, device.device_id, rows)

        assert len(calls) == 1, f"called {len(calls)} times for {len(rows)} rows"

    async def test_the_span_is_built_from_parsed_rows_not_inserted_ones(
        self, db_session: AsyncSession, make_livelink_vehicle
    ):
        """Re-running an identical batch must still refresh, though it inserts 0.

        The rows commit in batches here while `SdBackfillService` saves the file
        watermark only after this returns. A crash in between leaves the rows
        imported and their sessions never recomputed; the retry re-parses, every
        row conflicts, and a span built from INSERTS would be empty -- losing
        the refresh permanently rather than redoing it.
        """
        vin, device = await make_livelink_vehicle("sdonce", "2")
        service = TelemetryService(db_session)
        rows = _rows(
            (0, "A6-ODOMETER", 90_000.0),
            (1, "SPEED", 45.0),
            (2, "SPEED", 50.0),
            (5, "A6-ODOMETER", 90_007.0),
        )

        inserted_first = await service.bulk_backfill(vin, device.device_id, rows)
        assert inserted_first > 0

        session = (await _sessions(db_session, device.device_id))[0]
        session.distance_km = 999.0  # a stale figure a refresh must correct
        await db_session.flush()

        inserted_again = await service.bulk_backfill(vin, device.device_id, rows)
        assert inserted_again == 0, "every row should have conflicted"

        await db_session.refresh(session)
        assert session.distance_km == pytest.approx(7.0), (
            "the refresh was skipped, which is what a span built from inserts does"
        )


# P4: session reconstruction at a boundary two drives share.
#
# Drive 1 moves at minutes 0 and 5. A contact-only sample at minute 15 (RPM,
# below the movement floor, no odometer proof) chains `group_drives`' walk-back
# for drive 2 all the way back through drive 1's own burst, so the "never reach
# back into a drive already accounted for" clamp fires: drive 2's `started_at`
# is pinned to drive 1's `movement_ended_at` (minute 5) instead of the earlier
# instant the walk-back would otherwise have found. That shared instant is the
# boundary these tests pin.
_BOUNDARY_SPECS: tuple[tuple[int, str, float], ...] = (
    (0, "A6-ODOMETER", 50_000.0),
    (0, "SPEED", 45.0),
    (5, "SPEED", 50.0),
    (15, "ENGINE_RPM", 700.0),
    (25, "SPEED", 48.0),
    (30, "SPEED", 52.0),
    (30, "A6-ODOMETER", 50_010.0),
)


def _boundary_samples() -> list[tuple[datetime, str, float]]:
    return [(T0 + timedelta(minutes=m), key, value) for m, key, value in _BOUNDARY_SPECS]


# A later pull that widens both drives without crossing the shared instant:
# minute -10 joins drive 1's burst (drive 1's own end stays at minute 5), and
# minute 35 joins drive 2's (drive 2's own start stays at minute 5).
_EXTENSION_SPECS: tuple[tuple[int, str, float], ...] = (
    (-10, "SPEED", 55.0),
    (35, "SPEED", 60.0),
)


def _boundary_and_extension_samples() -> list[tuple[datetime, str, float]]:
    return [
        (T0 + timedelta(minutes=m), key, value)
        for m, key, value in (*_BOUNDARY_SPECS, *_EXTENSION_SPECS)
    ]


async def _seed_device(
    maker: async_sessionmaker[AsyncSession], prefix: str, suffix: str
) -> tuple[str, str]:
    """Seed a user/vehicle/device on their own committed transaction.

    Mirrors `make_livelink_vehicle`, but commits rather than flushes: the
    reconstruction calls below open their own sessions on this same engine,
    and a merely-flushed row is invisible to a different connection.
    """
    async with maker() as db:
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
        await db.commit()

    return vin, device_id


async def _session_rows(
    maker: async_sessionmaker[AsyncSession], device_id: str
) -> list[tuple[int, datetime, datetime | None, float | None, float | None]]:
    """`(id, started_at, ended_at, distance_km, max_speed)` for every session.

    Read into plain tuples inside the session block on purpose: the objects
    themselves must not be touched after their session closes.
    """
    async with maker() as db:
        rows = await _sessions(db, device_id)
        return [(s.id, s.started_at, s.ended_at, s.distance_km, s.max_speed) for s in rows]


class TestGroupDrivesSharedBoundary:
    """Step 1, encoded: where `group_drives` puts the shared instant.

    Pure and database-free on purpose -- a bound mutation here proves nothing
    about whether the overlap query in `_reconstruct_sessions_from_batch` can
    see an earlier drive's pending session, which is what the next two tests
    are for.
    """

    def test_group_drives_gives_a_shared_boundary_to_one_drive(self):
        drives = group_drives(_boundary_samples(), GAP)

        assert len(drives) == 2, f"expected 2 drives, got {len(drives)}"
        first, second = drives
        assert first.started_at == T0
        assert first.movement_started_at == T0
        assert first.movement_ended_at == T0 + timedelta(minutes=5)

        assert second.started_at == T0 + timedelta(minutes=5)
        assert second.movement_started_at == T0 + timedelta(minutes=25)
        assert second.movement_ended_at == T0 + timedelta(minutes=30)

        # The shared instant is drive 1's own `movement_ended_at` -- real
        # evidence drive 1 recorded. Drive 2's `started_at` at that same
        # instant is only the clamp floor, not evidence of its own: drive 2's
        # actual movement does not begin until twenty minutes later. The
        # instant belongs to drive 1.
        shared = first.movement_ended_at
        assert second.started_at == shared
        assert second.movement_started_at > shared, (
            "drive 2 has no evidence at the shared instant; it is drive 1's "
            "movement_ended_at, borrowed only as a floor"
        )


class TestReconstructionAtATouchingBoundary:
    """P4: the two drives `TestGroupDrivesSharedBoundary` describes, replayed
    through `_reconstruct_sessions_from_batch` on a session that does not
    autoflush, the way `app/database.py` builds every production session.

    The shared `db_session` fixture autoflushes, which would silently reveal
    an in-loop, unflushed session to the next drive's overlap query -- a unit
    of work production never runs. Builds its own session over `test_engine`
    instead, matching `test_tire_periods.py`'s
    `TestEditorUnderProductionUnitOfWork`.
    """

    @staticmethod
    def _maker(test_engine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    async def test_two_touching_drives_in_one_batch_make_two_sessions(
        self, test_engine, init_test_db
    ):
        maker = self._maker(test_engine)
        vin, device_id = await _seed_device(maker, "sdbound", "1")

        async with maker() as db:
            await TelemetryService(db).bulk_backfill(vin, device_id, _rows(*_BOUNDARY_SPECS))

        expected = group_drives(_boundary_samples(), GAP)
        rows = await _session_rows(maker, device_id)

        assert len(rows) == 2, f"expected 2 sessions, got {len(rows)}"
        (_, start1, end1, _, _), (_, start2, end2, _, _) = rows
        assert start1 == expected[0].started_at
        assert end1 == expected[0].movement_ended_at
        assert start2 == expected[1].started_at
        assert end2 == expected[1].movement_ended_at

        # Ownership rule: the shared instant is drive 1's, so the windows
        # touch at it without overlapping.
        assert end1 == start2

    async def test_running_the_same_backfill_twice_keeps_the_sessions(
        self, test_engine, init_test_db
    ):
        maker = self._maker(test_engine)
        vin, device_id = await _seed_device(maker, "sdbound", "2")
        rows_in = _rows(*_BOUNDARY_SPECS)

        async with maker() as db:
            await TelemetryService(db).bulk_backfill(vin, device_id, rows_in)
        first_run = await _session_rows(maker, device_id)
        assert len(first_run) == 2, f"expected 2 sessions after the first run, got {len(first_run)}"

        async with maker() as db:
            await TelemetryService(db).bulk_backfill(vin, device_id, rows_in)
        second_run = await _session_rows(maker, device_id)

        assert [r[0] for r in second_run] == [r[0] for r in first_run], (
            "the same replay must not create or drop a session"
        )
        assert [r[1:3] for r in second_run] == [r[1:3] for r in first_run], (
            "the same replay must not move a window"
        )
        assert [r[3:] for r in second_run] == [r[3:] for r in first_run], (
            "the same replay must not change distance or max speed"
        )

    async def test_a_rerun_that_extends_a_touching_drive_updates_its_own_session(
        self, test_engine, init_test_db
    ):
        """A later pull can legitimately widen one drive's window without
        crossing into its neighbour's. That widened drive must still find
        and extend its own session -- not get treated as spanning both
        sessions at the touching boundary, which is what the false
        "ambiguous" match there otherwise causes, silently dropping the
        extension.

        Extends both directions at once: drive 2's real evidence grows
        past its old end, and drive 1's grows before its old start, short
        of the shared instant -- so both of the query's two comparisons
        are exercised, not just the one the second drive's own overlap
        check uses.
        """
        maker = self._maker(test_engine)
        vin, device_id = await _seed_device(maker, "sdbound", "3")

        async with maker() as db:
            await TelemetryService(db).bulk_backfill(vin, device_id, _rows(*_BOUNDARY_SPECS))
        first_run = await _session_rows(maker, device_id)
        assert len(first_run) == 2, f"expected 2 sessions after the first run, got {len(first_run)}"

        async with maker() as db:
            await TelemetryService(db).bulk_backfill(
                vin, device_id, _rows(*_BOUNDARY_SPECS, *_EXTENSION_SPECS)
            )
        second_run = await _session_rows(maker, device_id)

        expected = group_drives(_boundary_and_extension_samples(), GAP)
        assert len(second_run) == 2, f"expected 2 sessions, no third one, got {len(second_run)}"
        assert [r[0] for r in second_run] == [r[0] for r in first_run], (
            "the extension must update the drives' own sessions, not create new ones"
        )
        (_, start1, end1, _, speed1), (_, start2, end2, _, speed2) = second_run
        assert start1 == expected[0].started_at, "drive 1's backward extension must move its start"
        assert end1 == expected[0].movement_ended_at, (
            "drive 1's end must stay at the shared instant"
        )
        assert start2 == expected[1].started_at, "drive 2's start must stay at the shared instant"
        assert end2 == expected[1].movement_ended_at, (
            "drive 2's forward extension must move its end"
        )
        assert speed1 == pytest.approx(55.0), "session 1's aggregates must reflect the new sample"
        assert speed2 == pytest.approx(60.0), "session 2's aggregates must reflect the new sample"
