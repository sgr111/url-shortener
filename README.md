# Smart URL Shortener

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-red?logo=python&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Upstash_REST-DC382D?logo=redis&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-81_passing-brightgreen?logo=pytest&logoColor=white)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

> A production-grade URL shortener REST API built with FastAPI and PostgreSQL — Base62-encoded short codes, cache-aside redirects via Upstash Redis, retry-safe webhook delivery, and per-user JWT rate limiting. Every architectural choice (REST-based Redis, a Postgres retry-queue instead of Celery, JWT-keyed rate limiting) was made to run correctly on a free-tier host with no persistent worker process.

## Introduction

- Production-grade URL shortener API — FastAPI, JWT auth, async SQLAlchemy + PostgreSQL, Base62 short codes with guaranteed no collisions.
- Core redirect path is cache-aside through Upstash Redis (REST API, not a persistent TCP client) with a 1-hour TTL, falling back cleanly to Postgres on any cache miss or Upstash error.
- Webhook-on-click is delivered through a Postgres retry-queue table processed by an in-process APScheduler job (exponential backoff, max 5 retries) rather than a fire-and-forget `BackgroundTask` — so a briefly-down webhook target doesn't silently lose the event.
- Also ships password-protected links, bulk CSV shortening, QR code generation, per-user (JWT-keyed) rate limiting, IDOR-hardened ID-based endpoints, and a soft-delete model that preserves analytics history.
- Covered by an 81-test suite — including a dedicated cache-integration suite verifying cache-aside behavior against a real DB — with the full suite run in CI on every push.

---

## Architecture

```
                ┌─────────────────────────────────┐
                │         FastAPI Application      │
                │                                  │
     JWT Auth ──┤  api/v1/endpoints/auth.py         │
                │  api/v1/endpoints/urls.py  ───────┼── async SQLAlchemy ORM
                │  api/v1/endpoints/redirect.py     │        │
                └──────────────┬──────────────────-┘        │
                               │                             ▼
                ┌──────────────▼──────────────────┐   ┌─────────────┐
                │        core/cache.py             │   │  PostgreSQL │
                │   Upstash Redis (REST, fail-open)│   │   (Neon)    │
                │   cache-aside on redirect lookup │   │             │
                │             │                    │   │  urls       │
                │   1hr TTL ─▶│◀── miss ───────────┼──▶│  click_events│
                │             │      refresh on hit│   │  webhook_   │
                └──────────────────────────────────┘   │   queue     │
                               │                        └─────────────┘
                ┌──────────────▼──────────────────┐            │
                │      core/scheduler.py            │            │
                │   APScheduler — runs every minute │            │
                │   drains webhook_queue, exponential│──────────┘
                │   backoff, max 5 retries          │
                └────────────────────────────────────┘

        core/limiter.py (slowapi) ── per-user (JWT) / per-IP (anonymous)
        key strategy, applied to auth + shortening endpoints

        core/base62.py ── deterministic encode/decode of the
        auto-incremented DB id → guaranteed-unique short code
```

---

## A FastAPI Project Demonstrating

- **Base62 Encoding** — deterministic, collision-free short codes from an auto-incremented DB id
- **Cache-Aside Pattern** — Upstash Redis (REST) in front of Postgres, fail-open on any cache error
- **JWT Auth** — register, login, per-user protected endpoints
- **SlowAPI** — per-user (JWT) / per-IP (anonymous) rate limiting
- **Postgres Retry-Queue** — webhook delivery via a queue table + APScheduler, not Celery
- **Atomic Updates** — single `UPDATE ... SET click_count = click_count + 1` — no read-modify-write race
- **BackgroundTasks** — click event logging happens after the redirect response is sent
- **IDOR Hardening** — ownership checks + dedicated tests on every ID-based endpoint
- **Alembic** — versioned schema migrations (3 revisions)
- **QR Codes** — local generation via `qrcode[pil]`, no external API
- **pytest** — 81-test suite, SQLite in-memory, real Upstash force-disabled for the whole suite

---

## What This Project Does — At A Glance

This is a **URL shortener API** where anyone can shorten a link anonymously, or register for an account to manage links, view analytics, and use bulk/webhook features. The redirect hot path is optimized for latency; everything else is optimized for correctness under free-tier hosting constraints.

### Core Features

| Feature | Endpoint | What It Does |
|---------|----------|--------------|
| **Shorten URL** | `POST /api/v1/urls/shorten` | Base62-encodes a new short code; supports optional `webhook_url` and `password` |
| **Redirect** | `GET /{short_code}` | Cache-aside lookup (Redis → Postgres), HTTP 302 |
| **Bulk Shorten** | `POST /api/v1/urls/bulk-shorten` | Upload a CSV of URLs, shorten them all in one request |
| **QR Code** | `GET /api/v1/urls/{short_code}/qr` | Returns a scannable PNG for the short URL |
| **Analytics** | `GET /api/v1/urls/{id}/analytics` | Total clicks, recent clicks, top countries |

