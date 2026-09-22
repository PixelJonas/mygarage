"""A hand-supplied device id must be safe to put in a URL path segment.

WiCAN ids arrive from an MQTT topic segment and Torque ids are generated, so
neither can contain a separator. The three request bodies below are the only
places an operator TYPES one, and every per-device admin route puts it in a
path: `/api/livelink/devices/{device_id}/readings` and its siblings. An id of
`rv/gw` routes to a different path entirely, `gw#1` is truncated at the
fragment, and an empty id produces `/devices//readings`.
"""

import pytest
from pydantic import ValidationError

from app.schemas.livelink import LiveLinkDeviceManualCreate
from app.schemas.livelink_topic_map import PresetApplyRequest, TopicMapCreate

VIN = "1HGBH41JXMN109186"


def _manual(device_id: str) -> LiveLinkDeviceManualCreate:
    return LiveLinkDeviceManualCreate(device_id=device_id, kind="generic_mqtt")


def _topic_map(device_id: str) -> TopicMapCreate:
    return TopicMapCreate(device_id=device_id, topic="a/b", param_key="LEVEL")


def _preset(device_id: str) -> PresetApplyRequest:
    return PresetApplyRequest(device_id=device_id, vin=VIN)


BUILDERS = [_manual, _topic_map, _preset]


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize(
    "device_id",
    ["gw01", "rvgw", "someone_else", "rv-gateway", "rv.gateway", "A1B2C3D4E5F6"],
)
def test_ordinary_ids_are_accepted(build, device_id):
    """The control: every id an existing test or preset uses still passes."""
    assert build(device_id).device_id == device_id


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize(
    "device_id",
    [
        "",  # /devices//readings
        "rv/gw",  # a different route
        "gw#1",  # truncated at the fragment
        "gw?x=1",  # becomes a query string
        "gw 1",  # needs encoding every time it is written
        "..",  # path traversal once normalised
        ".hidden",  # must start with a letter or digit
        "-gw",
        "gw%2F",  # a pre-encoded separator
    ],
)
def test_ids_that_break_a_url_path_are_rejected(build, device_id):
    with pytest.raises(ValidationError):
        build(device_id)


def test_a_stored_row_with_a_legacy_id_still_serialises():
    """The rule governs what an operator may TYPE, never what may be READ.

    `TopicMapResponse` shares a base with `TopicMapCreate`. If the pattern
    lived on the base, FastAPI's response validation would run it on every
    stored row, and one row written before the rule existed would turn
    `GET /topic-maps` into a 500 for the whole list.
    """
    from types import SimpleNamespace

    from app.schemas.livelink_topic_map import TopicMapResponse

    legacy = SimpleNamespace(
        id=1,
        device_id="rv/gw",
        topic="a/b",
        role="telemetry",
        param_key="LEVEL",
        value_path=None,
        unit=None,
        param_class=None,
        scale=1,
        value_offset=0,
        enabled=True,
    )
    assert TopicMapResponse.model_validate(legacy).device_id == "rv/gw"
