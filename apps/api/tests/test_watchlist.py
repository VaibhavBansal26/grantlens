from datetime import date, timedelta

import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.models import Opportunity
from grantlens_api.sources.base import NormalizedOpportunity as N

PW = "correct horse battery"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        soon = date.today() + timedelta(days=5)
        upsert([
            N("s", "1", "Later grant", status="posted", close_date=date.today() + timedelta(days=60)),
            N("s", "2", "Sooner grant", status="posted", close_date=soon),
            N("s", "3", "Rolling grant", status="posted", close_date=None),
            N("s", "4", "Unwatched grant", status="posted", close_date=soon),
        ])
        yield app


def login(app, email="a@example.com"):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c


def opp_id(ext):
    return Opportunity.query.filter_by(external_id=ext).one().id


def test_requires_login(app):
    c = app.test_client()
    assert c.get("/watchlist").status_code == 401
    assert c.put("/watchlist/1").status_code == 401
    assert c.delete("/watchlist/1").status_code == 401


def test_add_list_remove_and_ordering(app):
    c = login(app)
    for ext in ("1", "3", "2"):
        assert c.put(f"/watchlist/{opp_id(ext)}").status_code == 204
    assert c.put(f"/watchlist/{opp_id('2')}").status_code == 204  # idempotent
    items = c.get("/watchlist").get_json()["items"]
    assert [i["title"] for i in items] == ["Sooner grant", "Later grant", "Rolling grant"]
    assert items[0]["days_left"] == 5 and items[2]["days_left"] is None
    assert c.delete(f"/watchlist/{opp_id('2')}").status_code == 204
    assert c.delete(f"/watchlist/{opp_id('2')}").status_code == 204  # removing twice is fine
    assert [i["title"] for i in c.get("/watchlist").get_json()["items"]] == ["Later grant", "Rolling grant"]


def test_unknown_opportunity(app):
    assert login(app).put("/watchlist/99999").status_code == 404


def test_watchlists_are_private(app):
    a, b = login(app), login(app, "b@example.com")
    a.put(f"/watchlist/{opp_id('1')}")
    assert b.get("/watchlist").get_json()["items"] == []
    b.delete(f"/watchlist/{opp_id('1')}")  # must not remove A's entry
    assert len(a.get("/watchlist").get_json()["items"]) == 1


def test_calendar_scope_watchlist(app):
    c = login(app)
    assert app.test_client().get("/deadlines?scope=watchlist").status_code == 401
    c.put(f"/watchlist/{opp_id('2')}")
    c.put(f"/watchlist/{opp_id('3')}")  # no close date: never on a calendar
    start, end = date.today(), date.today() + timedelta(days=30)
    res = c.get(f"/deadlines?scope=watchlist&start={start}&end={end}")
    assert [d["title"] for d in res.get_json()["deadlines"]] == ["Sooner grant"]
