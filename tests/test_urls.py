import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, register_and_login


class TestShortenURL:
    async def test_shorten_anonymous(self, client: AsyncClient):
        """Anonymous users can shorten URLs."""
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "short_code" in data
        assert "short_url" in data
        assert data["click_count"] == 0
        assert data["is_active"] is True

    async def test_shorten_authenticated(self, client: AsyncClient):
        token = await register_and_login(client)
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://github.com"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["short_code"] is not None

    async def test_shorten_with_expiry(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={
                "original_url": "https://example.com",
                "expires_at": "2099-12-31T00:00:00Z",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    async def test_shorten_with_max_clicks(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com", "max_clicks": 5},
        )
        assert resp.status_code == 201
        assert resp.json()["max_clicks"] == 5

    async def test_shorten_invalid_url(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "not-a-url"},
        )
        assert resp.status_code == 422

    async def test_shorten_max_clicks_zero_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com", "max_clicks": 0},
        )
        assert resp.status_code == 422

    async def test_short_code_is_base62(self, client: AsyncClient):
        """Short code must only contain Base62 characters."""
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
        )
        code = resp.json()["short_code"]
        valid = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        assert all(c in valid for c in code)

    async def test_each_url_gets_unique_short_code(self, client: AsyncClient):
        r1 = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://example.com"}
        )
        r2 = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://google.com"}
        )
        assert r1.json()["short_code"] != r2.json()["short_code"]

    async def test_shorten_password_too_short_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com", "password": "abc"},
        )
        assert resp.status_code == 422

    async def test_shorten_with_password_accepted(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com", "password": "secret1"},
        )
        assert resp.status_code == 201
        assert resp.json()["is_password_protected"] is True
        # Raw password must never be echoed back
        assert "password" not in resp.json()


class TestQRCode:
    async def test_qr_code_returns_png(self, client: AsyncClient):
        create = await client.post(
            "/api/v1/urls/shorten", json={"original_url": "https://example.com"}
        )
        short_code = create.json()["short_code"]

        resp = await client.get(f"/api/v1/urls/{short_code}/qr")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG file signature

    async def test_qr_code_nonexistent_short_code_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/urls/doesnotexist/qr")
        assert resp.status_code == 404

    async def test_qr_code_deleted_url_returns_410(self, client: AsyncClient):
        token = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token),
        )
        url_id = create.json()["id"]
        short_code = create.json()["short_code"]
        await client.delete(f"/api/v1/urls/{url_id}", headers=auth_headers(token))

        resp = await client.get(f"/api/v1/urls/{short_code}/qr")
        assert resp.status_code == 410

    async def test_qr_code_works_for_password_protected_link(self, client: AsyncClient):
        """QR generation doesn't require the password — it only encodes the
        short URL. The redirect endpoint itself still enforces the password
        when someone scans it."""
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com", "password": "secret1"},
        )
        short_code = create.json()["short_code"]

        resp = await client.get(f"/api/v1/urls/{short_code}/qr")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"


