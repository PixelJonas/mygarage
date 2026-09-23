"""Every path that creates a mapping must register its parameter.

Without this the integrations sidecar shows a switch whose PUT 404s, because
parameters are otherwise registered only at first ingest and a freshly mapped
topic has not ingested anything yet.
"""

import itertools
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

BASE = "/api/livelink/topic-maps"
_SEQ = itertools.count()


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    from app.models.livelink_topic_map import LiveLinkTopicMap

    async def _wipe():
        await db_session.execute(delete(LiveLinkTopicMap))
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.fixture
def no_reload():
    with patch("app.routes.livelink_admin.mqtt_subscriber.reload", new=AsyncMock()) as r:
        yield r


async def _parameter(db_session, param_key):
    from app.models.livelink_parameter import LiveLinkParameter

    result = await db_session.execute(
        select(LiveLinkParameter).where(LiveLinkParameter.param_key == param_key)
    )
    return result.scalar_one_or_none()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_creating_a_mapping_registers_its_parameter(
    client, auth_headers, db_session, no_reload
):
    key = f"AUX_VOLTS_{next(_SEQ)}"
    response = await client.post(
        BASE,
        json={
            "device_id": "gw01",
            "topic": f"sensors/{key.lower()}",
            "param_key": key,
            "unit": "V",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert await _parameter(db_session, key) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patching_the_param_key_registers_the_new_parameter(
    client, auth_headers, db_session, no_reload
):
    """A PATCH can point a mapping at a key nothing has ever registered."""
    old = f"OLD_KEY_{next(_SEQ)}"
    new = f"NEW_KEY_{next(_SEQ)}"
    created = await client.post(
        BASE,
        json={"device_id": "gw01", "topic": f"sensors/{old.lower()}", "param_key": old},
        headers=auth_headers,
    )

    response = await client.patch(
        f"{BASE}/{created.json()['id']}", json={"param_key": new}, headers=auth_headers
    )

    assert response.status_code == 200
    assert await _parameter(db_session, new) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_status_mapping_registers_no_parameter(client, auth_headers, db_session, no_reload):
    """A role='status' row carries no param_key; it must not mint a parameter
    named after nothing."""
    from app.models.livelink_parameter import LiveLinkParameter

    before = len((await db_session.execute(select(LiveLinkParameter))).scalars().all())

    response = await client.post(
        BASE,
        json={"device_id": "gw01", "topic": "sensors/status", "role": "status"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    after = len((await db_session.execute(select(LiveLinkParameter))).scalars().all())
    assert after == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registration_does_not_overwrite_a_hand_tuned_parameter(
    client, auth_headers, db_session, no_reload
):
    """get_or_create, never create-or-clobber: an operator's display name and
    dashboard choice must survive re-mapping the topic."""
    from app.models.livelink_parameter import LiveLinkParameter

    key = f"TUNED_{next(_SEQ)}"
    db_session.add(
        LiveLinkParameter(
            param_key=key,
            display_name="Operator's Name",
            show_on_dashboard=False,
            archive_only=True,
        )
    )
    await db_session.commit()

    await client.post(
        BASE,
        json={"device_id": "gw01", "topic": f"sensors/{key.lower()}", "param_key": key},
        headers=auth_headers,
    )

    param = await _parameter(db_session, key)
    assert param.display_name == "Operator's Name"
    assert param.show_on_dashboard is False
