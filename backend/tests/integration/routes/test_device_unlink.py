"""PUT /devices/{id} can unlink, and stores the VIN it checked.

The UI's "Unlinked" option could never clear a VIN: `null` means "leave it"
and `""` failed `min_length=17`. And the ownership check uppercased the VIN
while the store did not, so a lowercase VIN was a foreign-key 500.
"""

import itertools

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

_SEQ = itertools.count()
_PREFIX = "UNLINK_"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    from app.models.livelink_device import LiveLinkDevice

    async def _wipe():
        await db_session.execute(
            delete(LiveLinkDevice).where(LiveLinkDevice.device_id.like(f"{_PREFIX}%"))
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


async def _device(db_session, vin):
    from app.models.livelink_device import LiveLinkDevice

    device = LiveLinkDevice(
        device_id=f"{_PREFIX}{next(_SEQ):06d}",
        kind="generic_mqtt",
        vin=vin,
        enabled=True,
        device_status="unknown",
    )
    db_session.add(device)
    await db_session.commit()
    return device.device_id


async def _stored_vin(db_session, device_id):
    from app.models.livelink_device import LiveLinkDevice

    db_session.expire_all()
    return (
        await db_session.execute(
            select(LiveLinkDevice.vin).where(LiveLinkDevice.device_id == device_id)
        )
    ).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_empty_vin_unlinks(client, auth_headers, db_session, test_vehicle):
    device_id = await _device(db_session, test_vehicle["vin"])

    response = await client.put(
        f"/api/livelink/devices/{device_id}", json={"vin": ""}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["vin"] is None
    assert await _stored_vin(db_session, device_id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_null_and_omitted_leave_the_link_alone(
    client, auth_headers, db_session, test_vehicle
):
    """Pins current behaviour that must survive: `null` is "not supplied"."""
    device_id = await _device(db_session, test_vehicle["vin"])

    for body in ({"vin": None}, {"label": "renamed"}):
        response = await client.put(
            f"/api/livelink/devices/{device_id}", json=body, headers=auth_headers
        )
        assert response.status_code == 200, body
        assert await _stored_vin(db_session, device_id) == test_vehicle["vin"], body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_lowercase_vin_is_stored_as_checked(client, auth_headers, db_session, test_vehicle):
    device_id = await _device(db_session, None)

    response = await client.put(
        f"/api/livelink/devices/{device_id}",
        json={"vin": test_vehicle["vin"].lower()},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert await _stored_vin(db_session, device_id) == test_vehicle["vin"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_partial_vin_is_rejected(client, auth_headers, db_session, test_vehicle):
    device_id = await _device(db_session, test_vehicle["vin"])

    response = await client.put(
        f"/api/livelink/devices/{device_id}", json={"vin": "1HGBH41"}, headers=auth_headers
    )

    assert response.status_code == 422
    assert await _stored_vin(db_session, device_id) == test_vehicle["vin"]