### Core Infrastructure

| Feature | Technology | What It Does |
|---------|-----------|--------------|
| **Cache-Aside Redirect** | Upstash Redis (REST) | Redis-first lookup, Postgres fallback, fail-open on any Redis error, 1hr TTL |
| **Webhook Delivery** | Postgres `webhook_queue` + APScheduler | Retry-safe delivery, exponential backoff, max 5 retries — survives a briefly-down target |
| **Per-User Rate Limiting** | slowapi | JWT identity for authenticated users, IP for anonymous — no shared quota per office network |
| **Click Logging** | FastAPI `BackgroundTask` | Logged after the redirect response is sent — zero latency impact on the redirect itself |
| **Atomic Click Counting** | Raw SQL `UPDATE` | Single atomic increment — no race under concurrent traffic |
| **Password-Protected Links** | bcrypt hash on `urls.password_hash` | Checked *before* click counting and webhook firing |
| **Expiry** | `expires_at` (date) / `max_clicks` (count) | Link returns `410 Gone` once either condition is met |
| **IDOR Hardening** | `user_id` ownership checks | Every ID-based endpoint tested with a cross-user 403/404 case |
| **JWT Auth** | python-jose + passlib (bcrypt) | Stateless auth, 30-min access tokens |
| **Migrations** | Alembic | 3 revisions: initial schema, webhook queue, password-protected links |

---

## Project Structure

```
url_shortener/
├── .github/workflows/
│   └── tests.yml            ← CI: installs deps, runs pytest on every push
├── app/
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── auth.py         ← register, login (rate-limited)
│   │   │   ├── urls.py         ← shorten, bulk-shorten, list, analytics, delete, qr
│   │   │   └── redirect.py     ← GET /{short_code} — core feature
│   │   ├── dependencies.py     ← get_current_user, get_optional_user
│   │   └── router.py
│   ├── core/
│   │   ├── base62.py           ← Base62 encode/decode algorithm
│   │   ├── cache.py            ← Upstash Redis REST wrapper (fail-open)
│   │   ├── config.py           ← Settings from .env
│   │   ├── limiter.py          ← slowapi Limiter, per-user/per-IP key strategy
│   │   ├── scheduler.py        ← APScheduler webhook retry-queue processor
│   │   └── security.py         ← JWT + bcrypt utilities
│   ├── db/
│   │   └── session.py          ← Async engine + get_db dependency
│   ├── models/
│   │   ├── url.py              ← URL, ClickEvent, WebhookQueue ORM models
│   │   └── user.py              ← User ORM model
│   ├── schemas/
│   │   ├── analytics.py        ← AnalyticsOut, ClickEventOut
│   │   ├── url.py              ← URLCreate, URLOut, BulkURLResult, ...
│   │   └── user.py             ← UserRegister, UserLogin, TokenResponse
│   ├── services/
│   │   ├── url_service.py      ← All URL business logic incl. cache-aside
│   │   └── user_service.py     ← User business logic
│   └── main.py                 ← App factory + lifespan (starts scheduler)
├── alembic/
│   └── versions/
│       ├── 001_initial.py                    ← users, urls, click_events
│       ├── 002_webhook_queue.py              ← webhook_queue table, urls.webhook_url
│       └── 003_password_protected_links.py   ← urls.password_hash
├── tests/
│   ├── conftest.py             ← SQLite fixtures, rate-limiter + cache isolation
│   ├── test_base62.py          ← 14 algorithm unit tests
│   ├── test_auth.py            ← 8 auth tests
│   ├── test_urls.py            ← shorten, bulk CSV, QR, list, delete, analytics, IDOR
│   ├── test_redirect.py        ← redirect, expiry, password protection, webhooks
│   ├── test_cache.py           ← Upstash REST wrapper, fully mocked
│   └── test_cache_integration.py  ← cache-aside behavior against real DB
├── .env.example
├── alembic.ini
├── pytest.ini
└── requirements.txt
```

---

## How It Works

### Base62 Encoding — No Collisions by Design
Instead of random strings, the auto-incremented database id is encoded to Base62
(`0-9`, `a-z`, `A-Z`). Guaranteed unique, URL-safe, and decodable back to the id —
no collision checks or retry loops needed at write time.

