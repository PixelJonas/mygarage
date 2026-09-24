"""A scripted Torque drive, asserted end to end through the real route.

Every test seeds its OWN vehicle and device under a uuid suffix and tears them
down. The suite shares one database with no per-test rollback (see the docstring
of tests/unit/services/conftest.py), so a shared `test_vehicle` VIN and a
hardcoded device id would collide on the second test and would also see rows
left by every other suite. This mirrors tests/integration/test_livelink_odometer_rows.py.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.drive_session import DriveSession
from app.models.livelink_device import LiveLinkDevice
from app.models.location_point import LocationPoint
from app.models.vehicle import Vehicle
from app.models.vehicle_telemetry import VehicleTelemetry
from app.services.livelink_service import LiveLinkService
from scripts.torque_sim import build_drive

# LiveLink's master switch gates the ingest pipeline and SD backfill, and it is
# off by default. Explicit, not inherited from whatever an earlier test left in
# the shared database.
pytestmark = pytest.mark.usefixtures("livelink_enabled")


@pytest_asyncio.fixture
async def torque_source(db_session, test_user):
    """An isolated vehicle plus Torque source: `(token, vin, device_id)`."""
    suffix = uuid.uuid4().hex[:10]
    vin = f"TQSIM{suffix.upper()}XX"[:17]
    device_id = f"tqsim{suffix}"
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="Torque sim",
            vehicle_type="Car",
        )
    )
    await db_session.flush()
    # generate_token is a @staticmethod returning str (livelink_service.py:60).
    token = LiveLinkService.generate_token()
    db_session.add(
        LiveLinkDevice(
            device_id=device_id,
            kind="torque",
            vin=vin,
            label="Simulated phone",
            torque_device_id=suffix.ljust(32, "0")[:32],
            device_token_hash=LiveLinkService.hash_token(token),
            enabled=True,
        )
    )
    await db_session.commit()
    yield token, vin, device_id
    for model in (DriveSession, VehicleTelemetry, LocationPoint):
        await db_session.execute(delete(model).where(model.vin == vin))
    await db_session.execute(delete(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id))
    await db_session.execute(delete(Vehicle).where(Vehicle.vin == vin))
    await db_session.commit()


@pytest.mark.asyncio
async def test_a_scripted_drive_produces_a_session_telemetry_and_a_track(
    client, db_session, torque_source
):
    token, vin, _device_id = torque_source
    for frame in build_drive(session_id="1001", minutes=10, start_odometer_mi=90170):
        resp = await client.get(f"/api/v1/torque/{token}/upload", params=frame)
        assert resp.status_code == 200
        assert resp.text == "OK!"

    sessions = (
        (await db_session.execute(select(DriveSession).where(DriveSession.vin == vin)))
        .scalars()
        .all()
    )
    assert len(sessions) == 1

    telemetry = (
        (await db_session.execute(select(VehicleTelemetry).where(VehicleTelemetry.vin == vin)))
        .scalars()
        .all()
    )
    assert {"ENGINE_RPM", "SPEED", "COOLANT_TMP"} <= {t.param_key for t in telemetry}

    points = (
        (await db_session.execute(select(LocationPoint).where(LocationPoint.vin == vin)))
        .scalars()
        .all()
    )
    assert len(points) >= 2, "GPS frames must become location_points"
    assert all(p.drive_session_id == sessions[0].id for p in points)


@pytest.mark.asyncio
async def test_a_second_session_id_opens_a_second_drive(client, db_session, torque_source):
    token, vin, _device_id = torque_source
    for sid in ("2001", "2002"):
        for frame in build_drive(session_id=sid, minutes=3, start_odometer_mi=90170):
            await client.get(f"/api/v1/torque/{token}/upload", params=frame)
    sessions = (
        (await db_session.execute(select(DriveSession).where(DriveSession.vin == vin)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2


def test_frames_are_ordered_and_land_in_the_past():
    """The route clamps a FUTURE device clock, so a drive starting now collapses."""
    import time

    frames = build_drive(session_id="3001", minutes=5, start_odometer_mi=90170)
    times = [int(f["time"]) for f in frames]
    assert times == sorted(times)
    assert len(set(times)) == len(times), "duplicate timestamps would dedupe away"
    now_ms = int(time.time() * 1000)
    assert times[-1] <= now_ms, "a future clock is clamped to now and flattens the drive"


def test_the_odometer_frame_is_present_and_advances():
    """Feeds Task 17: ff120C is the parameter a user would select."""
    frames = build_drive(session_id="4001", minutes=5, start_odometer_mi=90170)
    odo = [float(f["kff120c"]) for f in frames if "kff120c" in f]
    assert odo, "the simulator must emit an odometer PID"
    assert odo[-1] > odo[0]