class TestBulkUpload:
    async def test_bulk_shorten_valid_csv(self, client: AsyncClient):
        csv_content = (
            "original_url\n"
            "https://example.com\n"
            "https://github.com\n"
            "https://google.com\n"
        )
        resp = await client.post(
            "/api/v1/urls/bulk-shorten",
            files={"file": ("urls.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 3
        assert data["succeeded"] == 3
        assert data["failed"] == 0
        assert all(r["success"] for r in data["results"])

    async def test_bulk_shorten_reports_bad_rows(self, client: AsyncClient):
        csv_content = (
            "original_url\n"
            "https://example.com\n"
            "not-a-valid-url\n"
            " \n"
        )
        resp = await client.post(
            "/api/v1/urls/bulk-shorten",
            files={"file": ("urls.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 3
        assert data["succeeded"] == 1
        assert data["failed"] == 2

    async def test_bulk_shorten_rejects_non_csv(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/urls/bulk-shorten",
            files={"file": ("urls.txt", "original_url\nhttps://example.com\n", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_bulk_shorten_rejects_missing_column(self, client: AsyncClient):
        csv_content = "url\nhttps://example.com\n"
        resp = await client.post(
            "/api/v1/urls/bulk-shorten",
            files={"file": ("urls.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 400


class TestListURLs:
    async def test_list_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/urls/")
        assert resp.status_code == 401

    async def test_list_returns_only_own_urls(self, client: AsyncClient):
        token = await register_and_login(client)
        # Create 2 URLs as authenticated user
        for url in ["https://example.com", "https://github.com"]:
            await client.post(
                "/api/v1/urls/shorten",
                json={"original_url": url},
                headers=auth_headers(token),
            )
        resp = await client.get("/api/v1/urls/", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert "has_more" in data

    async def test_list_pagination(self, client: AsyncClient):
        token = await register_and_login(client)
        for i in range(5):
            await client.post(
                "/api/v1/urls/shorten",
                json={"original_url": f"https://example{i}.com"},
                headers=auth_headers(token),
            )
        resp = await client.get(
            "/api/v1/urls/?skip=0&limit=2", headers=auth_headers(token)
        )
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True

    async def test_list_empty_for_new_user(self, client: AsyncClient):
        token = await register_and_login(client)
        resp = await client.get("/api/v1/urls/", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestDeleteURL:
    async def test_delete_own_url(self, client: AsyncClient):
        token = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token),
        )
        url_id = create.json()["id"]
        resp = await client.delete(
            f"/api/v1/urls/{url_id}", headers=auth_headers(token)
        )
        assert resp.status_code == 204

    async def test_delete_nonexistent_url(self, client: AsyncClient):
        token = await register_and_login(client)
        resp = await client.delete("/api/v1/urls/99999", headers=auth_headers(token))
        assert resp.status_code == 404

    async def test_delete_requires_auth(self, client: AsyncClient):
        resp = await client.delete("/api/v1/urls/1")
        assert resp.status_code == 401

    async def test_delete_wrong_owner_returns_404(self, client: AsyncClient):
        """IDOR check: User B cannot delete User A's URL using its ID."""
        token_a = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token_a),
        )
        url_id = create.json()["id"]

        await client.post(
            "/api/v1/auth/register",
            json={"email": "idor_user_b@example.com", "password": "Testpass1"},
        )
        login_b = await client.post(
            "/api/v1/auth/login",
            json={"email": "idor_user_b@example.com", "password": "Testpass1"},
        )
        token_b = login_b.json()["access_token"]

        resp = await client.delete(
            f"/api/v1/urls/{url_id}", headers=auth_headers(token_b)
        )
        assert resp.status_code == 404

        # Confirm the URL was NOT actually deleted by the wrong owner
        still_there = await client.get(
            "/api/v1/urls/", headers=auth_headers(token_a)
        )
        assert still_there.json()["total"] == 1


class TestAnalytics:
    async def test_analytics_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/urls/1/analytics")
        assert resp.status_code == 401

    async def test_analytics_returns_correct_structure(self, client: AsyncClient):
        token = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token),
        )
        url_id = create.json()["id"]
        resp = await client.get(
            f"/api/v1/urls/{url_id}/analytics", headers=auth_headers(token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_clicks"] == 0
        assert data["short_code"] is not None
        assert "recent_clicks" in data
        assert "top_countries" in data

    async def test_analytics_wrong_owner_returns_404(self, client: AsyncClient):
        # Create URL as user 1
        token1 = await register_and_login(client)
        create = await client.post(
            "/api/v1/urls/shorten",
            json={"original_url": "https://example.com"},
            headers=auth_headers(token1),
        )
        url_id = create.json()["id"]

        # Register user 2 and try to access user 1's analytics
        await client.post(
            "/api/v1/auth/register",
            json={"email": "user2@example.com", "password": "Testpass1"},
        )
        resp2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "user2@example.com", "password": "Testpass1"},
        )
        token2 = resp2.json()["access_token"]

        resp = await client.get(
            f"/api/v1/urls/{url_id}/analytics", headers=auth_headers(token2)
        )
        assert resp.status_code == 404