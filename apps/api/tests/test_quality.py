from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.quality import report
from grantlens_api.sources.base import NormalizedOpportunity as N


def test_report_counts_nulls_and_dupes():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        upsert([N("s", "1", "Same", abstract="x"), N("s", "2", "same")])
        out = "\n".join(report())
    assert "opportunity/s: 2 rows" in out
    assert "abstract       null  50.0%" in out
    assert "duplicate titles: 1" in out