### Cache-Aside Redirect Lookup (Upstash Redis)
`get_url_by_code()` checks Redis first, falls back to Postgres on a miss, and
populates the cache with a 1-hour TTL. Upstash's **REST** API is used specifically
because it needs no persistent TCP connection — Render's free tier sleeps on
inactivity, and a normal Redis client's connection wouldn't reliably survive that.
The cache is **fail-open**: any Upstash error (timeout, outage, bad config) falls
back to a plain DB read rather than breaking the redirect.

A click **refreshes** the cached entry in place (new `click_count`) rather than
deleting it — an earlier version deleted on every click, which looked safer but
meant every subsequent click on a popular link forced a fresh DB read, defeating
the point of caching. Refreshing keeps popular links warm while staying correct
for `max_clicks` enforcement.

### Postgres Retry-Queue for Webhooks (Not Celery)
Webhook-on-click is delivered via a `webhook_queue` table + an in-process
APScheduler job (runs every minute, exponential backoff, max 5 retries) —
not a plain `BackgroundTask`. A fire-and-forget task loses the event if the
target endpoint is briefly down; the queue survives that. Celery was
deliberately avoided: it needs a separate always-on worker process, which
Render's free tier can't reliably host.

### Per-User Rate Limiting
`slowapi`'s key function checks for a valid JWT first (keys by user email) and
falls back to IP only for anonymous requests — so two authenticated users on
the same office network don't share a quota.

### IDOR Hardening
Every ID-based endpoint (analytics, delete) checks ownership (`user_id` match)
before acting, with dedicated tests that create a resource as User A and assert
User B gets 403/404 attempting to touch it by id.

### Password-Protected Links
Password check happens **before** click counting and webhook firing in the
redirect handler — a wrong or missing password never increments `click_count`
or triggers a webhook.

### Atomic Click Counting — No Race Conditions
```sql
UPDATE urls SET click_count = click_count + 1 WHERE id = X
```
Single atomic operation — no read-modify-write race under concurrent traffic.

### Background Task Click Logging — Zero Redirect Latency Impact
Click events are logged **after** the redirect response is sent, so users are
redirected instantly regardless of DB write latency.

---

## All Endpoints

### Authentication
| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| POST | `/api/v1/auth/register` | No | 5/min | Register with email + password |
| POST | `/api/v1/auth/login` | No | 5/min | Login, receive JWT token |

### URLs
| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| POST | `/api/v1/urls/shorten` | Optional | 10/min | Create short URL (supports `webhook_url`, `password`) |
| POST | `/api/v1/urls/bulk-shorten` | Optional | 3/min | Shorten many URLs from an uploaded CSV |
| GET | `/api/v1/urls/` | Required | — | List your URLs (paginated) |
| GET | `/api/v1/urls/{id}/analytics` | Required | — | Click stats for a URL |
| DELETE | `/api/v1/urls/{id}` | Required | — | Soft delete a URL |
| GET | `/api/v1/urls/{short_code}/qr` | No | — | PNG QR code for the short URL |

### Core
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/{short_code}` | No (or `?password=`) | Redirect to original URL |
| GET | `/health` | No | Health check |

---

## Quick Start

### 1. Clone and create virtual environment
```bash
git clone https://github.com/sgr111/url-shortener.git
cd url-shortener

# Windows
python -m venv venv
venv\Scripts\Activate.ps1

# Mac/Linux
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
```
```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/url_shortener
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ENVIRONMENT=development
BASE_URL=http://localhost:8000

# Optional — leave blank to disable caching (fails open to DB-only)
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
CACHE_TTL_SECONDS=3600
```

### 4. Create database and run migrations
```bash
psql -U postgres -c "CREATE DATABASE url_shortener;"
alembic upgrade head
```

### 5. Start the server
```bash
uvicorn app.main:app --reload
```
API live at `http://localhost:8000` · Swagger docs at `http://localhost:8000/docs`

---

## Configuration Management

All environment-driven settings — the JWT secret, token expiry, the database URL,
and the optional Upstash credentials — are loaded once through `app/core/config.py`
via `pydantic-settings`, so every module imports the same validated `Settings`
object instead of calling `os.getenv()` directly. `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN` are the only genuinely optional values — leaving them
blank disables caching entirely and the app falls back to DB-only reads, rather
than failing to start.

---

## Example Requests

### Shorten a URL with a webhook and password
```bash
curl -X POST http://localhost:8000/api/v1/urls/shorten \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://github.com/sgr111",
    "webhook_url": "https://webhook.site/your-id",
    "password": "secret1"
  }'
```

### Bulk shorten via CSV
```bash
curl -X POST http://localhost:8000/api/v1/urls/bulk-shorten \
  -F "file=@urls.csv"
```
`urls.csv` needs an `original_url` header column, one URL per row.

### Get a QR code
```bash
curl http://localhost:8000/api/v1/urls/1/qr --output qr.png
```

