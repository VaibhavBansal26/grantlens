from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
# Limits are set per endpoint with @limiter.limit; storage comes from RATELIMIT_STORAGE_URI (Redis in production).
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
