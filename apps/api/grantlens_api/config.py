import os

from .mail import MemoryMailer


class Config:
    # AI answers: OPENAI_API_KEY (and optionally OPENAI_MODEL) are read from the environment.
    LLM_BACKEND = os.environ.get("LLM_BACKEND", "openai")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL")
    # Email: "file" (dev, writes .eml files) or "smtp" (needs SMTP_* set). Nothing is sent by default.
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "file")
    MAIL_FROM = os.environ.get("MAIL_FROM", "GrantLens <alerts@localhost>")
    MAIL_OUTBOX = os.environ.get("MAIL_OUTBOX", "outbox")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:3000").rstrip("/")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://grantlens:grantlens@localhost:5432/grantlens"
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Flask rejects bigger request bodies with 413
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class TestConfig(Config):
    TESTING = True
    MAIL_BACKEND = "memory"
    LLM_BACKEND = "fake"
    LLM_FAKE = None  # each test installs its own
    MAIL_MEMORY = MemoryMailer()
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
