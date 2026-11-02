import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://grantlens:grantlens@localhost:5432/grantlens"
    )
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
