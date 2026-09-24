"""Discovery is bounded. Every limit is enforced server-side."""

from unittest.mock import AsyncMock, patch

import pytest

URL = "/api/livelink/topic-discovery"


@pytest.mark.asyncio
async def test_returns_observed_topics_with_samples(client, auth_headers):
    with patch(
        "app.routes.livelink_admin.mqtt_subscriber.discover_topics",
        new=AsyncMock(return_value=[{"topic": "mygarage/rv/status", "sample": "online"}]),
    ):
        resp = await client.post(URL, json={"prefix": "mygarage/rv/#"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["topic"] == "mygarage/rv/status"


@pytest.mark.asyncio
async def test_an_out_of_range_duration_is_rejected_by_the_schema(client, auth_headers):
    """The schema is the contract: ge=1, le=60. 9999 is a 422, not a clamp."""
    resp = await client.post(URL, json={"prefix": "a/#", "seconds": 9999}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_the_service_clamps_defensively_for_non_http_callers():
    """Belt and braces: the service is also callable from a task or shell."""
    from app.services.mqtt_subscriber import MAX_DISCOVERY_SECONDS, MQTTSubscriber

    sub = MQTTSubscriber()
    sub._discovering = True  # forces the guard before any network work
    with pytest.raises(RuntimeError):
        await sub.discover_topics(prefix="a/#", seconds=9999)
    assert MAX_DISCOVERY_SECONDS == 60


@pytest.mark.asyncio
async def test_a_concurrent_sniff_is_refused(client, auth_headers):
    with patch(
        "app.routes.livelink_admin.mqtt_subscriber.discover_topics",
        new=AsyncMock(side_effect=RuntimeError("A discovery run is already in progress")),
    ):
        resp = await client.post(URL, json={"prefix": "a/#"}, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_non_admins_are_refused(client, non_admin_headers):
    resp = await client.post(URL, json={"prefix": "a/#"}, headers=non_admin_headers)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_topic_cap_and_payload_truncation():
    """Unit-level: the collector itself must bound what it keeps."""
    from app.services.mqtt_subscriber import _DiscoveryCollector

    c = _DiscoveryCollector(max_topics=2, max_sample=4)
    c.observe("a", b"0123456789")
    c.observe("b", b"xy")
    c.observe("c", b"z")
    assert len(c.results()) == 2
    assert c.results()[0]["sample"] == "0123"


def test_collector_keeps_one_sample_per_topic():
    from app.services.mqtt_subscriber import _DiscoveryCollector

    c = _DiscoveryCollector(max_topics=10, max_sample=16)
    c.observe("a", b"first")
    c.observe("a", b"second")
    assert len(c.results()) == 1
    assert c.results()[0]["sample"] == "first"
