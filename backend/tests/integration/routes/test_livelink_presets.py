"""A preset adds ONE sensor: its own device, and a topic map per chosen reading.

Sensor indexes are never reused and the suite shares one database, so every
index here is read from `next_sensor_index` at the start of the test, never
assumed to be 1.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_parameter import LiveLinkParameter
from app.models.livelink_topic_map import LiveLinkTopicMap
from app.services.livelink_sources.presets import PRESETS
from app.services.livelink_sources.presets.sensors import next_sensor_index

BASE = "/api/livelink/presets"
MOPEKA = PRESETS["mopeka"]


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    """Topic maps, generic devices and preset-shaped parameters, before and after.

    Parameters too: they are what keeps an index held after its device is gone,
    so a leftover one moves every later test's index along.
    """

    async def _wipe():
        await db_session.execute(delete(LiveLinkTopicMap))
        await db_session.execute(
            delete(LiveLinkDevice).where(LiveLinkDevice.kind == "generic_mqtt")
        )
        await db_session.execute(
            delete(LiveLinkParameter).where(
                LiveLinkParameter.param_key.startswith("PROPANE_T")
                | LiveLinkParameter.param_key.startswith("RV_GATEWAY_")
            )
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.fixture
def no_reload():
    with patch("app.routes.livelink_admin.mqtt_subscriber.reload", new=AsyncMock()) as r:
        yield r


def _topics(tag: str, *suffixes: str) -> dict[str, str]:
    """Distinct per test: a topic already mapped anywhere is refused."""
    return {suffix: f"test/{tag}/{suffix.lower()}" for suffix in suffixes}


async def _add(client, headers, label="Front tank", vin=None, topics=None):
    return await client.post(
        f"{BASE}/mopeka/apply",
        json={"label": label, "vin": vin, "topics": topics or _topics(label, "LEVEL_PCT")},
        headers=headers,
    )


async def _parameter(db_session, key):
    db_session.expire_all()
    return (
        await db_session.execute(
            select(LiveLinkParameter).where(LiveLinkParameter.param_key == key)
        )
    ).scalar_one_or_none()


async def _sensor_count(db_session) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(LiveLinkDevice)
            .where(LiveLinkDevice.preset_key == "mopeka")
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_catalogue_describes_one_sensor(client, auth_headers):
    resp = await client.get(BASE, headers=auth_headers)

    assert resp.status_code == 200
    mopeka = {p["name"]: p for p in resp.json()}["mopeka"]
    assert mopeka["title"] == "Mopeka"
    assert [r["suffix"] for r in mopeka["readings"]] == [
        "LEVEL_PCT",
        "TEMP_C",
        "SENSOR_BATT_PCT",
        "QUALITY",
        "DEPTH_MM",
        "REJECTED",
        "AVAILABLE",
    ]
    assert [r["suffix"] for r in mopeka["readings"] if r["required"]] == ["LEVEL_PCT"]
    level = mopeka["readings"][0]
    assert level["default_topic"] == "level_percent"
    assert "level" in level["keywords"]


def test_no_reading_belongs_to_the_gateway():
    """The relay's Wi-Fi signal and uptime are the gateway's, not a tank's."""
    for reading in MOPEKA.readings:
        assert "GATEWAY" not in reading.suffix
        assert "gateway" not in reading.name


def test_the_description_assumes_no_count_layout_or_bottle():
    """Somebody else's setup might be different: one tank or three, another
    gateway, another bottle."""
    for word in ("Two", "ESPHome", "30 lb", "gateway"):
        assert word not in MOPEKA.description


def test_each_reading_says_how_it_is_shown():
    """The tank card and the settings drawer read these: "sensor heard" is Yes
    or No, not 1.0, and quality is a grade out of 3."""
    shown = {r.suffix: (r.format, r.max_value) for r in MOPEKA.readings}

    assert shown["AVAILABLE"] == ("boolean", None)
    assert shown["REJECTED"] == ("count", None)
    assert shown["QUALITY"] == ("of_max", 3)
    assert shown["TEMP_C"] == ("value", None)
    assert shown["DEPTH_MM"] == ("value", None)


