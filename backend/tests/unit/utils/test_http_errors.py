"""An HTTP failure is described without its URL.

httpx puts the full request URL in an HTTPStatusError's text. Telegram's bot
token is in that URL, and a Discord or Slack webhook URL is itself the secret.
"""

import logging

import httpx

from app.utils.http_errors import describe_http_error

SECRET_URL = "https://api.telegram.org/bot123456:SECRET-token/sendMessage"


def status_error(code: int, url: str = SECRET_URL) -> httpx.HTTPStatusError:
    """A real HTTPStatusError, as raise_for_status builds it."""
    response = httpx.Response(code, request=httpx.Request("POST", url))
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("raise_for_status did not raise")


def test_the_premise_httpx_puts_the_url_in_the_text():
    assert "SECRET-token" in str(status_error(400))


def test_a_status_error_is_described_by_its_status_only():
    assert describe_http_error(status_error(400)) == "HTTP 400"


def test_another_httpx_error_is_described_by_its_type():
    exc = httpx.ConnectError("boom", request=httpx.Request("POST", SECRET_URL))
    assert describe_http_error(exc) == "ConnectError"


def test_anything_else_keeps_its_message():
    assert describe_http_error(ValueError("bad value")) == "ValueError: bad value"


def test_httpx_request_logging_is_off():
    """httpx logs every request's URL at INFO; app.main turns that off."""
    import app.main  # noqa: F401  (configures logging on import)

    assert logging.getLogger("httpx").level == logging.WARNING
