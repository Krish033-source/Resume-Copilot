"""Central configuration. Everything is driven by environment variables."""
import os
from datetime import timedelta


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///resume_copilot_dev.db"
    # Render/Heroku style URLs -> SQLAlchemy + psycopg3 driver
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    ENV = os.getenv("APP_ENV", "development")
    DEBUG = ENV == "development"
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY", "")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or SECRET_KEY

    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Cookie based JWT (httpOnly) + CSRF double submit
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_SECURE = (ENV == "production") and os.getenv("COOKIE_SECURE", "1") == "1"
    JWT_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_REFRESH_COOKIE_PATH = "/api/auth/refresh"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN"

    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB uploads

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # AI (Groq)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_FALLBACK_MODELS = [m.strip() for m in os.getenv(
        "GROQ_FALLBACK_MODELS", "llama-3.3-70b-versatile,openai/gpt-oss-20b").split(",") if m.strip()]
    GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "40"))

    # Job / research sources
    ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
    ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "in")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")  # used for OpenAlex polite pool + User-Agent
    SOURCE_TTL_HOURS = {"remotive": 8, "arbeitnow": 4, "remoteok": 6, "jobicy": 6, "themuse": 8}
    SOURCE_DEFAULT_TTL_HOURS = 6
    AUTO_REFRESH_SOURCES = os.getenv("AUTO_REFRESH_SOURCES", "1") == "1"

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")


class TestConfig(Config):
    TESTING = True
    ENV = "testing"
    SECRET_KEY = "test-secret-key-test-secret-key-123456"
    JWT_SECRET_KEY = SECRET_KEY
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    AUTO_REFRESH_SOURCES = False
    GROQ_API_KEY = ""
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
