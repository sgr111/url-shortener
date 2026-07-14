# 🔗 Smart URL Shortener

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-red)
![Redis](https://img.shields.io/badge/Redis-Upstash_REST-DC382D?logo=redis)
![Pytest](https://img.shields.io/badge/Tests-81_passed-brightgreen?logo=pytest)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions)
![License](https://img.shields.io/badge/License-MIT-green)

A **production-grade URL shortener REST API** built with FastAPI and PostgreSQL.
Converts long URLs to short Base62-encoded codes with expiry, click analytics, JWT auth,
per-user rate limiting, Redis caching, retry-safe webhooks, password-protected links,
bulk CSV import, and QR code generation.

> **Live:** Deployed on Render — see repo description for the live URL.

---

## 🎯 Project Highlights

| Metric | Value |
|--------|-------|
| **Short Code Algorithm** | Base62 encoding of auto-incremented DB ID |
| **Redirect Lookup** | Cache-aside via Upstash Redis (REST) → Postgres on miss |
| **Click Logging** | Async BackgroundTask — zero redirect latency impact |
| **Race Condition Prevention** | Atomic SQL `click_count = click_count + 1` |
| **Test Coverage** | 81 tests — 100% pass rate |
| **Auth** | JWT access tokens (30 min expiry) |
| **Rate Limiting** | Per-user (JWT) / per-IP (anonymous), via slowapi |
| **Webhook Delivery** | Postgres retry-queue + APScheduler, exponential backoff |
| **CI/CD** | GitHub Actions — full suite runs on every push |

---

## ✨ Features

- **URL Shortening** — Base62-encoded short codes, guaranteed unique, no collisions
- **Instant Redirect** — HTTP 302, cache-aside lookup (Redis → Postgres)
- **Expiry by Date** — set `expires_at`, link returns 410 Gone after that
- **Expiry by Clicks** — set `max_clicks`, link dies after N clicks
- **Password-Protected Links** — optional password on any link; redirect requires `?password=`
- **Click Analytics** — total clicks, recent clicks, top countries per URL
- **JWT Authentication** — register, login, protected endpoints
- **Anonymous Shortening** — no account needed for basic shortening
- **Per-User Rate Limiting** — authenticated users keyed by identity, not shared IP
- **Bulk Shortening via CSV** — upload a CSV of URLs, shorten them all in one request
- **QR Code Generation** — `GET /urls/{short_code}/qr` returns a scannable PNG
- **Webhook-on-Click** — notify a URL on every click, delivered via a retry-safe queue
- **Redis Caching** — cache-aside pattern on the redirect hot path (Upstash REST)
- **IDOR-Hardened** — ownership checks + dedicated tests on every ID-based endpoint
- **Soft Delete** — `is_active=False`, data + analytics preserved
- **Pagination** — `skip/limit` with `has_more` field, silent MAX_PAGE_SIZE clamping
- **Health Check** — `/health` endpoint for deployment monitoring

---

## 🧰 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Framework | FastAPI 0.111 | Async-native, auto Swagger docs, Pydantic built-in |
| ORM | SQLAlchemy 2.0 (async) | Type-safe, async queries, connection pooling |
| Database | PostgreSQL 15 (Neon, prod) / SQLite (tests) | TIMESTAMPTZ, strict constraints, ACID |
| Cache | Upstash Redis (REST API) | No persistent TCP conn — survives Render free-tier sleep/wake |
| Migrations | Alembic | Version-controlled schema changes |
| Auth | python-jose (JWT) + passlib (bcrypt) | Stateless auth, secure password hashing |
| Validation | Pydantic v2 | Runtime type checking, field validators |
| Rate Limiting | slowapi | Per-user (JWT) / per-IP (anonymous) |
| Scheduling | APScheduler | In-process webhook retry-queue processor |
| QR Codes | qrcode[pil] | Local generation, no external API |
| HTTP Client | httpx | Async test client + Upstash/webhook delivery |
| Testing | pytest + pytest-asyncio | 81 tests, SQLite in-memory |
| CI/CD | GitHub Actions | Full suite on every push to `main` |

---

## 📁 Project Structure

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

## ⚙️ Setup & Run

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

Edit `.env`:

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

API live at `http://localhost:8000`
Swagger docs at `http://localhost:8000/docs`

---

## 🔌 API Endpoints

### Authentication

| Method | Endpoint | Auth | Rate Limit | Description |
|--------|----------|------|------------|-------------|
| POST | `/api/v1/auth/register` | No | 5/min | Register with email + password |
| POST | `/api/v1/auth/login` | No | 5/min | Login, receive JWT token |

### URLs

| Method | Endpoint | Auth | Rate Limit | Description |
|--------|----------|------|------------|-------------|
| POST | `/api/v1/urls/shorten` | Optional | 10/min | Create short URL (supports `webhook_url`, `password`) |
| POST | `/api/v1/urls/bulk-shorten` | Optional | 3/min | Shorten many URLs from an uploaded CSV |
| GET | `/api/v1/urls/` | Required | — | List your URLs (paginated) |
| GET | `/api/v1/urls/{id}/analytics` | Required | — | Click stats for a URL |
| DELETE | `/api/v1/urls/{id}` | Required | — | Soft delete a URL |
| GET | `/api/v1/urls/{short_code}/qr` | No | — | PNG QR code for the short URL |

### Core

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/{short_code}` | No (or `?password=`) | Redirect to original URL |
| GET | `/health` | No | Health check |

---

## 📋 Example Requests

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

## 🧪 Running Tests

Tests use SQLite — no PostgreSQL needed, and the real Upstash cache is
force-disabled for the whole suite regardless of what's in your local
`.env`, so tests never depend on or interfere with live infrastructure:

```bash
# Full suite (81 tests)
pytest -v
```

**Test results:**

```
tests/test_base62.py             14 passed
tests/test_auth.py                8 passed
tests/test_urls.py               32 passed
tests/test_redirect.py           18 passed
tests/test_cache.py               8 passed
tests/test_cache_integration.py   4 passed
=================== 81 passed ===================
```

CI runs the full suite on every push via `.github/workflows/tests.yml`.

---

## 🧠 Design Decisions

### Base62 Encoding — No Collisions by Design

Instead of random strings, the auto-incremented database ID is encoded to Base62
(0-9, a-z, A-Z). Guaranteed unique, URL-safe, decodable back to ID.

### Cache-Aside Redirect Lookup (Upstash Redis)

`get_url_by_code()` checks Redis first, falls back to Postgres on a miss, and
populates the cache with a 1-hour TTL. Upstash's **REST** API is used specifically
because it needs no persistent TCP connection — Render's free tier sleeps on
inactivity, and a normal Redis client's connection wouldn't survive that reliably.
The cache is **fail-open**: any Upstash error (timeout, outage, bad config) falls
back to a plain DB read rather than breaking the redirect.

A click **refreshes** the cached entry in place (new `click_count`) rather than
deleting it — an earlier version deleted on every click, which looked safer but
meant every subsequent click on a popular link forced a fresh DB read, defeating
the point of caching. Refreshing keeps popular links warm while staying correct
for `max_clicks` enforcement.

### Postgres Retry-Queue for Webhooks (not Celery)

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
User B gets 403/404 attempting to touch it by ID.

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

### SQLite for Tests — PostgreSQL for Production

Fresh DB per test, runs in CI with no external dependency. Timezone-aware
datetime handling ensures compatibility across both.

---

## 🏗️ Trade-offs & Limitations

| Decision | Trade-off | Status |
|----------|-----------|--------|
| Upstash free tier | 10,000 commands/day cap | Fine at current scale |
| BackgroundTasks for click logging (not webhooks) | Click *analytics* events can be lost if the task fails; webhooks are queue-backed and don't share this risk | Acceptable — analytics isn't safety-critical |
| Single PostgreSQL | Single point of failure | Deferred — not needed at current scale |
| No distributed cache invalidation across regions | N/A — single Upstash instance, single region | Not an issue at current traffic |
| API keys for external developers | Not built (Phase 2) | Diminishing portfolio value vs. JWT+rate-limiting already shown |

---

## 🔗 Related Projects

| Project | Description |
|---------|--------------|
| [FastAPI Task Manager v4](https://github.com/sgr111/fastapi-task-manager-v4) | CDC audit logs, JSONB, refresh tokens, pagination |
| [GitHub API Pytest Framework](https://github.com/sgr111/github-api-pytest-framework) | 112 assertions, 3-stage CI/CD, Newman, Allure |
| [Activity Tracker API](https://github.com/sgr111/activity-tracker-api) | Gemini AI search, httpx enrichment, CDC via DB triggers |

---

## 👤 Author

**Sourabh Sagar** — Backend Developer + QA Automation Engineer

- GitHub: [@sgr111](https://github.com/sgr111)
- Email: sgrsourabh111@gmail.com
- Location: Lucknow, Uttar Pradesh

---

## 📝 License

MIT
