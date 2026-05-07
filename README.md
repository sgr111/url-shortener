# 🔗 Smart URL Shortener

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-red)
![Pytest](https://img.shields.io/badge/Tests-51_passed-brightgreen?logo=pytest)
![License](https://img.shields.io/badge/License-MIT-green)

A **production-grade URL shortener REST API** built with FastAPI and PostgreSQL.  
Converts long URLs to short Base62-encoded codes with expiry, click analytics, JWT auth, rate limiting, and background task logging.

> **Live Demo:** _Coming soon (Render deployment — Phase 3)_

---

## 🎯 Project Highlights

| Metric | Value |
|--------|-------|
| **Short Code Algorithm** | Base62 encoding of auto-incremented DB ID |
| **Redirect Lookup** | O(log n) — indexed `short_code` column |
| **Click Logging** | Async BackgroundTask — zero redirect latency impact |
| **Race Condition Prevention** | Atomic SQL `click_count = click_count + 1` |
| **Test Coverage** | 51 tests — 100% pass rate |
| **Test Runtime** | ~24 seconds |
| **Auth** | JWT access tokens (30 min expiry) |
| **Rate Limiting** | Per-IP via slowapi |

---

## ✨ Features

- 🔗 **URL Shortening** — Base62-encoded short codes, guaranteed unique, no collisions
- ↩️ **Instant Redirect** — HTTP 302 with indexed lookup
- ⏳ **Expiry by Date** — set `expires_at`, link returns 410 Gone after that
- 🖱️ **Expiry by Clicks** — set `max_clicks`, link dies after N clicks
- 📊 **Click Analytics** — total clicks, recent clicks, top countries per URL
- 🔐 **JWT Authentication** — register, login, protected endpoints
- 👤 **Anonymous Shortening** — no account needed for basic shortening
- 🗑️ **Soft Delete** — `is_active=False`, data + analytics preserved
- 📄 **Pagination** — `skip/limit` with `has_more` field, silent MAX_PAGE_SIZE clamping
- 🚦 **Rate Limiting** — per-IP limits via slowapi
- ✅ **Password Validation** — requires uppercase + digit
- 🏥 **Health Check** — `/health` endpoint for deployment monitoring

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Framework | FastAPI 0.111 | Async-native, auto Swagger docs, Pydantic built-in |
| ORM | SQLAlchemy 2.0 (async) | Type-safe, async queries, connection pooling |
| Database | PostgreSQL 15 (prod) / SQLite (tests) | TIMESTAMPTZ, strict constraints, ACID |
| Migrations | Alembic | Version-controlled schema changes |
| Auth | python-jose (JWT) + passlib (bcrypt) | Stateless auth, secure password hashing |
| Validation | Pydantic v2 | Runtime type checking, field validators |
| Rate Limiting | slowapi | Per-IP request throttling |
| HTTP Client | httpx | Async test client |
| Testing | pytest + pytest-asyncio | 51 tests, SQLite in-memory |

---

## 📁 Project Structure

```
url_shortener/
├── app/
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── auth.py         ← register, login
│   │   │   ├── urls.py         ← shorten, list, analytics, delete
│   │   │   └── redirect.py     ← GET /{short_code} — core feature
│   │   ├── dependencies.py     ← get_current_user, get_optional_user
│   │   └── router.py
│   ├── core/
│   │   ├── base62.py           ← Base62 encode/decode algorithm
│   │   ├── config.py           ← Settings from .env
│   │   ├── limiter.py          ← slowapi Limiter instance
│   │   └── security.py         ← JWT + bcrypt utilities
│   ├── db/
│   │   └── session.py          ← Async engine + get_db dependency
│   ├── models/
│   │   ├── url.py              ← URL + ClickEvent ORM models
│   │   └── user.py             ← User ORM model
│   ├── schemas/
│   │   ├── analytics.py        ← AnalyticsOut, ClickEventOut
│   │   ├── url.py              ← URLCreate, URLOut, URLListOut
│   │   └── user.py             ← UserRegister, UserLogin, TokenResponse
│   ├── services/
│   │   ├── url_service.py      ← All URL business logic
│   │   └── user_service.py     ← User business logic
│   └── main.py                 ← App factory + lifespan
├── alembic/
│   └── versions/
│       └── 001_initial.py      ← users, urls, click_events + indexes
├── tests/
│   ├── conftest.py             ← SQLite fixtures, AsyncClient setup
│   ├── test_base62.py          ← 14 algorithm unit tests
│   ├── test_auth.py            ← 8 auth tests
│   ├── test_urls.py            ← 16 URL endpoint tests
│   └── test_redirect.py        ← 7 redirect + expiry tests
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

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | No | Register with email + password |
| POST | `/api/v1/auth/login` | No | Login, receive JWT token |

### URLs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/urls/shorten` | Optional | Create short URL |
| GET | `/api/v1/urls/` | Required | List your URLs (paginated) |
| GET | `/api/v1/urls/{id}/analytics` | Required | Click stats for a URL |
| DELETE | `/api/v1/urls/{id}` | Required | Soft delete a URL |

### Core

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/{short_code}` | No | Redirect to original URL |
| GET | `/health` | No | Health check |

---

## 📋 Example Requests

### Shorten a URL

```bash
curl -X POST http://localhost:8000/api/v1/urls/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://github.com/sgr111"}'
```

```json
{
  "id": 1,
  "short_code": "1",
  "short_url": "http://localhost:8000/1",
  "original_url": "https://github.com/sgr111/",
  "click_count": 0,
  "is_active": true,
  "expires_at": null,
  "max_clicks": null,
  "created_at": "2026-05-06T10:00:00Z"
}
```

### Shorten with expiry + click limit

```bash
curl -X POST http://localhost:8000/api/v1/urls/shorten \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://github.com/sgr111",
    "expires_at": "2026-12-31T00:00:00Z",
    "max_clicks": 100
  }'
```

### View analytics

```bash
curl http://localhost:8000/api/v1/urls/1/analytics \
  -H "Authorization: Bearer YOUR_TOKEN"
```

```json
{
  "url_id": 1,
  "short_code": "1",
  "total_clicks": 42,
  "recent_clicks": [...],
  "top_countries": [
    {"country": "IN", "count": 30},
    {"country": "US", "count": 12}
  ]
}
```

---

## 🧪 Running Tests

Tests use SQLite — no PostgreSQL needed:

```bash
# Full suite (51 tests)
pytest -v

# Specific file
pytest tests/test_redirect.py -v
pytest tests/test_base62.py -v

# By marker
pytest -m unit -v
```

**Test results:**

```
tests/test_base62.py    .............. 14 passed
tests/test_auth.py      ........       8 passed
tests/test_urls.py      ................  16 passed
tests/test_redirect.py  .......        7 passed
======================== 51 passed in 24.76s ========================
```

---

## 🧠 Design Decisions

### Base62 Encoding — No Collisions by Design

Instead of random strings (which need collision detection), I encode the auto-incremented database ID to Base62 (0-9, a-z, A-Z):

```python
encode(1)   → "1"     # 1 char
encode(62)  → "10"    # 2 chars  
encode(125) → "21"
encode(3_500_000_000) → 6 chars
```

**Benefits:** Guaranteed unique, URL-safe characters only, decodable back to ID, predictable length growth.

### Indexed Short Code — O(log n) Redirect Lookup

The redirect endpoint is the hottest path in the system. `short_code` has a unique B-tree index — lookup is O(log n) regardless of table size. With 1 million URLs that's ~20 comparisons instead of 1 million.

### Atomic Click Counting — No Race Conditions

```sql
UPDATE urls SET click_count = click_count + 1 WHERE id = X
```

Single atomic operation. 1000 concurrent clicks all increment correctly. No read-modify-write race condition.

### Background Task Click Logging — Zero Redirect Latency Impact

Click events are logged **after** the redirect response is sent. Users are redirected instantly. Database write happens in the background. Keeps p99 redirect latency low under load.

### Designed for Redis Caching

`get_url_by_code()` in `url_service.py` is the single lookup point for redirects. A comment marks the exact line where Redis cache check would be inserted — adding caching requires changing one function only.

### Soft Delete — Data Preserved

`DELETE /urls/{id}` sets `is_active=False`. Click history is preserved. Short code is not reassigned. Returns 410 Gone on redirect. Recoverable if deleted by mistake.

### SQLite for Tests — PostgreSQL for Production

Tests use SQLite (no install needed, fresh DB per test, runs in CI). Production uses PostgreSQL. The timezone-aware datetime handling (`expires_at.tzinfo` check) ensures compatibility across both.

---

## 🏗️ Trade-offs & Limitations

| Decision | Trade-off | Future Improvement |
|----------|-----------|-------------------|
| No Redis | DB hit on every redirect | Add Redis in `get_url_by_code()` — one function change |
| BackgroundTasks | Click events lost if task fails | Move to Celery + Redis queue |
| Single PostgreSQL | Single point of failure | Add read replica for redirect lookups |
| Per-IP rate limiting | Office networks share one limit | Switch to per-user limiting with JWT user ID |
| No distributed cache | Can't scale horizontally yet | Redis + multiple app instances |

---

## 🔗 Related Projects

| Project | Description |
|---------|-------------|
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
