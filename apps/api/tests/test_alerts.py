from datetime import UTC, date, datetime, timedelta

import pytest

from grantlens_api import alerts, create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.mail import MemoryMailer
from grantlens_api.models import DeadlineReminder, Opportunity, SavedSearch, User
from grantlens_api.sources.base import NormalizedOpportunity as N

PW = "correct horse battery"
NOW = datetime(2030, 6, 1, 12, tzinfo=UTC)
URL = "http://app.test"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    app.config["MAIL_MEMORY"] = MemoryMailer()
    with app.app_context():
        db.create_all()
        yield app


def make_user(app, email="a@example.com"):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c, User.query.filter_by(email=email).one()


def add_opp(ext, title, first_seen, **kw):
    upsert([N("s", ext, title, abstract=kw.pop("abstract", title), status="posted", **kw)])
    o = Opportunity.query.filter_by(external_id=ext).one()
    o.first_seen_at = first_seen
    db.session.commit()
    return o


def save_search(client, alerts_on=True, q="imaging"):
    sid = client.post("/saved-searches", json={"name": "Imaging <b>", "params": {"q": q, "mode": "bm25"}}).get_json()["id"]
    if alerts_on:
        assert client.patch(f"/saved-searches/{sid}", json={"alerts": True}).status_code == 200
    return db.session.get(SavedSearch, sid)


def run(app, **kw):
    mailer = app.config["MAIL_MEMORY"]
    stats, _ = alerts.send_alerts(mailer, URL, now=NOW, **kw)
    return stats, mailer.sent


def test_nothing_sent_without_opt_in(app):
    c, _ = make_user(app)
    save_search(c, alerts_on=False)
    add_opp("1", "Cancer imaging AI", NOW)
    stats, sent = run(app)
    assert stats.users == 0 and sent == []


def test_enabling_alerts_skips_the_backlog_then_sends_only_new(app):
    c, _ = make_user(app)
    add_opp("old", "Old imaging grant", NOW - timedelta(days=30))
    saved = save_search(c)
    saved.last_alerted_at = NOW  # what enabling alerts records (the real clock differs from NOW)
    db.session.commit()
    assert run(app)[1] == []  # the old grant is backlog, not news
    saved.last_alerted_at = NOW - timedelta(hours=1)
    db.session.commit()
    add_opp("new", "Fresh imaging grant", NOW - timedelta(minutes=5))
    stats, sent = run(app)
    assert stats.sent == 1 and "Fresh imaging grant" in sent[0].text
    assert "Old imaging grant" not in sent[0].text
    assert run(app)[0].sent == 0 and len(sent) == 1  # cursor advanced: no repeat


def test_failed_send_is_retried_not_lost(app):
    c, _ = make_user(app)
    saved = save_search(c)
    saved.last_alerted_at = NOW - timedelta(hours=1)
    db.session.commit()
    add_opp("new", "Fresh imaging grant", NOW)

    class Down:
        def send(self, mail):
            raise OSError("smtp down")

    stats, _ = alerts.send_alerts(Down(), URL, now=NOW)
    assert stats.failed == 1 and stats.sent == 0
    stats, sent = run(app)
    assert stats.sent == 1 and "Fresh imaging grant" in sent[0].text


def test_dry_run_records_nothing(app):
    c, _ = make_user(app)
    saved = save_search(c)
    saved.last_alerted_at = NOW - timedelta(hours=1)
    db.session.commit()
    add_opp("new", "Fresh imaging grant", NOW)
    stats, sent = run(app, dry_run=True)
    assert sent == [] and stats.sent == 0
    assert run(app)[0].sent == 1  # still unsent after the dry run


def test_deadline_reminders_once_per_threshold(app):
    c, user = make_user(app)
    assert c.patch("/auth/preferences", json={"reminders": True}).get_json() == {"reminders": True}
    soon = add_opp("1", "Closing in five", NOW, close_date=date(2030, 6, 6))
    far = add_opp("2", "Far away", NOW, close_date=date(2030, 8, 1))
    gone = add_opp("3", "Already closed", NOW, close_date=date(2030, 5, 20))
    for o in (soon, far, gone):
        assert c.put(f"/watchlist/{o.id}").status_code == 204
    stats, sent = run(app)
    assert stats.sent == 1
    assert "Closing in five" in sent[0].text and "Far away" not in sent[0].text
    assert "Already closed" not in sent[0].text
    assert run(app)[0].sent == 0  # same threshold: not repeated
    last_day = alerts.build_digest(user, NOW + timedelta(days=4))  # now 1 day left
    assert [t for _, _, t in last_day.reminders] == [1]  # a second, final reminder
    assert DeadlineReminder.query.count() == 1


def test_isolation_between_users(app):
    a, _ = make_user(app)
    b, _ = make_user(app, "b@example.com")
    saved = save_search(a)
    saved.last_alerted_at = NOW - timedelta(hours=1)
    db.session.commit()
    add_opp("new", "Fresh imaging grant", NOW)
    _, sent = run(app)
    assert [m.to for m in sent] == ["a@example.com"]
    assert b.get("/saved-searches").get_json()["saved"] == []


def test_email_content_is_escaped_and_unsubscribable(app):
    c, user = make_user(app)
    saved = save_search(c)
    saved.last_alerted_at = NOW - timedelta(hours=1)
    db.session.commit()
    add_opp("x", "Imaging <script>alert(1)</script> R&D", NOW)
    _, sent = run(app)
    mail = sent[0]
    assert "<script>" not in mail.html  # tags are stripped from titles
    assert "R&amp;D" in mail.html  # remaining text is escaped
    assert "Imaging &lt;b&gt;" in mail.html  # so is the user-chosen search name
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    token = mail.headers["List-Unsubscribe"].split("token=")[1].rstrip(">")
    anon = app.test_client()
    assert anon.post("/alerts/unsubscribe?token=garbage").status_code == 400
    assert anon.post(f"/alerts/unsubscribe?token={token}").status_code == 200
    assert db.session.get(SavedSearch, saved.id).alerts is False
    assert db.session.get(User, user.id).reminders is False
    assert run(app)[1] == [mail]  # nothing further is sent


def test_preference_validation(app):
    c, _ = make_user(app)
    sid = save_search(c, alerts_on=False).id
    assert c.patch(f"/saved-searches/{sid}", json={"alerts": "yes"}).status_code == 400
    assert c.patch("/auth/preferences", json={"reminders": 1}).status_code == 400
    assert app.test_client().patch("/auth/preferences", json={"reminders": True}).status_code == 401


def test_long_list_unsubscribe_header_is_not_encoded():
    import email

    from grantlens_api.mail import Mail, _message

    url = "<http://example.test/api/alerts/unsubscribe?token=" + "x" * 90 + ">"
    mail = Mail("a@example.com", "s", "t", "<p>t</p>", {"List-Unsubscribe": url})
    raw = bytes(_message(mail, "GrantLens <alerts@localhost>"))
    assert b"=?utf-8?" not in raw.split(b"\n\n")[0].lower()
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    assert parsed["List-Unsubscribe"] == url
