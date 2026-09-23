"""Telegram fuel commands, fetched from Telegram by long polling.

MyGarage asks Telegram for new messages (``getUpdates``) instead of receiving
them at a webhook, so fuel commands work on any install that can reach
``api.telegram.org``, public address or not, and nothing inbound is exposed.
Spec: Obsidian builds/mygarage/plans/2026-09-22-telegram-fuel-polling-design.md.

One task, started and stopped with the app. Every round re-reads the
switches, so turning fuel commands on or off needs no restart.

Exactly-once: the stored offset (the next update id to ask for) moves past an
update in the same commit as the fill-up that update logged
(``_handle_update``). A bot cannot poll while a webhook is set, so starting
clears any webhook on the bot.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import httpx
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.settings_service import SettingsService
from app.services.telegram_fuel_commands import handle_message
from app.utils.datetime_utils import utc_now
from app.utils.household_time import load_household_zone
from app.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)

PollerState = Literal["off", "starting", "listening", "error"]
PollerErrorCode = Literal[
    "bot_token_rejected", "conflict", "rate_limited", "unreachable", "database_error", "unexpected"
]

OFFSET_KEY = "telegram_update_offset"
LONG_POLL_SECONDS = 25
OFF_WAIT_SECONDS = 30.0
ERROR_WAIT_SECONDS = 60.0
BACKOFF_START_SECONDS = 5.0
BACKOFF_MAX_SECONDS = 60.0
SKIP_AFTER_FAILURES = 3
SKIPPED_REPLY = "Could not log that: something went wrong."
COMMITTED_REPLY = "Logged fill-up."

_TOKEN_BOT_ID = re.compile(r"^(\d+):")
_STORED_OFFSET = re.compile(r"^(\d+):(\d+)$")


class TelegramApiError(Exception):
    """Telegram answered with an HTTP error or ``ok: false``. Its text holds no URL."""

    def __init__(self, status: int, description: str | None, retry_after: int | None) -> None:
        """Keep Telegram's status, description and requested wait."""
        super().__init__(f"HTTP {status}")
        self.status = status
        self.description = description
        self.retry_after = retry_after


class BotTokenRejectedError(Exception):
    """The saved token has no numeric bot id, so it cannot be a bot token."""


@dataclass(frozen=True)
class _Config:
    token: str
    chat_id: str


def is_outage(exc: BaseException) -> bool:
    """Whether a failure means the database is unreachable, not that a message is bad.

    ``OSError`` is not optional: with PostgreSQL down, asyncpg's
    ``ConnectionRefusedError`` reaches the caller unwrapped by SQLAlchemy.
    """
    if isinstance(exc, sa_exc.OperationalError | sa_exc.InterfaceError | OSError):
        return True
    return isinstance(exc, sa_exc.DBAPIError) and exc.connection_invalidated


def bot_id_of(token: str) -> str | None:
    """The numeric bot id a token starts with, or None when it has none."""
    match = _TOKEN_BOT_ID.match(token)
    return match.group(1) if match else None


def parse_stored_offset(value: str | None, bot_id: str) -> int | None:
    """The stored next offset for this bot; None when absent, unreadable or another bot's.

    Update ids are per bot. A higher offset left by another bot would confirm,
    and so silently drop, every message to this one.
    """
    match = _STORED_OFFSET.match(value or "")
    if match is None or match.group(1) != bot_id:
        return None
    return int(match.group(2))


async def _read_config(db: AsyncSession) -> _Config | None:
    """The bot and chat to poll for, or None while fuel commands are off."""
    if not (
        await SettingsService.get_bool(db, "telegram_enabled")
        and await SettingsService.get_bool(db, "telegram_inbound_enabled")
    ):
        return None
    token_row = await SettingsService.get(db, "telegram_bot_token")
    token = (token_row.value or "").strip() if token_row else ""
    if not token:
        return None
    chat_row = await SettingsService.get(db, "telegram_chat_id")
    return _Config(token=token, chat_id=(chat_row.value or "").strip() if chat_row else "")


async def _stage_offset(db: AsyncSession, bot_id: str, next_offset: int) -> None:
    """Write the offset into this session (flushed, not committed)."""
    await SettingsService.set(db, OFFSET_KEY, f"{bot_id}:{next_offset}", category="notifications")


async def _clear_offset(db: AsyncSession) -> None:
    """Forget the offset so switching on again skips the backlog.

    Runs every 30 s while fuel commands are off. SQLAlchemy emits no UPDATE
    for an unchanged value, so an already-empty row costs no write.
    """
    row = await SettingsService.get(db, OFFSET_KEY)
    if row is not None:
        row.value = ""
        await db.commit()


def _default_client() -> httpx.AsyncClient:
    # Read timeout above the long poll's, so a quiet poll ends by Telegram's clock.
    return httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=10.0))


