import re
from datetime import date

import pytest

from grantlens_api import create_app, ics
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.models import Opportunity
from grantlens_api.sources.base import NormalizedOpportunity as N


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        upsert([
            N("s", "1", "Cancer imaging AI", abstract="tumor imaging", agency="NIH",
              status="posted", close_date=date(2030, 3, 5)),
            N("s", "2", "Rural health access", abstract="health", agency="HRSA",
              status="posted", close_date=date(2030, 3, 20)),
            N("s", "3", "Old cancer program", abstract="cancer", agency="NIH",
              status="archived", close_date=date(2030, 3, 6)),
            N("s", "4", "Rolling grant", agency="NIH", status="posted", close_date=None),
            N("s", "5", "Later cancer call", abstract="cancer", agency="NIH",
              status="posted", close_date=date(2030, 6, 1)),
        ])
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def titles(res):
    return [d["title"] for d in res.get_json()["deadlines"]]


def test_window_and_default_status(client):
    res = client.get("/deadlines?start=2030-03-01&end=2030-03-31")
    assert titles(res) == ["Cancer imaging AI", "Rural health access"]  # ordered, posted only
    assert titles(client.get("/deadlines?start=2030-03-01&end=2030-03-31&status=archived")) == [
        "Old cancer program"
    ]


def test_agency_filter(client):
    res = client.get("/deadlines?start=2030-03-01&end=2030-12-31&agency=nih")
    assert titles(res) == ["Cancer imaging AI", "Later cancer call"]


def test_bad_windows(client):
    assert client.get("/deadlines?start=nope").status_code == 400
    assert client.get("/deadlines?start=2030-03-10&end=2030-03-01").status_code == 400
    assert client.get("/deadlines?start=2030-01-01&end=2032-01-01").status_code == 400


def test_ics_feed(client):
    res = client.get("/deadlines.ics?start=2030-03-01&end=2030-03-31")
    body = res.data.decode()
    assert res.mimetype == "text/calendar"
    assert body.count("BEGIN:VEVENT") == 2 and body.startswith("BEGIN:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20300305" in body
    assert re.search(r"DTSTAMP:\d{8}T\d{6}Z", body)


def test_ics_lines_are_folded_and_escaped(app):
    with app.app_context():
        o = Opportunity.query.filter_by(external_id="1").one()
        o.title = "A, B; " + "long " * 40
        body = ics.calendar([o])
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    unfolded = body.replace("\r\n ", "")
    assert r"A\, B\; long" in unfolded


def test_saved_scope_needs_login_and_uses_own_searches(app):
    anon = app.test_client()
    assert anon.get("/deadlines?scope=saved").status_code == 401
    a, b = app.test_client(), app.test_client()
    for c, email in ((a, "a@example.com"), (b, "b@example.com")):
        c.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    a.post("/saved-searches", json={"name": "imaging", "params": {"q": "tumor imaging", "mode": "bm25",
                                                                    "agency": "NIH"}})
    mine = a.get("/deadlines?scope=saved&start=2030-01-01&end=2030-12-31")
    assert "Cancer imaging AI" in titles(mine) and "Rural health access" not in titles(mine)
    assert titles(b.get("/deadlines?scope=saved&start=2030-01-01&end=2030-12-31")) == []


def test_titles_are_cleaned_everywhere(app):
    upsert([N("s", "9", "DoW Parkinson&rsquo;s &amp; Spinal", agency="DoD", status="posted",
              close_date=date(2030, 4, 2))])
    c = app.test_client()
    d = c.get("/deadlines?start=2030-04-01&end=2030-04-30").get_json()["deadlines"][0]
    assert d["title"] == "DoW Parkinson’s & Spinal"
    opp = Opportunity.query.filter_by(external_id="9").one()
    assert c.get(f"/opportunities/{opp.id}").get_json()["title"] == "DoW Parkinson’s & Spinal"
    hit = c.get("/search?q=spinal&mode=bm25&k=1").get_json()["results"][0]
    assert hit["title"] == "DoW Parkinson’s & Spinal"
    assert "Parkinson’s & Spinal" in c.get("/deadlines.ics?start=2030-04-01&end=2030-04-30").data.decode()
