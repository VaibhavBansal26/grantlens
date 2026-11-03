import json
import logging

import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db, limiter
from grantlens_api.hardening import JsonFormatter

PW = "correct horse battery"


class RateLimited(TestConfig):
    RATELIMIT_ENABLED = True


class BehindProxy(RateLimited):
    TRUSTED_PROXY_HOPS = 1


class WithCors(TestConfig):
    CORS_ORIGINS = "https://app.example.com, https://admin.example.com"


def make(config=TestConfig):
    app = create_app(config)
    if app.config["RATELIMIT_ENABLED"]:
        limiter.reset()  # counters live in the shared extension, so start every test from zero
    with app.app_context():
        db.create_all()
    return app


# ---- headers, request ids, error shape ----------------------------------------------------

def test_every_response_has_security_headers_and_a_request_id():
    res = make().test_client().get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert res.headers["Cache-Control"] == "no-store"
    assert len(res.headers["X-Request-ID"]) == 16


def test_a_sane_incoming_request_id_is_kept_and_a_hostile_one_replaced():
    c = make().test_client()
    assert c.get("/health", headers={"X-Request-ID": "abcdef123456"}).headers["X-Request-ID"] == "abcdef123456"
    for bad in ("short", "has spaces and \\n newline injected", "x" * 200, "<script>alert(1)</script>"):
        got = c.get("/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert got != bad and len(got) == 16


def test_errors_are_json_never_html_pages():
    c = make().test_client()
    nf = c.get("/nope")
    assert nf.status_code == 404 and nf.is_json and "error" in nf.get_json()
    assert c.delete("/search").status_code == 405 and c.delete("/search").is_json
    assert c.post("/auth/login", data="x", content_type="text/plain").status_code in (400, 401)


def test_unexpected_exceptions_return_json_without_a_traceback():
    app = make()

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail: db password is hunter2")

    res = app.test_client().get("/boom", headers={"X-Request-ID": "reqid1234567"})
    body = res.get_json()
    assert res.status_code == 500 and body["error"] == "something went wrong on our side"
    assert body["request_id"] == "reqid1234567"
    assert "hunter2" not in res.get_data(as_text=True) and "Traceback" not in res.get_data(as_text=True)


def test_log_lines_are_json_with_structured_fields():
    record = logging.LogRecord("grantlens", logging.INFO, __file__, 1, "request", None, None)
    record.fields = {"request_id": "abc", "status": 200, "path": "/search"}
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "request" and out["request_id"] == "abc" and out["status"] == 200 and out["level"] == "INFO"


# ---- CORS, secret key, proxy ---------------------------------------------------------------

def test_cors_is_off_by_default_and_opt_in_per_origin():
    plain = make().test_client().get("/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in plain.headers
    c = make(WithCors).test_client()
    ok = c.get("/health", headers={"Origin": "https://admin.example.com"})
    assert ok.headers["Access-Control-Allow-Origin"] == "https://admin.example.com"
    assert "Access-Control-Allow-Origin" not in c.get("/health", headers={"Origin": "https://evil.example"}).headers
    assert "Access-Control-Allow-Credentials" not in ok.headers


@pytest.mark.parametrize("key", ["dev", "change-me", "CHANGEME", "short-but-not-a-placeholder", ""])
def test_production_refuses_weak_secret_keys(key):
    class Prod(TestConfig):
        SESSION_COOKIE_SECURE = True
        SECRET_KEY = key

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(Prod)


def test_production_accepts_a_long_random_secret():
    class Prod(TestConfig):
        SESSION_COOKIE_SECURE = True
        SECRET_KEY = "x" * 40

    assert create_app(Prod) is not None


# ---- rate limits --------------------------------------------------------------------------

def login(c, email="a@example.com", ip="10.0.0.1", pw="wrong password!!"):
    return c.post("/auth/login", json={"email": email, "password": pw}, environ_overrides={"REMOTE_ADDR": ip})


def test_login_is_limited_per_address():
    c = make(RateLimited).test_client()
    assert [login(c).status_code for _ in range(10)] == [401] * 10
    blocked = login(c)
    assert blocked.status_code == 429 and blocked.is_json and "Retry-After" in blocked.headers
    assert login(c, ip="10.0.0.2").status_code == 401  # another address is unaffected


def test_login_is_limited_per_account_across_many_addresses():
    c = make(RateLimited).test_client()
    codes = [login(c, email="victim@example.com", ip=f"10.1.{i // 250}.{i % 250 + 1}").status_code for i in range(25)]
    assert codes[:20] == [401] * 20 and set(codes[20:]) == {429}  # a botnet guessing one account is stopped
    assert login(c, email="other@example.com", ip="10.9.9.9").status_code == 401  # other accounts are not


def test_registration_and_expensive_public_endpoints_are_limited():
    c = make(RateLimited).test_client()
    codes = [c.post("/auth/register", json={"email": f"u{i}@example.com", "password": PW}).status_code for i in range(7)]
    assert codes[:5] == [201] * 5 and codes[5:] == [429, 429]
    m = make(RateLimited).test_client()
    assert {m.post("/match", json={}).status_code for _ in range(20)} == {400}
    assert m.post("/match", json={}).status_code == 429


def test_limits_follow_the_forwarded_client_address_only_behind_a_trusted_proxy():
    c = make(BehindProxy).test_client()
    xff = lambda ip: {"X-Forwarded-For": ip}
    for _ in range(10):
        c.post("/auth/login", json={"email": "a@example.com", "password": "x" * 12}, headers=xff("203.0.113.5"))
    assert c.post("/auth/login", json={"email": "b@example.com", "password": "x" * 12}, headers=xff("203.0.113.5")).status_code == 429
    assert c.post("/auth/login", json={"email": "c@example.com", "password": "x" * 12}, headers=xff("203.0.113.6")).status_code == 401
    direct = make(RateLimited).test_client()  # no trusted proxy: a forged header must not buy a fresh allowance
    for _ in range(10):
        direct.post("/auth/login", json={"email": "a@example.com", "password": "x" * 12}, headers=xff("203.0.113.7"))
    assert direct.post("/auth/login", json={"email": "d@example.com", "password": "x" * 12}, headers=xff("203.0.113.8")).status_code == 429
