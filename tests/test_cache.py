"""
Tests for app.core.cache — the Upstash REST wrapper.

No real network calls are made. httpx.AsyncClient is monkeypatched with a
fake client so we can verify both the "disabled" (no config) and
"enabled" (mocked Upstash response) code paths deterministically.
"""

import httpx
import pytest

from app.core import cache as cache_module
from app.core.config import settings


class _FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    """Records the JSON body of the POST it receives and returns a canned result."""

    last_payload = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last_payload = json
        command = json[0]
        if command == "GET":
            return _FakeResponse({"result": "cached-value"})
        if command == "SET":
            return _FakeResponse({"result": "OK"})
        if command == "DEL":
            return _FakeResponse({"result": 1})
        return _FakeResponse({"result": None})


class _FailingAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        raise httpx.ConnectTimeout("simulated timeout")


class _AssertNotCalledAsyncClient:
    """Used to prove disabled cache never attempts a network call."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("httpx.AsyncClient should not be constructed when cache is disabled")


@pytest.fixture(autouse=True)
def _reset_upstash_settings(monkeypatch):
    # Ensure every test starts from a known "disabled" baseline.
    monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_URL", "")
    monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_TOKEN", "")
    yield


class TestCacheDisabled:
    async def test_cache_get_returns_none_without_network_call(self, monkeypatch):
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _AssertNotCalledAsyncClient)
        result = await cache_module.cache_get("some-key")
        assert result is None

    async def test_cache_set_noops_without_network_call(self, monkeypatch):
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _AssertNotCalledAsyncClient)
        await cache_module.cache_set("some-key", "some-value")  # must not raise

    async def test_cache_delete_noops_without_network_call(self, monkeypatch):
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _AssertNotCalledAsyncClient)
        await cache_module.cache_delete("some-key")  # must not raise


class TestCacheEnabled:
    def _enable(self, monkeypatch):
        monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_URL", "https://fake.upstash.io")
        monkeypatch.setattr(settings, "UPSTASH_REDIS_REST_TOKEN", "fake-token")

    async def test_cache_get_returns_value_on_hit(self, monkeypatch):
        self._enable(monkeypatch)
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _FakeAsyncClient)
        result = await cache_module.cache_get("url:abc")
        assert result == "cached-value"
        assert _FakeAsyncClient.last_payload[0] == "GET"
        assert _FakeAsyncClient.last_payload[1] == "url:abc"

    async def test_cache_set_sends_correct_command_with_ttl(self, monkeypatch):
        self._enable(monkeypatch)
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _FakeAsyncClient)
        await cache_module.cache_set("url:abc", "some-json", ttl_seconds=3600)
        assert _FakeAsyncClient.last_payload == ["SET", "url:abc", "some-json", "EX", "3600"]

    async def test_cache_delete_sends_correct_command(self, monkeypatch):
        self._enable(monkeypatch)
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _FakeAsyncClient)
        await cache_module.cache_delete("url:abc")
        assert _FakeAsyncClient.last_payload == ["DEL", "url:abc"]

    async def test_network_failure_fails_open_returns_none(self, monkeypatch):
        """If Upstash is unreachable, cache_get must not raise — just miss."""
        self._enable(monkeypatch)
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _FailingAsyncClient)
        result = await cache_module.cache_get("url:abc")
        assert result is None

    async def test_network_failure_on_set_does_not_raise(self, monkeypatch):
        self._enable(monkeypatch)
        monkeypatch.setattr(cache_module.httpx, "AsyncClient", _FailingAsyncClient)
        await cache_module.cache_set("url:abc", "value")  # must not raise
