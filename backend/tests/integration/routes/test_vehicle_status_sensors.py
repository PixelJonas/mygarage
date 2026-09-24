"""The Live tab draws one card per preset sensor, from the status response.

Which readings belong to which tank comes from the server, from each sensor's
own topic maps, rather than from the frontend guessing at key names.
"""

import itertools
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_topic_map import LiveLinkTopicMap
from app.models.vehicle import Vehicle
from app.utils.datetime_utils import utc_now

#: Sensor indexes far from anything the preset tests create, one block per test.
_BLOCKS = itertools.count(7000, 10)


@pytest_asyncio.fixture
async def made(db_session):
    """Device ids this test created; their devices and maps go afterwards."""
    ids: list[str] = []
    yield ids
    if ids:
        await db_session.execute(
            delete(LiveLinkTopicMap).where(LiveLinkTopicMap.device_id.in_(ids))
        )
        await db_session.execute(delete(LiveLinkDevice).where(LiveLinkDevice.device_id.in_(ids)))
        await db_session.commit()


async def _vehicle(db_session, test_user) -> str:
    vin = f"SN{uuid.uuid4().hex[:15].upper()}"
    db_session.add(Vehicle(vin=vin, user_id=test_user["id"], nickname="RV", vehicle_type="RV"))
    await db_session.commit()
    return vin


async def _device(db_session, made, vin, device_id, *, keys=(), **fields) -> None:
    fields.setdefault("kind", "generic_mqtt")
    fields.setdefault("enabled", True)
    db_session.add(LiveLinkDevice(device_id=device_id, vin=vin, **fields))
    for key in keys:
        db_session.add(
            LiveLinkTopicMap(
                device_id=device_id, topic=f"t/{device_id}/{key}", role="telemetry", param_key=key
            )
        )
    made.append(device_id)
    await db_session.commit()


async def _sensors(client, auth_headers, vin) -> list[dict]:
    response = await client.get(f"/api/vehicles/{vin}/livelink/status", headers=auth_headers)
    assert response.status_code == 200
    return response.json()["sensors"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_each_tank_is_described_in_the_order_it_was_added(
    client, auth_headers, db_session, test_user, made
):
    vin = await _vehicle(db_session, test_user)
    n = next(_BLOCKS)
    front, rear = f"mopeka-t{n + 1}", f"mopeka-t{n + 2}"
    # The rear tank first, and its readings mapped out of order: neither the
    # insert order nor the mapping order may leak into the card.
    await _device(
        db_session,
        made,
        vin,
        rear,
        label="Rear tank",
        preset_key="mopeka",
        keys=[f"PROPANE_T{n + 2}_AVAILABLE", f"PROPANE_T{n + 2}_LEVEL_PCT"],
    )
    await _device(
        db_session,
        made,
        vin,
        front,
        label="Front tank",
        preset_key="mopeka",
        keys=[
            f"PROPANE_T{n + 1}_AVAILABLE",
            f"PROPANE_T{n + 1}_QUALITY",
            f"PROPANE_T{n + 1}_LEVEL_PCT",
            f"PROPANE_T{n + 1}_TEMP_C",
        ],
    )

    sensors = await _sensors(client, auth_headers, vin)

    assert [s["device_id"] for s in sensors] == [front, rear]
    first = sensors[0]
    assert (first["label"], first["preset_key"]) == ("Front tank", "mopeka")
    assert first["fill_key"] == f"PROPANE_T{n + 1}_LEVEL_PCT"
    assert [(r["param_key"], r["format"], r["max_value"]) for r in first["readings"]] == [
        (f"PROPANE_T{n + 1}_LEVEL_PCT", "value", None),
        (f"PROPANE_T{n + 1}_TEMP_C", "value", None),
        (f"PROPANE_T{n + 1}_QUALITY", "of_max", 3),
        (f"PROPANE_T{n + 1}_AVAILABLE", "boolean", None),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_key_mapped_by_hand_on_a_tank_comes_last_as_a_plain_value(
    client, auth_headers, db_session, test_user, made
):
    vin = await _vehicle(db_session, test_user)
    n = next(_BLOCKS)
    await _device(
        db_session,
        made,
        vin,
        f"mopeka-t{n}",
        label="Tank",
        preset_key="mopeka",
        keys=[f"PROPANE_T{n}_EXTRA", f"PROPANE_T{n}_LEVEL_PCT"],
    )

    readings = (await _sensors(client, auth_headers, vin))[0]["readings"]

    assert [(r["param_key"], r["format"]) for r in readings] == [
        (f"PROPANE_T{n}_LEVEL_PCT", "value"),
        (f"PROPANE_T{n}_EXTRA", "value"),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_tank_whose_level_is_not_mapped_has_nothing_to_fill(
    client, auth_headers, db_session, test_user, made
):
    vin = await _vehicle(db_session, test_user)
    n = next(_BLOCKS)
    await _device(
        db_session,
        made,
        vin,
        f"mopeka-t{n}",
        preset_key="mopeka",
        keys=[f"PROPANE_T{n}_TEMP_C"],
    )

    assert (await _sensors(client, auth_headers, vin))[0]["fill_key"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_each_tank_says_whether_it_is_reporting(
    client, auth_headers, db_session, test_user, made
):
    vin = await _vehicle(db_session, test_user)
    n = next(_BLOCKS)
    await _device(
        db_session,
        made,
        vin,
        f"mopeka-t{n + 1}",
        preset_key="mopeka",
        device_status="unknown",
        last_seen=utc_now() - timedelta(minutes=1),
    )
    await _device(
        db_session,
        made,
        vin,
        f"mopeka-t{n + 2}",
        preset_key="mopeka",
        device_status="unknown",
        last_seen=utc_now() - timedelta(hours=10),
    )

    sensors = await _sensors(client, auth_headers, vin)

    assert [s["online"] for s in sensors] == [True, False]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_only_preset_sensors_get_a_card(client, auth_headers, db_session, test_user, made):
    """A WiCAN, a handmade gateway and a device whose preset is gone keep
    their ordinary gauges."""
    vin = await _vehicle(db_session, test_user)
    tag = uuid.uuid4().hex[:8]
    await _device(db_session, made, vin, f"wc{tag}", kind="wican", keys=["0D-VEHICLESPEED"])
    await _device(db_session, made, vin, f"hm{tag}", keys=[f"HM{tag}_LEVEL"])
    await _device(
        db_session, made, vin, f"old{tag}", preset_key="mopeka_two_tank", keys=[f"OLD{tag}_LEVEL"]
    )

    assert await _sensors(client, auth_headers, vin) == []
