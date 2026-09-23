"""A rejected POI search logs no API key.

TomTom and Google Places take the key as a query parameter, so an
HTTPStatusError's text, which holds the request URL, holds the key too.
"""

import logging
from unittest.mock import patch

import httpx
import pytest

from app.services.poi import google_places, tomtom
from app.services.poi.base import POICategory
from app.services.poi.google_places import GooglePlacesProvider
from app.services.poi.tomtom import TomTomProvider

KEY = "SECRET-poi-key"
PROVIDERS = {
    "tomtom": (tomtom, lambda: TomTomProvider(api_key=KEY)),
    "google": (google_places, lambda: GooglePlacesProvider(api_key=KEY)),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(PROVIDERS))
async def test_a_rejected_search_logs_no_key(name, caplog):
    module, make = PROVIDERS[name]
    real_client = httpx.AsyncClient
    urls: list[str] = []

    def reject(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(403, request=request)

    def client_factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(reject))

    caplog.set_level(logging.DEBUG)
    with patch.object(module.httpx, "AsyncClient", client_factory):
        results = await make().search(45.0, -93.0, 5000, [POICategory.GAS_STATION])

    assert results == []
    assert urls and KEY in urls[0]  # the premise: the key travels in the URL
    assert KEY not in caplog.text
