"""Describe an HTTP failure without its request URL.

An ``httpx.HTTPStatusError``'s text includes the full request URL. For
Telegram that URL holds the bot token, and a Discord or Slack webhook URL is
itself the secret, so logging ``str(exc)`` writes the credential to the logs.
A response *body* carries no URL; callers may still show a service's own
error description read from it.
"""

from __future__ import annotations

import httpx


def describe_http_error(exc: BaseException) -> str:
    """A log-safe description: status and type for httpx errors, never their text."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return type(exc).__name__
    return f"{type(exc).__name__}: {exc}"
