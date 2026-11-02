from datetime import UTC, datetime, timedelta

import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.models import Opportunity, SavedSearch
from grantlens_api.sources.base import NormalizedOpportunity as N

CREDS = {"email": "Ann@Example.com", "password": "correct horse battery"}


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        upsert([N("s", "1", "Cancer imaging AI", abstract="tumor imaging", status="posted")])
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, **over):
    return client.post("/auth/register", json={**CREDS, **over})


def test_register_login_logout_me(client):
    assert client.get("/auth/me").get_json() == {"user": None}
    res = register(client)
    assert res.status_code == 201 and res.get_json()["email"] == "ann@example.com"
    assert client.get("/auth/me").get_json()["user"]["email"] == "ann@example.com"
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").get_json() == {"user": None}
    assert client.post("/auth/login", json=CREDS).status_code == 200
    assert client.post("/auth/login", json={**CREDS, "password": "wrong password!!"}).status_code == 401
    assert client.post("/auth/login", json={**CREDS, "email": "none@example.com"}).status_code == 401


def test_register_validation(client):
    assert register(client, email="not-an-email").status_code == 400
    assert register(client, password="short").status_code == 400
    assert register(client).status_code == 201
    assert register(client, email="ANN@example.com").status_code == 409


def test_password_is_hashed(client, app):
    register(client)
    from grantlens_api.models import User

    assert CREDS["password"] not in User.query.one().password_hash


def test_saved_search_requires_login(client):
    assert client.get("/saved-searches").status_code == 401
    assert client.post("/saved-searches", json={"name": "x", "params": {"q": "a"}}).status_code == 401


def test_saved_search_crud_and_validation(client):
    register(client)
    bad = client.post("/saved-searches", json={"name": "x", "params": {"q": "a", "mode": "zzz"}})
    assert bad.status_code == 400
    assert client.post("/saved-searches", json={"name": "", "params": {"q": "a"}}).status_code == 400
    ok = client.post("/saved-searches", json={
        "name": "AI imaging", "params": {"q": "imaging", "status": ["posted"], "evil": "x", "agency": ""},
    })
    assert ok.status_code == 201
    saved = ok.get_json()
    assert saved["params"] == {"q": ["imaging"], "status": ["posted"]}
    assert len(client.get("/saved-searches").get_json()["saved"]) == 1
    assert client.delete(f"/saved-searches/{saved['id']}").status_code == 204
    assert client.get("/saved-searches").get_json()["saved"] == []


def test_users_cannot_see_each_others_searches(app):
    a, b = app.test_client(), app.test_client()
    register(a)
    register(b, email="bob@example.com")
    sid = a.post("/saved-searches", json={"name": "mine", "params": {"q": "imaging"}}).get_json()["id"]
    assert b.get("/saved-searches").get_json()["saved"] == []
    assert b.delete(f"/saved-searches/{sid}").status_code == 404
    assert b.get(f"/saved-searches/{sid}/new").status_code == 404
    assert b.post(f"/saved-searches/{sid}/seen").status_code == 404


def test_new_matches_since_last_seen(client, app):
    register(client)
    sid = client.post("/saved-searches", json={"name": "s", "params": {"q": "imaging", "mode": "bm25"}}).get_json()["id"]
    assert client.get(f"/saved-searches/{sid}/new").get_json()["count"] == 0
    saved = db.session.get(SavedSearch, sid)
    saved.last_seen_at = datetime.now(UTC) - timedelta(days=1)  # user last looked yesterday
    db.session.commit()
    assert client.get(f"/saved-searches/{sid}/new").get_json()["count"] == 1
    Opportunity.query.update({"first_seen_at": datetime.now(UTC) - timedelta(days=3)})
    db.session.commit()
    assert client.get(f"/saved-searches/{sid}/new").get_json()["count"] == 0
    assert client.post(f"/saved-searches/{sid}/seen").status_code == 204
