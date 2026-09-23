"""The two routes that CREATE a device with a vehicle must treat the VIN the way
the route that LINKS one does.

`PUT /devices/{id}` uppercases the VIN and resolves it through
`get_vehicle_for_owner_or_403`. Manual create and preset apply passed the body's
VIN straight into `livelink_devices.vin`, a foreign key to `vehicles.vin`, so:

- an unknown VIN was an IntegrityError at commit, i.e. a 500, not a 404;
- a lowercase VIN never matches (VINs are stored uppercase), so the same;
- neither left anything behind to explain it.
"""

import itertools
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

_SEQ = itertools.count()
UNKNOWN_VIN = "1FTFW1ET5DFA00000"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    from app.models.livelink_device import LiveLinkDevice
    from app.models.livelink_topic_map import LiveLinkTopicMap

    async def _wipe():
        await db_session.execute(delete(LiveLinkTopicMap))
        await db_session.execute(
            delete(LiveLinkDevice).where(LiveLinkDevice.kind == "generic_mqtt")
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.fixture
def no_reload():
    with patch("app.routes.livelink_admin.mqtt_subscriber.reload", new=AsyncMock()) as r:
        yield r


async def _device(db_session, device_id):
    from app.models.livelink_device import LiveLinkDevice

    return (
        await db_session.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id)
        )
    ).scalar_one_or_none()


def _id() -> str:
    return f"vin{next(_SEQ):06d}"


async def _sensors(db_session) -> list:
    from app.models.livelink_device import LiveLinkDevice

    return list(
        (
            await db_session.execute(
                select(LiveLinkDevice).where(LiveLinkDevice.preset_key == "mopeka")
            )
        )
        .scalars()
        .all()
    )


def _sensor(vin: str) -> dict:
    """A preset picks its own device id, so the body names none."""
    return {"label": "Tank", "vin": vin, "topics": {"LEVEL_PCT": f"test/vin/{_id()}"}}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preset_with_an_unknown_vin_is_404_and_creates_nothing(
    client, auth_headers, db_session, no_reload
):
    response = await client.post(
        "/api/livelink/presets/mopeka/apply", json=_sensor(UNKNOWN_VIN), headers=auth_headers
    )

    assert response.status_code == 404
    assert await _sensors(db_session) == []
    no_reload.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preset_stores_a_lowercase_vin_uppercased(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    response = await client.post(
        "/api/livelink/presets/mopeka/apply",
        json=_sensor(test_vehicle["vin"].lower()),
        headers=auth_headers,
    )

    assert response.status_code == 201
    device_id = response.json()["device_id"]
    assert (await _device(db_session, device_id)).vin == test_vehicle["vin"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manual_create_with_an_unknown_vin_is_404_and_creates_nothing(
    client, auth_headers, db_session
):
    device_id = _id()
    response = await client.post(
        "/api/livelink/devices",
        json={"device_id": device_id, "kind": "generic_mqtt", "vin": UNKNOWN_VIN},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert await _device(db_session, device_id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manual_create_stores_a_lowercase_vin_uppercased(
    client, auth_headers, db_session, test_vehicle
):
    device_id = _id()
    response = await client.post(
        "/api/livelink/devices",
        json={"device_id": device_id, "kind": "generic_mqtt", "vin": test_vehicle["vin"].lower()},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert (await _device(db_session, device_id)).vin == test_vehicle["vin"]
