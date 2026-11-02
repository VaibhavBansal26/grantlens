import itertools

import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.models import Award
from grantlens_api.sources import nih_reporter, nsf

NIH = {
    "appl_id": 1, "project_num": "5P30CA1-16", "project_title": " Cancer Imaging ",
    "abstract_text": "Summary", "agency_ic_admin": {"name": "NCI"},
    "organization": {"org_name": "STANFORD"}, "award_amount": 91918, "fiscal_year": 2024,
    "principal_investigators": [{"full_name": "Jane Doe"}],
    "terms": "<Imaging><Cancer><Imaging>", "project_start_date": "2007-06-04T00:00:00",
    "project_end_date": None, "project_detail_url": "https://reporter.nih.gov/project-details/1",
}
NSF = {
    "id": "2500001", "title": "Sensors", "abstractText": "Abs", "awardeeName": "OU",
    "fundsObligatedAmt": "125000", "startDate": "08/01/2025", "expDate": "07/31/2027",
    "piFirstName": "Ann", "piLastName": "Lee", "fundProgramName": "EPSCoR",
}


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app


def test_nih_normalize():
    a = nih_reporter.normalize(NIH)
    assert a.title == "Cancer Imaging" and a.investigators == ["Jane Doe"]
    assert a.keywords == ["Cancer", "Imaging"] and a.organization == "STANFORD"
    assert str(a.start_date) == "2007-06-04" and a.end_date is None


def test_nsf_normalize():
    a = nsf.normalize(NSF)
    assert (a.amount, a.fiscal_year) == (125000, 2025)
    assert a.investigators == ["Ann Lee"] and str(a.end_date) == "2027-07-31"
    assert a.url.endswith("AWD_ID=2500001")


def test_award_upsert_idempotent(app):
    assert upsert([nih_reporter.normalize(NIH), nsf.normalize(NSF)]).inserted == 2
    assert upsert([nih_reporter.normalize(NIH), nsf.normalize(NSF)]).unchanged == 2
    assert Award.query.count() == 2


def test_weekly_windows_cover_range_without_overlap():
    from datetime import date, timedelta

    from grantlens_api.sources.windows import windows

    wins = list(windows(date(2025, 1, 1), date(2025, 1, 20)))
    assert wins[0] == (date(2025, 1, 1), date(2025, 1, 7))
    assert wins[-1][1] == date(2025, 1, 20)
    assert all(b[0] == a[1] + timedelta(days=1) for a, b in itertools.pairwise(wins))