class _TelegramApi:
    """The Bot API methods the poller uses. Never puts the URL in an error."""

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._base = f"https://api.telegram.org/bot{token}"

    async def call(self, method: str, **params: Any) -> Any:
        """Call one method; its ``result`` on success, ``TelegramApiError`` otherwise."""
        response = await self._client.post(f"{self._base}/{method}", json=params)
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            body = {}
        if response.status_code >= 400 or not body.get("ok"):
            parameters = body.get("parameters") or {}
            raise TelegramApiError(
                response.status_code, body.get("description"), parameters.get("retry_after")
            )
        return body.get("result")


class TelegramPoller:
    """Polls Telegram for fuel commands while Telegram and fuel commands are on."""

    def __init__(self) -> None:
        """Start in the off state; ``start()`` begins polling."""
        self._task: asyncio.Task[None] | None = None
        self._state: PollerState = "off"
        self._error_code: PollerErrorCode | None = None
        self._description: str | None = None
        self._since: datetime = utc_now()
        #: The bot polling was started for; None means (re)start first.
        self._polling_bot: str | None = None
        #: Counted failures per (bot id, update id), with the last exception type.
        #: Update ids are per bot, so another bot's update may share the number.
        self._failures: dict[tuple[str, int], tuple[int, str]] = {}
        self._backoff = BACKOFF_START_SECONDS
        #: Test seams.
        self.client_factory: Callable[[], httpx.AsyncClient] = _default_client
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    @property
    def status(self) -> dict[str, Any]:
        """The state for Settings > Notifications > Telegram."""
        return {
            "state": self._state,
            "error_code": self._error_code,
            "description": self._description,
            "since": self._since,
        }

    async def start(self) -> None:
        """Start polling in the background. Always started: it watches its own switches."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="telegram-poller")

    async def stop(self) -> None:
        """Cancel the task and wait for it, as ``MQTTSubscriber.stop()`` does."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._set_state("off")

    async def _run(self) -> None:
        # ``run_once`` catches ``Exception``, which excludes CancelledError, so
        # ``stop()`` always ends the loop.
        client = self.client_factory()
        try:
            while True:
                wait = await self.run_once(client)
                if wait > 0:
                    await self.sleep(wait)
        finally:
            await client.aclose()

    async def run_once(self, client: httpx.AsyncClient) -> float:
        """One round; returns the seconds to wait before the next."""
        try:
            return await self._round(client)
        except TelegramApiError as exc:
            self._polling_bot = None
            if exc.status in (401, 404):
                return self._fail("bot_token_rejected", exc.description, ERROR_WAIT_SECONDS)
            if exc.status == 409:
                return self._fail("conflict", exc.description, ERROR_WAIT_SECONDS)
            if exc.status == 429:
                return self._fail(
                    "rate_limited", exc.description, float(exc.retry_after or ERROR_WAIT_SECONDS)
                )
            if exc.status >= 500:
                return self._fail("unreachable", exc.description, self._next_backoff())
            return self._fail("unexpected", exc.description, ERROR_WAIT_SECONDS)
        except BotTokenRejectedError:
            self._polling_bot = None
            return self._fail("bot_token_rejected", None, ERROR_WAIT_SECONDS)
        except httpx.HTTPError as exc:
            self._polling_bot = None
            return self._fail("unreachable", None, self._next_backoff(), describe_http_error(exc))
        except Exception as exc:
            self._polling_bot = None
            if is_outage(exc):
                # Class name only: a DBAPIError's text holds the SQL and its parameters.
                return self._fail("database_error", None, self._next_backoff(), type(exc).__name__)
            return self._fail("unexpected", None, ERROR_WAIT_SECONDS, type(exc).__name__)

    async def _round(self, client: httpx.AsyncClient) -> float:
        async with AsyncSessionLocal() as db:
            config = await _read_config(db)
            if config is None:
                await _clear_offset(db)
                self._polling_bot = None
                self._set_state("off")
                self._backoff = BACKOFF_START_SECONDS
                return OFF_WAIT_SECONDS
        bot_id = bot_id_of(config.token)
        if bot_id is None:
            raise BotTokenRejectedError
        api = _TelegramApi(client, config.token)
        if self._polling_bot != bot_id:
            if self._state != "error":
                # While failing, stay "error": no state flapping, no repeated warning.
                self._set_state("starting")
            await api.call("deleteWebhook", drop_pending_updates=False)
            await self._bootstrap(api, bot_id)
            self._polling_bot = bot_id
        offset = await self._read_offset(bot_id)
        if offset is None:
            # Cleared or replaced since polling started: an admin edit, a restore.
            await self._bootstrap(api, bot_id)
            offset = await self._read_offset(bot_id) or 0
        updates = await api.call(
            "getUpdates", offset=offset, timeout=LONG_POLL_SECONDS, allowed_updates=["message"]
        )
        async with AsyncSessionLocal() as db:
            if await _read_config(db) is None:
                return 0.0  # switched off while waiting: the next round takes the off branch
        for update in updates or []:
            await self._handle_update(api, bot_id, config.chat_id, update)
        # Only a whole round counts as recovery. Reset any earlier, and a
        # database that reads but cannot write would be retried every 5 s.
        self._set_state("listening")
        self._backoff = BACKOFF_START_SECONDS
        return 0.0

    async def _bootstrap(self, api: _TelegramApi, bot_id: str) -> None:
        """Resume from this bot's stored offset, or forget the backlog (spec D4).

        With an empty queue the stored offset is 0 ("initialised, nothing
        handled"), so a restart resumes instead of bootstrapping again and
        discarding whatever was sent while MyGarage was down.
        """
        if await self._read_offset(bot_id) is not None:
            return
        latest = await api.call("getUpdates", offset=-1, timeout=0)
        await self._commit_offset(bot_id, latest[-1]["update_id"] + 1 if latest else 0)

    async def _read_offset(self, bot_id: str) -> int | None:
        async with AsyncSessionLocal() as db:
            row = await SettingsService.get(db, OFFSET_KEY)
            return parse_stored_offset(row.value if row else None, bot_id)

    async def _commit_offset(self, bot_id: str, next_offset: int) -> None:
        async with AsyncSessionLocal() as db:
            await _stage_offset(db, bot_id, next_offset)
            await db.commit()

    async def _handle_update(
        self, api: _TelegramApi, bot_id: str, chat_id: str, update: dict[str, Any]
    ) -> None:
        update_id = int(update["update_id"])
        message = update.get("message") or {}
        key = (bot_id, update_id)
        count, error_type = self._failures.get(key, (0, ""))
        if count >= SKIP_AFTER_FAILURES:
            await self._skip(api, bot_id, update_id, message, error_type)
            return
        try:
            async with AsyncSessionLocal() as db:
                await load_household_zone(db)
                # Staged in this session, so a fill-up's commit carries it.
                await _stage_offset(db, bot_id, update_id + 1)
                result = await handle_message(db, message, chat_id)
                if not result.logged:
                    # Commit the offset alone, never whatever the session holds.
                    await db.rollback()
                    await _stage_offset(db, bot_id, update_id + 1)
                    await db.commit()
        except Exception as exc:
            if await self._is_past(bot_id, update_id):
                # The fill-up committed and a later step failed. Say so, or the
                # user re-sends and logs it twice.
                self._failures.pop(key, None)
                await self._reply(api, message, COMMITTED_REPLY)
                return
            if not is_outage(exc):
                self._failures[key] = (count + 1, type(exc).__name__)
            raise  # stop the batch; the next round retries from the durable offset
        self._failures.pop(key, None)
        if result.reply:
            await self._reply(api, message, result.reply)

    async def _is_past(self, bot_id: str, update_id: int) -> bool:
        stored = await self._read_offset(bot_id)
        return stored is not None and stored > update_id

    async def _skip(
        self,
        api: _TelegramApi,
        bot_id: str,
        update_id: int,
        message: dict[str, Any],
        error_type: str,
    ) -> None:
        # If this commit fails, it raises; the count stays, and the next round skips again.
        await self._commit_offset(bot_id, update_id + 1)
        self._failures.pop((bot_id, update_id), None)
        logger.error(
            "Telegram fuel commands: update %d failed %d times (%s); skipped",
            update_id,
            SKIP_AFTER_FAILURES,
            error_type,
        )
        await self._reply(api, message, SKIPPED_REPLY)

    async def _reply(self, api: _TelegramApi, message: dict[str, Any], text: str) -> None:
        """Send a reply. A lost reply never undoes a committed update."""
        chat_id = (message.get("chat") or {}).get("id")
        if chat_id is None:
            return
        try:
            await api.call("sendMessage", chat_id=chat_id, text=text)
        except Exception as exc:
            detail = (
                exc.description
                if isinstance(exc, TelegramApiError) and exc.description
                else describe_http_error(exc)
            )
            logger.warning("Telegram fuel commands: reply not sent (%s)", detail)

    def _set_state(self, state: PollerState) -> None:
        if state != self._state:
            self._since = utc_now()
        self._state = state
        self._error_code = None
        self._description = None

    def _fail(
        self, code: PollerErrorCode, description: str | None, wait: float, detail: str | None = None
    ) -> float:
        if self._state != "error" or self._error_code != code:
            logger.warning("Telegram fuel commands: %s%s", code, f" ({detail})" if detail else "")
            self._since = utc_now()
        self._state = "error"
        self._error_code = code
        self._description = description
        return wait

    def _next_backoff(self) -> float:
        wait = self._backoff
        self._backoff = min(self._backoff * 2, BACKOFF_MAX_SECONDS)
        return wait


telegram_poller = TelegramPoller()