def test_the_tank_is_filled_by_the_level():
    assert MOPEKA.fill_suffix == "LEVEL_PCT"
    assert MOPEKA.reading(MOPEKA.fill_suffix) is not None


def test_every_default_topic_is_one_exact_segment():
    """It is appended to the level topic's folder, so it cannot carry a slash
    or a wildcard."""
    for reading in MOPEKA.readings:
        assert not {"/", "+", "#"} & set(reading.default_topic)


# ---------------------------------------------------------------------------
# Adding a sensor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adding_a_sensor_creates_its_device_maps_and_names(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    n = await next_sensor_index(db_session, MOPEKA)

    resp = await _add(
        client,
        auth_headers,
        vin=test_vehicle["vin"],
        topics=_topics("front", "LEVEL_PCT", "TEMP_C"),
    )

    assert resp.status_code == 201
    assert resp.json()["device_id"] == f"mopeka-t{n}"
    assert resp.json()["preset_key"] == "mopeka"
    device = (
        await db_session.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == f"mopeka-t{n}")
        )
    ).scalar_one()
    assert (device.kind, device.label, device.vin) == (
        "generic_mqtt",
        "Front tank",
        test_vehicle["vin"],
    )
    maps = (
        (
            await db_session.execute(
                select(LiveLinkTopicMap)
                .where(LiveLinkTopicMap.device_id == f"mopeka-t{n}")
                .order_by(LiveLinkTopicMap.id)
            )
        )
        .scalars()
        .all()
    )
    # Level first: the readings list shows keys in mapping order.
    assert [(m.topic, m.param_key) for m in maps] == [
        ("test/front/level_pct", f"PROPANE_T{n}_LEVEL_PCT"),
        ("test/front/temp_c", f"PROPANE_T{n}_TEMP_C"),
    ]
    # One at a time: `_parameter` expires everything it did not just load.
    level = await _parameter(db_session, f"PROPANE_T{n}_LEVEL_PCT")
    level_fields = (level.display_name, level.storage_interval_seconds)
    temp = await _parameter(db_session, f"PROPANE_T{n}_TEMP_C")
    temp_fields = (temp.display_name, temp.storage_interval_seconds)
    # Retained messages replay on every resubscribe; without an interval each
    # reconnect writes a row.
    assert level_fields == ("Front tank level", 300)
    assert temp_fields == ("Front tank temperature", 300)