### View analytics
```bash
curl http://localhost:8000/api/v1/urls/1/analytics \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

<details>
<summary><h2 style="display:inline">Testing</h2></summary>

Tests use SQLite — no PostgreSQL needed, and the real Upstash cache is
force-disabled for the whole suite regardless of what's in your local
`.env`, so tests never depend on or interfere with live infrastructure.

### Run the full suite
```bash
pytest -v
```

### Test suite breakdown — 81 tests
| File | Tests | What It Covers |
|------|-------|-----------------|
| `test_base62.py` | 14 | Encode/decode correctness, round-trips, edge cases |
| `test_auth.py` | 8 | Register, login, JWT token, duplicate email |
| `test_urls.py` | 32 | Shorten, bulk CSV, QR, list, delete, analytics, IDOR |
| `test_redirect.py` | 18 | Redirect, expiry, password protection, webhooks |
| `test_cache.py` | 8 | Upstash REST wrapper, fully mocked |
| `test_cache_integration.py` | 4 | Cache-aside behavior against a real DB |

CI runs the full suite on every push via `.github/workflows/tests.yml`. A
separate scheduled workflow (`keep-redis-alive.yml`) pings the Upstash REST
endpoint every 5 days so the free-tier database isn't archived for inactivity
between demo/dev sessions.

</details>

---

<details>
<summary><h2 style="display:inline">Known Limitations & Trade-offs</h2></summary>

### 1. Not Currently Deployed
The project runs locally / in CI only at this point — there is no live
Render (or other) deployment right now. Everything above (redirect,
caching, webhooks, rate limiting) is verified via the local test suite
and manual `uvicorn` runs, not against a hosted instance.

### 2. Upstash Free Tier — 10,000 Commands/Day Cap
Fine at current scale (portfolio/demo traffic). A `keep-redis-alive.yml`
scheduled workflow also pings the database every 5 days purely to prevent
Upstash's free-tier inactivity archiving — that ping itself is a negligible
fraction of the daily quota.

### 3. BackgroundTasks for Click Logging (Not Webhooks)
Click *analytics* events can be lost if the background task fails after the
redirect response is already sent. Webhooks don't share this risk — they're
queue-backed with retries. Acceptable trade-off since analytics isn't
safety-critical, unlike webhook delivery.

### 4. Single PostgreSQL Instance
No replica or failover — a single point of failure. Deferred; not needed at
current scale.

### 5. No Distributed Cache Invalidation Across Regions
Not an issue today — single Upstash instance, single region, no multi-region
deployment planned.

### 6. No API Keys for External Developers
Considered for Phase 2 but not built — JWT + per-user rate limiting already
demonstrates the same auth/throttling concepts, so building a parallel
API-key system added limited additional portfolio value.

</details>

---

<details>
<summary><h2 style="display:inline">Tech Stack</h2></summary>

```
FastAPI            — API framework
SQLAlchemy 2.0     — Async ORM, connection pooling
PostgreSQL 15      — Primary database (Neon, prod) / SQLite (tests)
Alembic            — Schema version control (3 migrations)
Upstash Redis      — Cache-aside layer via REST API (no persistent TCP conn)
python-jose        — JWT encode/decode
passlib (bcrypt)   — Password hashing
Pydantic v2        — Runtime validation, field validators
slowapi            — Per-user (JWT) / per-IP rate limiting
APScheduler        — In-process webhook retry-queue processor
qrcode[pil]        — Local QR code generation, no external API
httpx              — Async test client + webhook delivery
pytest             — 81-test suite, SQLite in-memory
GitHub Actions     — CI on every push + scheduled Upstash keep-alive
```

</details>

---

## Quick Commands

```bash
uvicorn app.main:app --reload               # Start server
alembic upgrade head                        # Apply all migrations
alembic downgrade -1                        # Rollback one migration
pytest -v                                   # Run full test suite (81 tests)
pytest tests/test_cache_integration.py -v   # Cache-aside behavior against real DB
```

---

## Related Projects

| Project | Description |
|---------|--------------|
| [FastAPI Task Manager v4](https://github.com/sgr111/fastapi-task-manager-v4) | CDC audit logs, JSONB, refresh tokens, pagination |
| [GitHub API Pytest Framework](https://github.com/sgr111/github-api-pytest-framework) | 112 assertions, 3-stage CI/CD, Newman, Allure |
| [Activity Tracker API](https://github.com/sgr111/activity-tracker-api-v2) | Gemini AI search, LangChain RAG, pgvector, LLM observability |

---

## Author

Sourabh Sagar
Lucknow, Uttar Pradesh, India
github.com/sgr111 · sgrsourabh111@gmail.com

Built as part of a self-taught transition into Backend Development / QA Automation (SDET) roles.