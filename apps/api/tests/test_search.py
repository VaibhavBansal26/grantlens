from datetime import date

import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.retrieval import service
from grantlens_api.retrieval.filters import Filters
from grantlens_api.retrieval.fusion import rrf
from grantlens_api.sources.base import NormalizedOpportunity as N


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        upsert([
            N("s", "1", "Cancer imaging AI", abstract="deep learning tumor", agency="NIH",
              status="posted", close_date=date(2030, 1, 1), amount_max=500_000),
            N("s", "2", "Rural mental health", abstract="behavioral health access", agency="HRSA",
              status="posted", close_date=None, amount_max=100_000),
            N("s", "3", "Cancer drug trials", abstract="oncology clinical", agency="NIH",
              status="archived", close_date=date(2010, 1, 1), amount_max=900_000),
        ])
        yield app


def test_rrf_rewards_agreement():
    fused = rrf({"a": [1, 2, 3], "b": [3, 1, 4]})
    assert [d for d, _ in fused][:2] == [1, 3]


def test_bm25_search_and_filters(app):
    hits = service.search("cancer imaging", mode="bm25")
    assert hits[0].external_id == "1" and "bm25" in hits[0].ranks
    posted = service.search("cancer", mode="bm25", filters=Filters(status=["posted"]))
    assert posted[0].external_id == "1" and len(posted) == 2
    assert all(h.status == "posted" for h in posted)


def test_deadline_and_amount_filters(app):
    f = Filters(closes_after=date(2026, 1, 1))  # open-ended grants are kept by default
    ids = {h.external_id for h in service.search("health cancer", mode="bm25", filters=f)}
    assert "3" not in ids and "1" in ids
    strict = Filters(closes_after=date(2026, 1, 1), include_no_deadline=False)
    assert "2" not in {h.external_id for h in service.search("mental health", mode="bm25", filters=strict)}
    big = Filters(min_amount=400_000)
    assert {h.external_id for h in service.search("cancer", mode="bm25", filters=big)} == {"1", "3"}


def test_endpoint_validation(app):
    client = app.test_client()
    assert client.get("/search").status_code == 400
    assert client.get("/search?q=x&mode=bad").status_code == 400
    assert client.get("/search?q=x&closes_after=nope").status_code == 400
    res = client.get("/search?q=cancer&mode=bm25&k=2")
    assert res.status_code == 200 and res.get_json()["results"]


def test_detail_facets_and_ics(app):
    client = app.test_client()
    hit = client.get("/search?q=cancer+imaging+tumor&mode=bm25").get_json()["results"][0]
    assert hit["snippet"] and "amount_max" in hit
    d = client.get(f"/opportunities/{hit['id']}").get_json()
    assert d["title"] == "Cancer imaging AI" and d["amount_max"] == 500_000
    assert client.get("/opportunities/9999").status_code == 404
    facets = client.get("/facets").get_json()
    assert {"value": "posted", "count": 2} in facets["statuses"]
    ics = client.get(f"/opportunities/{hit['id']}.ics")
    assert ics.mimetype == "text/calendar" and b"DTSTART;VALUE=DATE:20300101" in ics.data
    open_ended = client.get("/search?q=mental&mode=bm25").get_json()["results"][0]["id"]
    assert client.get(f"/opportunities/{open_ended}.ics").status_code == 404


def test_clean_text_strips_html():
    from grantlens_api.retrieval.clean import clean_text

    out = clean_text("<p><strong>Summary:</strong>&nbsp;Early&nbsp;career &rsquo;26</p><p>Next</p>")
    assert out == "Summary: Early career ’26\n\nNext"
    assert clean_text(None) == ""
