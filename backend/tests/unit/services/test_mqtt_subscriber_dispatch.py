"""Subscriber dispatch and resubscribe. The WiCAN behavior gate is the existing suite."""

import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.livelink_sources.base import BaseSourceModule, Capability, IngestBatch
from app.services.mqtt_subscriber import MQTTSubscriber


class _Spy(BaseSourceModule):
    kind = "spy"
    capabilities = frozenset({Capability.TELEMETRY})

    def __init__(self):
        self.seen = []

    async def subscriptions(self, db):
        return ["spy/one"]

    async def parse(self, env):
        self.seen.append(env.topic)
        return IngestBatch(device_key="x")


@contextlib.contextmanager
def _session_factory(db_session):
    """Bind `_process_message`'s own session factory to the test session.

    `_process_message` opens `AsyncSessionLocal()` itself, which resolves to
    the configured database rather than the test one (`unable to open database
    file`). The old `_handle_*` handlers took a session argument and so never
    hit this; dispatch owns the transaction now, so the factory is what the
    test has to replace.
    """

    @contextlib.asynccontextmanager
    async def _factory():
        yield db_session

    with (
        patch("app.services.mqtt_subscriber.AsyncSessionLocal", _factory),
        patch("app.services.mqtt_subscriber.load_household_zone", new=AsyncMock()),
    ):
        yield


@pytest.mark.asyncio
async def test_a_message_is_dispatched_to_its_owning_module(db_session):
    sub = MQTTSubscriber()
    spy = _Spy()
    sub._subscribed = {"spy/one": spy}
    with (
        _session_factory(db_session),
        patch("app.services.mqtt_subscriber.ingest", new=AsyncMock()) as ing,
    ):
        await sub._process_message("spy/one", b"42")
        ing.assert_awaited_once()
        assert ing.await_args.args[0] is spy


@pytest.mark.asyncio
async def test_an_unowned_topic_is_ignored_without_raising(db_session):
    sub = MQTTSubscriber()
    sub._subscribed = {}
    with (
        _session_factory(db_session),
        patch("app.services.mqtt_subscriber.ingest", new=AsyncMock()) as ing,
    ):
        await sub._process_message("nobody/cares", b"42")
        ing.assert_not_called()


@pytest.mark.asyncio
async def test_reload_subscribes_new_topics_and_unsubscribes_dropped_ones():
    sub = MQTTSubscriber()
    client = AsyncMock()
    sub._client = client
    sub._subscribed = {"old/topic": _Spy()}
    sub._confirmed = {"old/topic"}
    with patch.object(
        MQTTSubscriber, "_desired_subscriptions", new=AsyncMock(return_value={"new/topic": _Spy()})
    ):
        await sub.reload()
    client.subscribe.assert_awaited_once_with("new/topic")
    client.unsubscribe.assert_awaited_once_with("old/topic")
    assert set(sub._subscribed) == {"new/topic"}


@pytest.mark.asyncio
async def test_the_new_map_is_installed_before_subscribing(db_session):
    """R1-H3: retained messages arrive the instant SUBSCRIBE lands."""
    sub = MQTTSubscriber()
    spy = _Spy()
    seen_during_subscribe: list[bool] = []

    client = AsyncMock()

    async def _subscribe(topic):
        seen_during_subscribe.append("new/topic" in sub._subscribed)

    client.subscribe.side_effect = _subscribe
    sub._client = client
    sub._subscribed = {}
    with patch.object(
        MQTTSubscriber, "_desired_subscriptions", new=AsyncMock(return_value={"new/topic": spy})
    ):
        await sub.reload()
    assert seen_during_subscribe == [True], "map must be live before SUBSCRIBE"


@pytest.mark.asyncio
async def test_reload_is_a_no_op_when_disconnected():
    sub = MQTTSubscriber()
    sub._client = None
    await sub.reload()  # must not raise


@pytest.mark.asyncio
async def test_a_failed_subscribe_is_retried_on_the_next_reload():
    """R1-H3 round 2: a failed SUBSCRIBE must not look permanently done.

    The dispatch map is the union, so diffing against it would mark a failed
    topic as already subscribed. The mapping would then look healthy in the UI
    and receive nothing, forever.
    """
    sub = MQTTSubscriber()
    spy = _Spy()
    client = AsyncMock()
    client.subscribe.side_effect = [RuntimeError("broker said no"), None]
    sub._client = client
    with patch.object(
        MQTTSubscriber, "_desired_subscriptions", new=AsyncMock(return_value={"flaky/t": spy})
    ):
        await sub.reload()
        assert "flaky/t" not in sub._confirmed
        await sub.reload()
    assert "flaky/t" in sub._confirmed
    assert client.subscribe.await_count == 2


@pytest.mark.asyncio
async def test_a_reconnect_resubscribes_everything():
    """A fresh client holds no subscriptions, so _confirmed must be cleared.

    Deliberately exercises `_reset_subscription_state()` and then `reload()`,
    rather than asserting an assignment the test made itself. Delete the body of
    `_reset_subscription_state` and this fails: reload would diff against stale
    confirmations and re-subscribe nothing on a reconnected client.
    """
    sub = MQTTSubscriber()
    spy = _Spy()
    client = AsyncMock()
    sub._client = client
    sub._confirmed = {"spy/one"}  # what the PREVIOUS connection had ACKed
    sub._subscribed = {"spy/one": spy}

    sub._reset_subscription_state()  # what _run does on connect

    with patch.object(
        MQTTSubscriber, "_desired_subscriptions", new=AsyncMock(return_value={"spy/one": spy})
    ):
        await sub.reload()

    client.subscribe.assert_awaited_once_with("spy/one")
    assert sub._confirmed == {"spy/one"}


@pytest.mark.asyncio
async def test_reload_leaves_unchanged_topics_alone():
    sub = MQTTSubscriber()
    client = AsyncMock()
    sub._client = client
    keep = _Spy()
    sub._subscribed = {"keep/me": keep}
    sub._confirmed = {"keep/me"}  # already ACKed by the broker
    with patch.object(
        MQTTSubscriber, "_desired_subscriptions", new=AsyncMock(return_value={"keep/me": keep})
    ):
        await sub.reload()
    client.subscribe.assert_not_called()
    client.unsubscribe.assert_not_called()
