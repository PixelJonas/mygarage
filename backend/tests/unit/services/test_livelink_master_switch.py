"""LiveLink's master switch gates the ingest pipeline.

Before Plan 3 "Enable LiveLink" gated only the HTTPS route and the periodic
jobs; MQTT messages and Torque uploads went through `ingest()` and stored data
with it off, while the integrations card painted every tab "Disabled".

Each test sets the switch itself and the shared database gets its prior value
back, so nothing here depends on what an earlier test left behind.
"""

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_device import LiveLinkDevice
from app.models.settings import Setting
from app.models.vehicle_telemetry import VehicleTelemetry
from app.services.livelink_ingest import ingest
from app.services.livelink_sources.base import MqttEnvelope
from app.services.livelink_sources.wican import WicanModule

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def switch(db_session: AsyncSession):
    """Set the master switch; the prior value comes back afterwards."""
    existing = await db_session.get(Setting, "livelink_enabled")
    previous = existing.value if existing is not None else None

    async def _set(on: bool) -> None:
        row = await db_session.get(Setting, "livelink_enabled")
        value = "true" if on else "false"
        if row is None:
            db_session.add(Setting(key="livelink_enabled", value=value))
        else:
            row.value = value
        await db_session.commit()

    yield _set

    row = await db_session.get(Setting, "livelink_enabled")
    if previous is None:
        if row is not None:
            await db_session.delete(row)
    elif row is not None:
        row.value = previous
    await db_session.commit()


async def _frame(db: AsyncSession, device_id: str, subtopic: str, payload: dict) -> None:
    await ingest(
        WicanModule(),
        MqttEnvelope(f"wican/{device_id}/{subtopic}", json.dumps(payload).encode()),
        db,
    )


async def _rows(db: AsyncSession, device_id: str) -> int:
    return len(
        (
            await db.execute(
                select(VehicleTelemetry).where(VehicleTelemetry.device_id == device_id)
            )
        ).all()
    )


async def test_nothing_is_stored_while_switched_off(
    db_session: AsyncSession, make_livelink_vehicle, switch
):
    _vin, device = await make_livelink_vehicle("mswoff", "1")
    device_id = device.device_id
    await db_session.commit()
    await switch(False)

    await _frame(db_session, device_id, "can/rx", {"0D-VEHICLESPEED": 50})

    assert await _rows(db_session, device_id) == 0
    db_session.expire_all()
    last_seen = (
        await db_session.execute(
            select(LiveLinkDevice.last_seen).where(LiveLinkDevice.device_id == device_id)
        )
    ).scalar_one()
    assert last_seen is None


async def test_the_same_frame_is_stored_once_switched_on(
    db_session: AsyncSession, make_livelink_vehicle, switch
):
    """The positive control: without it, the test above passes against a
    frame the pipeline would never have stored anyway."""
    _vin, device = await make_livelink_vehicle("mswon", "1")
    device_id = device.device_id
    await db_session.commit()
    await switch(True)

    await _frame(db_session, device_id, "can/rx", {"0D-VEHICLESPEED": 50})

    assert await _rows(db_session, device_id) == 1


async def test_no_new_device_is_discovered_while_switched_off(db_session: AsyncSession, switch):
    """Gated before parsing, not after resolving the device: a gate placed
    after `resolve_device` would still let WiCAN auto-discovery create rows."""
    device_id = f"ms{uuid.uuid4().hex[:10]}"
    await switch(False)

    await _frame(db_session, device_id, "can/status", {"status": "online"})

    found = (
        await db_session.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id)
        )
    ).scalar_one_or_none()
    assert found is None