@pytest.mark.asyncio
async def test_a_reading_left_blank_is_not_mapped(client, auth_headers, db_session, no_reload):
    topics = {**_topics("blank", "LEVEL_PCT"), "TEMP_C": "  "}

    resp = await _add(client, auth_headers, topics=topics)

    assert resp.status_code == 201
    maps = (
        (
            await db_session.execute(
                select(LiveLinkTopicMap.param_key).where(
                    LiveLinkTopicMap.device_id == resp.json()["device_id"]
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(maps) == 1 and maps[0].endswith("_LEVEL_PCT")


@pytest.mark.asyncio
async def test_each_sensor_gets_the_next_index(client, auth_headers, db_session, no_reload):
    n = await next_sensor_index(db_session, MOPEKA)

    first = await _add(client, auth_headers, label="Front tank")
    second = await _add(client, auth_headers, label="Rear tank")

    assert first.json()["device_id"] == f"mopeka-t{n}"
    assert second.json()["device_id"] == f"mopeka-t{n + 1}"


@pytest.mark.asyncio
async def test_a_deleted_sensors_index_is_never_reused(client, auth_headers, db_session, no_reload):
    """Reuse would merge a new sensor into the deleted one's history: its
    parameters, and so its charts, outlive the device."""
    n = await next_sensor_index(db_session, MOPEKA)
    await _add(client, auth_headers, label="Front tank")
    await _add(client, auth_headers, label="Rear tank")

    deleted = await client.delete(f"/api/livelink/devices/mopeka-t{n}", headers=auth_headers)
    third = await _add(client, auth_headers, label="Spare tank")

    assert deleted.status_code == 204
    assert third.json()["device_id"] == f"mopeka-t{n + 2}"


@pytest.mark.asyncio
async def test_an_index_held_only_by_a_parameter_is_skipped(
    client, auth_headers, db_session, no_reload
):
    """The device and its maps are gone; the parameter is what remembers."""
    n = await next_sensor_index(db_session, MOPEKA)
    db_session.add(LiveLinkParameter(param_key=f"PROPANE_T{n}_LEVEL_PCT"))
    await db_session.commit()

    resp = await _add(client, auth_headers)

    assert resp.json()["device_id"] == f"mopeka-t{n + 1}"


@pytest.mark.asyncio
async def test_an_index_held_only_by_a_device_id_is_skipped(
    client, auth_headers, db_session, no_reload
):
    """A device made by hand under a sensor's name: creating over it would 500
    on the primary key."""
    n = await next_sensor_index(db_session, MOPEKA)
    db_session.add(LiveLinkDevice(device_id=f"mopeka-t{n}", kind="generic_mqtt"))
    await db_session.commit()

    resp = await _add(client, auth_headers)

    assert resp.json()["device_id"] == f"mopeka-t{n + 1}"


@pytest.mark.asyncio
async def test_a_topic_mapped_by_another_device_is_409_and_creates_nothing(
    client, auth_headers, db_session, no_reload
):
    """One topic, one device: the subscriber ignores a topic two devices map."""
    db_session.add(
        LiveLinkTopicMap(
            device_id="handmade1", topic="test/taken/level", role="telemetry", param_key="HM_LEVEL"
        )
    )
    await db_session.commit()

    resp = await _add(client, auth_headers, topics={"LEVEL_PCT": "test/taken/level"})

    assert resp.status_code == 409
    assert "test/taken/level" in resp.json()["detail"]
    assert "handmade1" in resp.json()["detail"]
    assert await _sensor_count(db_session) == 0
    no_reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "topics"),
    [
        pytest.param("Front tank", {"TEMP_C": "test/v/temp"}, id="no-level"),
        pytest.param("Front tank", {"LEVEL_PCT": "  "}, id="blank-level"),
        pytest.param("Front tank", {"LEVEL_PCT": "test/v/+/level"}, id="wildcard-plus"),
        pytest.param("Front tank", {"LEVEL_PCT": "test/v/#"}, id="wildcard-hash"),
        pytest.param(
            "Front tank", {"LEVEL_PCT": "test/v/level", "BOGUS": "test/v/b"}, id="unknown-reading"
        ),
        pytest.param(
            "Front tank", {"LEVEL_PCT": "test/v/same", "TEMP_C": "test/v/same"}, id="same-topic"
        ),
        pytest.param("Front tank", {"LEVEL_PCT": "t/" + "x" * 254}, id="topic-too-long"),
        pytest.param("   ", {"LEVEL_PCT": "test/v/level"}, id="blank-label"),
        pytest.param("x" * 61, {"LEVEL_PCT": "test/v/level"}, id="label-too-long"),
    ],
)
async def test_an_invalid_sensor_is_422_and_creates_nothing(
    client, auth_headers, db_session, no_reload, label, topics
):
    resp = await _add(client, auth_headers, label=label, topics=topics)

    assert resp.status_code == 422
    assert await _sensor_count(db_session) == 0


@pytest.mark.asyncio
async def test_adding_a_sensor_resubscribes(client, auth_headers, no_reload):
    await _add(client, auth_headers)

    no_reload.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_unknown_preset_is_404(client, auth_headers):
    resp = await client.post(
        f"{BASE}/nope/apply",
        json={"label": "x", "topics": {"LEVEL_PCT": "test/nope/level"}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_admins_are_refused(client, non_admin_headers):
    assert (await _add(client, non_admin_headers)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_a_sensor_says_which_preset_made_it(client, auth_headers, no_reload):
    """The drawers group and title a device by it."""
    device_id = (await _add(client, auth_headers)).json()["device_id"]

    resp = await client.get(f"/api/livelink/devices/{device_id}", headers=auth_headers)

    assert resp.json()["preset_key"] == "mopeka"


# ---------------------------------------------------------------------------
# Renaming a sensor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renaming_a_sensor_renames_its_readings(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    """The Live tab shows two tanks' readings side by side, by these names."""
    device_id = (
        await _add(
            client,
            auth_headers,
            vin=test_vehicle["vin"],
            topics=_topics("rename", "LEVEL_PCT", "TEMP_C"),
        )
    ).json()["device_id"]
    n = MOPEKA.index_of_device(device_id)
    temp = await _parameter(db_session, f"PROPANE_T{n}_TEMP_C")
    temp.display_name = "Bottle temp"  # set by hand: theirs
    await db_session.commit()

    resp = await client.put(
        f"/api/livelink/devices/{device_id}", json={"label": "Rear tank"}, headers=auth_headers
    )

    assert resp.status_code == 200
    assert (await _parameter(db_session, f"PROPANE_T{n}_LEVEL_PCT")).display_name == (
        "Rear tank level"
    )
    assert (await _parameter(db_session, f"PROPANE_T{n}_TEMP_C")).display_name == "Bottle temp"


@pytest.mark.asyncio
async def test_a_change_that_is_not_a_rename_leaves_the_names_alone(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    device_id = (await _add(client, auth_headers)).json()["device_id"]
    n = MOPEKA.index_of_device(device_id)

    resp = await client.put(
        f"/api/livelink/devices/{device_id}", json={"enabled": False}, headers=auth_headers
    )

    assert resp.status_code == 200
    assert (await _parameter(db_session, f"PROPANE_T{n}_LEVEL_PCT")).display_name == (
        "Front tank level"
    )


# ---------------------------------------------------------------------------
# A sensor's keys are its own (E10)
# ---------------------------------------------------------------------------

MAPS = "/api/livelink/topic-maps"


@pytest.mark.asyncio
async def test_another_device_cannot_map_a_sensors_key(client, auth_headers, db_session, no_reload):
    """The key carries the sensor's name ("Front tank level"), so another
    device writing it would file its readings under that name."""
    device_id = (await _add(client, auth_headers)).json()["device_id"]
    n = MOPEKA.index_of_device(device_id)

    resp = await client.post(
        MAPS,
        json={
            "device_id": "handmade1",
            "topic": "test/foreign/level",
            "param_key": f"PROPANE_T{n}_LEVEL_PCT",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 409
    assert device_id in resp.json()["detail"]


@pytest.mark.asyncio
async def test_a_sensor_can_map_another_reading_of_its_own(
    client, auth_headers, db_session, no_reload
):
    """The Topic mappings editor inside the sensor's block."""
    device_id = (await _add(client, auth_headers)).json()["device_id"]
    n = MOPEKA.index_of_device(device_id)

    resp = await client.post(
        MAPS,
        json={
            "device_id": device_id,
            "topic": "test/own/depth",
            "param_key": f"PROPANE_T{n}_DEPTH_MM",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_a_mapping_cannot_be_repointed_at_a_sensors_key(
    client, auth_headers, db_session, no_reload
):
    device_id = (await _add(client, auth_headers)).json()["device_id"]
    n = MOPEKA.index_of_device(device_id)
    own = await client.post(
        MAPS,
        json={"device_id": "handmade1", "topic": "test/hm/level", "param_key": "HM_LEVEL"},
        headers=auth_headers,
    )

    resp = await client.patch(
        f"{MAPS}/{own.json()['id']}",
        json={"param_key": f"PROPANE_T{n}_LEVEL_PCT"},
        headers=auth_headers,
    )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_an_older_mapping_of_a_sensor_key_can_still_be_edited(
    client, auth_headers, db_session, no_reload
):
    """A key mapped before the rule existed (the two-tank preset's `rvgateway`
    on the dev database) is refused only a NEW claim: switching it off must
    still work, or it can never be retired."""
    row = LiveLinkTopicMap(
        device_id="rvgateway",
        topic="test/old/level",
        role="telemetry",
        param_key="PROPANE_T1_LEVEL_PCT",
    )
    db_session.add(row)
    await db_session.commit()

    resp = await client.patch(f"{MAPS}/{row.id}", json={"enabled": False}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_other_keys_stay_shareable(client, auth_headers, db_session, no_reload):
    """Two handmade gateways on two vehicles publishing the same kind of
    reading is a supported setup."""
    for device_id in ("handmade1", "handmade2"):
        resp = await client.post(
            MAPS,
            json={"device_id": device_id, "topic": f"test/{device_id}/t", "param_key": "CABIN_T"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
