"""Per-device readings for the integrations sidecar.

The attribution tests are the reason this endpoint exists rather than reusing
the vehicle status payload.
"""

import itertools
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.utils.datetime_utils import utc_now

_SEQ = itertools.count()

#: Prefix for parameters this file registers, so `_clean` can remove exactly those.
_PREFIX = "DEVREAD_"


def _url(device_id: str) -> str:
    return f"/api/livelink/devices/{device_id}/readings"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    from app.models.livelink_device import LiveLinkDevice
    from app.models.livelink_parameter import LiveLinkParameter
    from app.models.livelink_topic_map import LiveLinkTopicMap
    from app.models.vehicle_telemetry import VehicleTelemetry

    async def _wipe():
        await db_session.execute(delete(LiveLinkTopicMap))
        await db_session.execute(delete(VehicleTelemetry))
        # Parameters this file registers. Without this a leftover row leaks
        # into other files that count parameters by prefix: the preset test
        # counts every PROPANE_* row and expects exactly 14.
        await db_session.execute(
            delete(LiveLinkParameter).where(LiveLinkParameter.param_key.startswith(_PREFIX))
        )
        await db_session.execute(
            delete(LiveLinkDevice).where(LiveLinkDevice.kind == "generic_mqtt")
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


async def _device(db_session, vin=None, **over):
    from app.models.livelink_device import LiveLinkDevice

    device = LiveLinkDevice(
        device_id=f"gw{next(_SEQ):08d}", kind="generic_mqtt", enabled=True, vin=vin, **over
    )
    db_session.add(device)
    await db_session.commit()
    return device


async def _map(db_session, device_id, param_key, role="telemetry", topic=None):
    from app.models.livelink_topic_map import LiveLinkTopicMap

    db_session.add(
        LiveLinkTopicMap(
            device_id=device_id,
            topic=topic or f"t/{device_id}/{param_key or 'status'}/{next(_SEQ)}",
            role=role,
            param_key=param_key,
        )
    )
    await db_session.commit()


async def _reading(db_session, device_id, vin, param_key, value, when):
    from app.models.vehicle_telemetry import VehicleTelemetry

    db_session.add(
        VehicleTelemetry(
            vin=vin, device_id=device_id, param_key=param_key, value=value, timestamp=when
        )
    )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requires_admin(client, db_session):
    device = await _device(db_session)
    assert (await client.get(_url(device.device_id))).status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_device_is_404(client, auth_headers):
    assert (await client.get(_url("nope"), headers=auth_headers)).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lists_the_devices_mapped_parameters(client, auth_headers, db_session, test_vehicle):
    device = await _device(db_session, vin=test_vehicle["vin"])
    key = f"LEVEL_{next(_SEQ)}"
    await _map(db_session, device.device_id, key)

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert [r["param_key"] for r in body["readings"]] == [key]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_status_mappings_are_excluded(client, auth_headers, db_session, test_vehicle):
    """A preset's first row is a status row whose param_key is NULL. Passing it
    through would fail the response model."""
    device = await _device(db_session, vin=test_vehicle["vin"])
    key = f"LEVEL_{next(_SEQ)}"
    await _map(db_session, device.device_id, key)
    await _map(db_session, device.device_id, None, role="status")

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert [r["param_key"] for r in body["readings"]] == [key]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_key_mapped_twice_appears_once(client, auth_headers, db_session, test_vehicle):
    """Uniqueness is (topic, param_key), so one device may map two topics to
    one key."""
    device = await _device(db_session, vin=test_vehicle["vin"])
    key = f"LEVEL_{next(_SEQ)}"
    await _map(db_session, device.device_id, key, topic="a/one")
    await _map(db_session, device.device_id, key, topic="a/two")

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert [r["param_key"] for r in body["readings"]] == [key]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_another_devices_key_does_not_appear(client, auth_headers, db_session, test_vehicle):
    """Catches a lazily VIN-scoped key list."""
    mine = await _device(db_session, vin=test_vehicle["vin"])
    theirs = await _device(db_session, vin=test_vehicle["vin"])
    my_key, their_key = f"MINE_{next(_SEQ)}", f"THEIRS_{next(_SEQ)}"
    await _map(db_session, mine.device_id, my_key)
    await _map(db_session, theirs.device_id, their_key)

    body = (await client.get(_url(mine.device_id), headers=auth_headers)).json()

    keys = [r["param_key"] for r in body["readings"]]
    assert my_key in keys
    assert their_key not in keys


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_shared_key_returns_this_devices_value(
    client, auth_headers, db_session, test_vehicle
):
    """THE attribution test. Two devices on one VIN mapping the same key is
    permitted: livelink_topic_maps is UNIQUE(topic, param_key), not
    (device_id, param_key). vehicle_telemetry_latest is UNIQUE(vin, param_key)
    with no device_id, so reading values from it returns whoever wrote last.

    The previous test passes with that bug fully intact. This one does not.
    """
    vin = test_vehicle["vin"]
    mine = await _device(db_session, vin=vin)
    theirs = await _device(db_session, vin=vin)
    key = f"SHARED_{next(_SEQ)}"
    now = utc_now()
    await _map(db_session, mine.device_id, key, topic="a/mine")
    await _map(db_session, theirs.device_id, key, topic="a/theirs")
    await _reading(db_session, mine.device_id, vin, key, 11.0, now - timedelta(minutes=5))
    # The other device writes LAST, so it owns the _latest row.
    await _reading(db_session, theirs.device_id, vin, key, 99.0, now)

    body = (await client.get(_url(mine.device_id), headers=auth_headers)).json()

    assert body["readings"][0]["value"] == 11.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_same_instant_reading_from_another_device_is_not_attributed(
    client, auth_headers, db_session, test_vehicle
):
    """The OUTER device filter's test. The one above cannot see it.

    The newest-per-key subquery is device-scoped, so it yields THIS device's
    newest timestamp. The outer query then joins every row at that
    (param_key, timestamp), and only its own `device_id` filter keeps another
    device's row out. That only matters when the two share an instant, which
    the dedup index permits: it is (device_id, param_key, timestamp), so two
    devices may hold the same timestamp. SD-card backfill carries
    second-resolution device timestamps, so this is not hypothetical.

    Without the outer filter both rows match and whichever arrives last is
    reported. Theirs is inserted second so the mutant returns theirs.
    """
    vin = test_vehicle["vin"]
    mine = await _device(db_session, vin=vin)
    theirs = await _device(db_session, vin=vin)
    key = f"SAME_INSTANT_{next(_SEQ)}"
    instant = utc_now().replace(microsecond=0)
    await _map(db_session, mine.device_id, key, topic="b/mine")
    await _map(db_session, theirs.device_id, key, topic="b/theirs")
    await _reading(db_session, mine.device_id, vin, key, 11.0, instant)
    await _reading(db_session, theirs.device_id, vin, key, 99.0, instant)

    body = (await client.get(_url(mine.device_id), headers=auth_headers)).json()

    assert body["readings"][0]["value"] == 11.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_newest_reading_wins(client, auth_headers, db_session, test_vehicle):
    vin = test_vehicle["vin"]
    device = await _device(db_session, vin=vin)
    key = f"LEVEL_{next(_SEQ)}"
    now = utc_now()
    await _map(db_session, device.device_id, key)
    await _reading(db_session, device.device_id, vin, key, 1.0, now - timedelta(hours=2))
    await _reading(db_session, device.device_id, vin, key, 2.0, now)

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert body["readings"][0]["value"] == 2.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_mapped_but_never_reported_key_returns_a_null_value(
    client, auth_headers, db_session, test_vehicle
):
    """The ordinary state between applying a preset and the first publish."""
    device = await _device(db_session, vin=test_vehicle["vin"])
    key = f"QUIET_{next(_SEQ)}"
    await _map(db_session, device.device_id, key)

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert body["readings"][0]["value"] is None
    assert body["readings"][0]["timestamp"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_unlinked_device_returns_its_mappings_without_values(
    client, auth_headers, db_session
):
    """No vin means nothing to join against. The mappings and their switches
    must still render, with the UI saying the device is not linked."""
    device = await _device(db_session, vin=None)
    key = f"ORPHAN_{next(_SEQ)}"
    await _map(db_session, device.device_id, key)

    response = await client.get(_url(device.device_id), headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["vin"] is None
    assert body["readings"][0]["param_key"] == key
    assert body["readings"][0]["value"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_show_on_dashboard_is_reported(client, auth_headers, db_session, test_vehicle):
    """The switch's current position. Task 4 guarantees the parameter row
    exists for every mapped telemetry key."""
    from app.services.telemetry_service import TelemetryService

    device = await _device(db_session, vin=test_vehicle["vin"])
    key = f"{_PREFIX}LEVEL_PCT_{next(_SEQ)}"
    await _map(db_session, device.device_id, key)
    param = await TelemetryService(db_session).get_or_create_parameter(
        key, unit="%", param_class="propane"
    )
    param.show_on_dashboard = True
    param.archive_only = False
    await db_session.commit()

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert body["readings"][0]["show_on_dashboard"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readings_come_in_the_order_they_were_mapped(
    client, auth_headers, db_session, test_vehicle
):
    """A preset maps a tank's level first; the drawer should list it first.

    Alphabetical put "Tank 1 sensor heard" (AVAILABLE) ahead of the level,
    the one reading the integration exists to show.
    """
    device = await _device(db_session, vin=test_vehicle["vin"])
    n = next(_SEQ)
    mapped = [f"ZZ_LEVEL_{n}", f"AA_AVAILABLE_{n}", f"MM_DEPTH_{n}"]
    for key in mapped:
        await _map(db_session, device.device_id, key)

    body = (await client.get(_url(device.device_id), headers=auth_headers)).json()

    assert [r["param_key"] for r in body["readings"]] == mapped
