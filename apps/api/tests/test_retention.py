from datetime import UTC, datetime, timedelta

import pytest

from grantlens_api import create_app, retention
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.models import (
    DeadlineReminder,
    DocChunk,
    Document,
    LlmUsage,
    Opportunity,
    Review,
    SavedSearch,
    User,
)

NOW = datetime(2030, 6, 1, 12, tzinfo=UTC)


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app


def seed():
    u = User(email="a@example.com", password_hash="x")
    o = Opportunity(source="s", external_id="1", title="t", abstract="a", content_hash="h")
    db.session.add_all([u, o])
    db.session.flush()
    for name, age in (("old", 100), ("fresh", 10)):
        d = Document(user_id=u.id, title=name, page_count=1, created_at=NOW - timedelta(days=age))
        db.session.add(d)
        db.session.flush()
        db.session.add(DocChunk(document_id=d.id, idx=0, page=1, text=name))
    db.session.add_all([
        LlmUsage(user_id=u.id, day=(NOW - timedelta(days=40)).date(), count=3),
        LlmUsage(user_id=u.id, day=NOW.date(), count=1),
        DeadlineReminder(user_id=u.id, opportunity_id=o.id, days=7, sent_at=NOW - timedelta(days=200)),
        DeadlineReminder(user_id=u.id, opportunity_id=o.id, days=1, sent_at=NOW - timedelta(days=2)),
        SavedSearch(user_id=u.id, name="keep", params={"q": "x"}, created_at=NOW - timedelta(days=900)),
        Review(user_id=u.id, topic="keep", result={}, created_at=NOW - timedelta(days=900)),
    ])
    db.session.commit()


def test_purge_deletes_only_what_is_past_its_limit_and_never_curated_data(app):
    seed()
    out = retention.purge(90, 30, 180, now=NOW)
    assert (out.documents, out.usage_rows, out.reminder_rows) == (1, 1, 1)
    assert [d.title for d in Document.query.all()] == ["fresh"]
    assert [c.text for c in DocChunk.query.all()] == ["fresh"]  # the old document's passages went with it
    assert LlmUsage.query.one().day == NOW.date() and DeadlineReminder.query.one().days == 1
    assert SavedSearch.query.count() == 1 and Review.query.count() == 1  # never expired automatically


def test_dry_run_counts_but_deletes_nothing_and_zero_disables_a_cleanup(app):
    seed()
    out = retention.purge(90, 30, 180, now=NOW, dry_run=True)
    assert (out.documents, out.usage_rows, out.reminder_rows) == (1, 1, 1)
    assert Document.query.count() == 2 and LlmUsage.query.count() == 2 and DeadlineReminder.query.count() == 2
    off = retention.purge(0, 0, 0, now=NOW)
    assert (off.documents, off.usage_rows, off.reminder_rows) == (0, 0, 0) and Document.query.count() == 2


def test_cli_reports_and_documents_show_when_they_expire(app):
    seed()
    result = app.test_cli_runner().invoke(args=["retention", "--dry-run"])
    assert "(dry run)" in result.output and "documents=" in result.output
    c = app.test_client()
    c.post("/auth/register", json={"email": "b@example.com", "password": "correct horse battery"})
    assert c.get("/documents").get_json() == {"documents": []}
    d = Document(user_id=User.query.filter_by(email="b@example.com").one().id, title="t", page_count=1)
    db.session.add(d)
    db.session.commit()
    doc = c.get("/documents").get_json()["documents"][0]
    created, expires = (datetime.fromisoformat(doc[k]) for k in ("created_at", "expires_at"))
    assert expires.replace(tzinfo=None) - created.replace(tzinfo=None) == timedelta(days=90)
