"""Cross-cutting production concerns: proxy trust, CORS, request ids, logs, headers, error responses."""
import json
import logging
import time
import uuid

from flask import Flask, g, jsonify, request, session
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

PLACEHOLDER_SECRETS = {"dev", "change-me", "changeme", "secret", "password"}
log = logging.getLogger("grantlens")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                 "msg": record.getMessage()}
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def _setup_logging(app: Flask) -> None:
    if app.config.get("TESTING") or log.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def scrub_event(event: dict, hint=None) -> dict:
    """Keep what is needed to debug (route, status, stack) and drop what the privacy notes promise is never kept:
    query strings, bodies, cookies, headers, IP addresses and any user details."""
    req = event.get("request") or {}
    for key in ("query_string", "data", "cookies", "headers", "env"):
        req.pop(key, None)
    event["request"] = req
    event.pop("user", None)
    return event


def _setup_sentry(app: Flask) -> None:
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed (uv sync --extra observability)")
        return
    sentry_sdk.init(dsn=dsn, send_default_pii=False, before_send=scrub_event,
                    traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0))


def check_secret(app: Flask) -> None:
    """In production the session key signs login cookies and reset links, so it must not be guessable."""
    if not app.config["SESSION_COOKIE_SECURE"]:
        return
    key = app.config["SECRET_KEY"]
    if key.lower() in PLACEHOLDER_SECRETS or len(key) < 32:
        raise RuntimeError("SECRET_KEY must be a random value of at least 32 characters in production")


def harden(app: Flask) -> None:
    check_secret(app)
    _setup_logging(app)
    _setup_sentry(app)
    if hops := app.config["TRUSTED_PROXY_HOPS"]:
        # Only valid when the API is reachable solely through that many proxies; otherwise the
        # client could forge X-Forwarded-For and dodge the rate limits.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)
    if origins := [o.strip() for o in app.config["CORS_ORIGINS"].split(",") if o.strip()]:
        CORS(app, origins=origins, supports_credentials=False)  # the web app is same-origin; this is opt-in

    @app.before_request
    def start() -> None:
        g.started = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if 8 <= len(incoming) <= 64 and incoming.isalnum() else uuid.uuid4().hex[:16]

    @app.after_request
    def finish(response):
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")  # API answers are per-user or fast-changing
        if request.endpoint != "health.health":  # health checks every few seconds would drown the log
            log.info("request", extra={"fields": {
                "request_id": g.get("request_id"), "method": request.method, "path": request.path,
                "status": response.status_code, "ms": round((time.perf_counter() - g.get("started", 0)) * 1000),
                "user": session.get("uid"),
            }})
        return response

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        return jsonify(error=e.description or e.name), e.code

    @app.errorhandler(Exception)
    def unexpected(e: Exception):
        log.exception("unhandled error", extra={"fields": {"request_id": g.get("request_id"), "path": request.path}})
        return jsonify(error="something went wrong on our side", request_id=g.get("request_id")), 500
