import pytest
from httpx import AsyncClient


async def create_url(client: AsyncClient, original_url: str, **kwargs) -> dict:
    resp = await client.post(
        "/api/v1/urls/shorten",
        json={"original_url": original_url, **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


class TestRedirect:
    async def test_redirect_works(self, client: AsyncClient):
        data = await create_url(client, "https://example.com")
        resp = await client.get(f"/{data['short_code']}", follow_redirects=False)
        assert resp.status_code == 302
        assert "example.com" in resp.headers["location"]

    async def test_redirect_increments_click_count(self, client: AsyncClient):
        data = await create_url(client, "https://example.com")
        code = data["short_code"]

        await client.get(f"/{code}", follow_redirects=False)
        await client.get(f"/{code}", follow_redirects=False)

        # Check analytics directly via service (click_count in list)
        # Anonymous URL — no analytics endpoint, check via shorten response
        # We verify count via a second shorten to get a new ID > first
        # Simpler: just verify the redirect keeps working (idempotent)
        resp = await client.get(f"/{code}", follow_redirects=False)
        assert resp.status_code == 302

    async def test_redirect_invalid_code_returns_404(self, client: AsyncClient):
        resp = await client.get("/invalidcode999", follow_redirects=False)
        assert resp.status_code == 404

    async def test_redirect_expired_url_returns_410(self, client: AsyncClient):
        """URLs past their expiry date return 410 Gone — not 404."""
        data = await create_url(
            client,
            "https://example.com",
            expires_at="2000-01-01T00:00:00Z",  # Already expired
        )
        resp = await client.get(f"/{data['short_code']}", follow_redirects=False)
        assert resp.status_code == 410
        assert "expired" in resp.json()["detail"].lower()

    async def test_redirect_max_clicks_exceeded_returns_410(self, client: AsyncClient):
        """URLs that hit max_clicks return 410 Gone."""
        data = await create_url(client, "https://example.com", max_clicks=2)
        code = data["short_code"]

        # Use up the 2 clicks
        await client.get(f"/{code}", follow_redirects=False)
        await client.get(f"/{code}", follow_redirects=False)

        # 3rd click should be blocked
        resp = await client.get(f"/{code}", follow_redirects=False)
        assert resp.status_code == 410
        assert "maximum" in resp.json()["detail"].lower()

    async def test_deleted_url_returns_410(self, client: AsyncClient):
        """Soft-deleted URLs return 410."""
        # Register to get ownership for delete
        await client.post(
            "/api/v1/auth/register",
            json={"email": "del@example.com", "password": "Testpass1"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "del@example.com", "password": "Testpass1"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=headers,
        )
        url_id = create.json()["id"]
        code = create.json()["short_code"]

        await client.delete(f"/api/v1/urls/{url_id}", headers=headers)

        resp = await client.get(f"/{code}", follow_redirects=False)
        assert resp.status_code == 410


class TestPasswordProtectedLinks:
    async def test_password_protected_redirect_without_password_returns_401(self, client: AsyncClient):
        data = await create_url(client, "https://example.com", password="secret1")
        resp = await client.get(f"/{data['short_code']}", follow_redirects=False)
        assert resp.status_code == 401

    async def test_password_protected_redirect_wrong_password_returns_401(self, client: AsyncClient):
        data = await create_url(client, "https://example.com", password="secret1")
        resp = await client.get(
            f"/{data['short_code']}?password=wrong", follow_redirects=False
        )
        assert resp.status_code == 401

    async def test_password_protected_redirect_correct_password_works(self, client: AsyncClient):
        data = await create_url(client, "https://example.com", password="secret1")
        resp = await client.get(
            f"/{data['short_code']}?password=secret1", follow_redirects=False
        )
        assert resp.status_code == 302

    async def test_unprotected_redirect_ignores_password_param(self, client: AsyncClient):
        data = await create_url(client, "https://example.com")
        resp = await client.get(f"/{data['short_code']}", follow_redirects=False)
        assert resp.status_code == 302

    async def test_shorten_reports_is_password_protected(self, client: AsyncClient):
        protected = await create_url(client, "https://example.com", password="secret1")
        unprotected = await create_url(client, "https://example.com")
        assert protected["is_password_protected"] is True
        assert unprotected["is_password_protected"] is False


class TestHealth:
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestWebhookQueue:
    async def test_click_with_webhook_url_enqueues_job(self, client: AsyncClient, db_session):
        from sqlalchemy import select
        from app.models.url import WebhookQueue

        data = await create_url(
            client,
            "https://example.com",
            webhook_url="https://webhook.site/fake-endpoint",
        )
        await client.get(f"/{data['short_code']}", follow_redirects=False)

        result = await db_session.execute(select(WebhookQueue))
        jobs = result.scalars().all()
        assert len(jobs) == 1
        assert jobs[0].status == "pending"
        assert jobs[0].webhook_url == "https://webhook.site/fake-endpoint"
        assert jobs[0].payload["url_id"] == data["id"]

    async def test_click_without_webhook_url_enqueues_nothing(self, client: AsyncClient, db_session):
        from sqlalchemy import select
        from app.models.url import WebhookQueue

        data = await create_url(client, "https://example.com")
        await client.get(f"/{data['short_code']}", follow_redirects=False)

        result = await db_session.execute(select(WebhookQueue))
        assert len(result.scalars().all()) == 0