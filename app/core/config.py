from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./url_shortener.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENVIRONMENT: str = "development"
    BASE_URL: str = "http://localhost:8000"

    # Upstash Redis (REST-based — no persistent TCP connection, safe across
    # Render free-tier sleep/wake cycles). Left blank by default so caching
    # is automatically disabled (fails open to DB-only) in tests/local dev
    # unless a real .env supplies these.
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""
    CACHE_TTL_SECONDS: int = 3600

    class Config:
        env_file = ".env"


settings = Settings()