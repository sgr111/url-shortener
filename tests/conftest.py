"""
Test configuration — mirrors your v4 pattern exactly.

Key decisions:
  - SQLite (aiosqlite) for tests — no PostgreSQL needed locally
  - Limiter storage reset before every test — real limits stay active,
    but one test's quota usage never bleeds into the next test
  - Function-scoped DB — each test gets a clean slate
  - AsyncClient (httpx) — same as v4
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_url_shortener.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
def _disable_real_cache_by_default(monkeypatch):
    """
    Force the Upstash cache OFF for every test, regardless of what's in
    the developer's local .env.

    Why this matters: pydantic-settings reads the real .env file, so once
    real UPSTASH_REDIS_REST_URL/TOKEN values are configured for local dev,
    every test run would otherwise talk to the *real* Upstash cache too.
    That cache is an external, persistent store — it is NOT reset between
    tests the way the SQLite test DB is. Since short_codes restart from
    "1" in every test (fresh DB), a later test can end up reading another
    test's leftover cached entry for the same key, causing failures that
    have nothing to do with the code under test (e.g. an "expired URL"
    test getting back a still-valid cached row from an earlier test).

    Tests that specifically want to exercise the real Upstash code path
    (tests/test_cache.py's TestCacheEnabled) re-enable it themselves via
    monkeypatch inside the test body, which runs after this fixture and
    so takes precedence.
    """
    monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_URL", "")
    monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_TOKEN", "")


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    # Reset the rate limiter's in-memory storage before every test so that
    # quota used up by one test (e.g. register/login called in a helper)
    # never bleeds into the next test. Without this, real @limiter.limit(...)
    # decorators on endpoints will cause unrelated tests to fail with 429s
    # once the whole suite's request count crosses the per-minute threshold.
    limiter.reset()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def register_and_login(client: AsyncClient) -> str:
    """Register a user and return a valid JWT token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "Testpass1"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "Testpass1"},
    )
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}