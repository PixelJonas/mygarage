"""The topic-map model: round-trip, uniqueness, and cleanup on device delete.

Deliberately NOT in tests/migrations/: that package's `engine_for_migration`
fixture drops the PostgreSQL `public` schema, which destroys the tables these
ORM tests rely on.

Every test scopes its rows under a uuid and filters every query by it, because
the suite shares one database with no per-test rollback.
"""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.livelink_topic_map import LiveLinkTopicMap


@pytest.fixture
def scope() -> str:
    """A topic prefix and device id nothing else uses."""
    return uuid.uuid4().hex[:10]


async def _rows(db, scope: str):
    return (
        await db.execute(
            select(LiveLinkTopicMap).where(LiveLinkTopicMap.device_id == scope)
        )
    ).scalars().all()


def test_offset_column_avoids_the_reserved_word():
    cols = set(LiveLinkTopicMap.__table__.c.keys())
    assert "value_offset" in cols, "OFFSET is reserved in SQL"
    assert "offset" not in cols


def test_defaults_are_the_identity_transform():
    col = LiveLinkTopicMap.__table__.c
    assert col.scale.default.arg == 1
    assert col.value_offset.default.arg == 0


@pytest.mark.asyncio
async def test_a_row_round_trips(db_session, scope):
    db_session.add(
        LiveLinkTopicMap(
            device_id=scope,
            topic=f"{scope}/rv/propane/tank1/level_percent",
            param_key="PROPANE_T1_LEVEL_PCT",
            unit="%",
            param_class="propane",
        )
    )
    await db_session.commit()
    rows = await _rows(db_session, scope)
    assert len(rows) == 1
    assert rows[0].role == "telemetry"
    assert rows[0].enabled is True
    assert float(rows[0].scale) == 1.0
    assert rows[0].value_path is None
    await db_session.execute(
        delete(LiveLinkTopicMap).where(LiveLinkTopicMap.device_id == scope)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_the_same_topic_cannot_map_to_the_same_param_twice(db_session, scope):
    for _ in range(2):
        db_session.add(
            LiveLinkTopicMap(device_id=scope, topic=f"{scope}/t", param_key="P")
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_one_topic_may_feed_two_params(db_session, scope):
    """A JSON payload legitimately carries several values on one topic."""
    for key in ("A", "B"):
        db_session.add(
            LiveLinkTopicMap(
                device_id=scope,
                topic=f"{scope}/t",
                param_key=key,
                value_path=key.lower(),
            )
        )
    await db_session.commit()
    assert len(await _rows(db_session, scope)) == 2
    await db_session.execute(
        delete(LiveLinkTopicMap).where(LiveLinkTopicMap.device_id == scope)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_deleting_a_device_removes_its_topic_maps(db_session, scope):
    """Config, unlike telemetry, must not outlive its device."""
    from app.models.livelink_device import LiveLinkDevice
    from app.services.livelink_service import LiveLinkService

    db_session.add(LiveLinkDevice(device_id=scope, kind="generic_mqtt"))
    db_session.add(
        LiveLinkTopicMap(device_id=scope, topic=f"{scope}/x", param_key="P")
    )
    await db_session.commit()

    assert len(await _rows(db_session, scope)) == 1
    await LiveLinkService(db_session).delete_device(scope)
    assert await _rows(db_session, scope) == []
