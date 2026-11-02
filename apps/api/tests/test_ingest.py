import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.models import Opportunity
from grantlens_api.sources.grants_gov import normalize, parse_date

HIT = {
    "id": "1", "number": "RFA-1", "title": " Cancer Informatics ", "agency": "NIH",
    "openDate": "05/21/2026", "closeDate": "", "oppStatus": "posted",
}
DETAIL = {
    "synopsis": {
        "synopsisDesc": "Fund tools.", "awardFloor": "50000", "awardCeiling": "300000",
        "applicantTypes": [{"id": "02", "description": "City governments"}],
        "fundingActivityCategories": [{"id": "HL", "description": "Health"}],
        "fundingInstruments": [{"id": "CA", "description": "Cooperative Agreement"}],
    }
}


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app


def test_parse_date():
    assert str(parse_date("05/21/2026")) == "2026-05-21"
    assert parse_date("") is None


def test_normalize_fields():
    n = normalize(HIT, DETAIL)
    assert n.title == "Cancer Informatics"
    assert (n.amount_min, n.amount_max) == (50000, 300000)
    assert n.eligibility == ["City governments"] and n.close_date is None


def test_normalize_without_detail():
    assert normalize(HIT, None).abstract is None


def test_upsert_is_idempotent_and_detects_change(app):
    item = normalize(HIT, DETAIL)
    assert upsert([item]).inserted == 1
    assert upsert([normalize(HIT, DETAIL)]).unchanged == 1
    changed = normalize({**HIT, "title": "New title"}, DETAIL)
    assert upsert([changed]).updated == 1
    assert Opportunity.query.count() == 1
    assert Opportunity.query.one().title == "New title"


def test_list_order_does_not_change_hash():
    a = {"synopsis": {"applicantTypes": [{"description": "A"}, {"description": "B"}]}}
    b = {"synopsis": {"applicantTypes": [{"description": "B"}, {"description": "A"}]}}
    from grantlens_api.ingest import content_hash

    assert content_hash(normalize(HIT, a)) == content_hash(normalize(HIT, b))
