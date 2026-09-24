"""The test suite's database sessions behave like production's."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal


async def test_test_sessions_flush_and_expire_like_production(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A session setting that differs from `app/database.py` changes what a test proves.

    With autoflush on, a service that adds a row and then queries for it in the
    same unit of work passes here and fails in production. Regression tests for
    that defect build their own sessionmakers, so without this check nothing in
    the suite notices the shared one drifting back.
    """
    async with test_sessionmaker() as test_session, AsyncSessionLocal() as production_session:
        for setting in ("autoflush", "expire_on_commit"):
            assert getattr(test_session.sync_session, setting) == getattr(
                production_session.sync_session, setting
            ), f"test sessions and production sessions disagree on {setting}"
