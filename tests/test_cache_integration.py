"""
Tests that get_url_by_code()/increment_click_count()/deactivate_url()
correctly drive the cache-aside pattern — using a monkeypatched cache
layer so no real Upstash connection is needed, but a real (SQLite) DB.
"""
import json

import pytest
from httpx import AsyncClient

from app.services import url_service
from tests.conftest import auth_headers, register_and_login


class _FakeCacheStore:
    """In-memory stand-in for Redis, so cache-aside logic can be tested
    without a real Upstash connection."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.set_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self.store[key] = value
        self.set_calls.append(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.delete_calls.append(key)


@pytest.fixture
def fake_cache(monkeypatch):
    fake = _FakeCacheStore()
    monkeypatch.setattr(url_service, "cache_get", fake.get)
    monkeypatch.setattr(url_service, "cache_set", fake.set)
    monkeypatch.setattr(url_service, "cache_delete", fake.delete)
    return fake


class TestCacheAsideLookup:
    async def test_cache_miss_populates_cache(self, client: AsyncClient, db_session, fake_cache):
        create = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://example.com"}
        )
        short_code = create.json()["short_code"]

        assert fake_cache.store == {}  # nothing cached yet

        url = await url_service.get_url_by_code(db_session, short_code)
        assert url is not None
        assert f"url:{short_code}" in fake_cache.store  # populated on miss

    async def test_cache_hit_returns_cached_row_without_extra_set(
        self, client: AsyncClient, db_session, fake_cache
    ):
        create = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://example.com"}
        )
        short_code = create.json()["short_code"]

        await url_service.get_url_by_code(db_session, short_code)  # populates cache
        sets_after_first_call = len(fake_cache.set_calls)

        url = await url_service.get_url_by_code(db_session, short_code)  # should hit cache
        assert url.original_url == "https://example.com/"
        assert len(fake_cache.set_calls) == sets_after_first_call  # no re-populate on hit

    async def test_redirect_click_refreshes_cache_instead_of_deleting(
        self, client: AsyncClient, db_session, fake_cache
    ):
        """
        A click should update the cached entry's click_count in place,
        not delete it — deleting would force every subsequent click on a
        popular link back to a DB read, defeating the point of caching.
        """
        create = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://example.com"}
        )
        short_code = create.json()["short_code"]

        await client.get(f"/{short_code}", follow_redirects=False)

        key = f"url:{short_code}"
        assert key not in fake_cache.delete_calls
        assert key in fake_cache.store  # still cached after the click
        cached_data = json.loads(fake_cache.store[key])
        assert cached_data["click_count"] == 1  # refreshed with the new count

    async def test_delete_invalidates_cache(self, client: AsyncClient, db_session, fake_cache):
        token = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token),
        )
        url_id = create.json()["id"]
        short_code = create.json()["short_code"]

        await url_service.get_url_by_code(db_session, short_code)  # populate cache
        await client.delete(f"/api/v1/urls/{url_id}", headers=auth_headers(token))

        assert f"url:{short_code}" in fake_cache.delete_calls