from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints.redirect import router as redirect_router
from app.api.v1.router import router as api_router
from app.core.limiter import limiter
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (Alembic handles this in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Smart URL Shortener",
    description="Production-grade URL shortener with Base62 encoding, click analytics, expiry, and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routes — health first, then API, then wildcard redirect last
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "url-shortener"}

app.include_router(api_router)
app.include_router(redirect_router)