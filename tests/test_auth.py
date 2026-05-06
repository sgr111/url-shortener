import pytest
from httpx import AsyncClient


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "Testpass1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "user@example.com"
        assert data["is_active"] is True
        assert "id" in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = {"email": "dup@example.com", "password": "Testpass1"}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    async def test_register_weak_password_no_uppercase(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "alllower1"},
        )
        assert resp.status_code == 422

    async def test_register_weak_password_no_digit(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "NoDigitPass"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "Testpass1"},
        )
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "Testpass1"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "Testpass1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "wp@example.com", "password": "Testpass1"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wp@example.com", "password": "WrongPass1"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "Testpass1"},
        )
        assert resp.status_code == 401
