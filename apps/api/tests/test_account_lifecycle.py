import io
import re

import pymupdf
import pytest

from grantlens_api import accounts, create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.mail import MemoryMailer
from grantlens_api.models import (
    DeadlineReminder,
    DocChunk,
    Document,
    LlmUsage,
    Opportunity,
    Review,
    SavedSearch,
    User,
    WatchedOpportunity,
)
from grantlens_api.retrieval import embedder
from grantlens_api.sources.base import NormalizedOpportunity as N

PW = "correct horse battery"
NEW_PW = "another long passphrase"


@pytest.fixture
def app(monkeypatch):
    app = create_app(TestConfig)
    app.config["MAIL_MEMORY"] = MemoryMailer()
    monkeypatch.setattr(embedder, "embed_documents", lambda ts: [[1.0, 0.0] for _ in ts])
    with app.app_context():
        db.create_all()
        yield app


def register(app, email="a@example.com"):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c


def token_from_last_email(app) -> str:
    mail = app.config["MAIL_MEMORY"].sent[-1]
    return re.search(r"token=([\w.\-]+)", mail.text).group(1)


# ---- password reset -----------------------------------------------------------------------

def test_forgot_answers_identically_and_only_mails_real_accounts(app):
    register(app)
    app.config["MAIL_MEMORY"].sent.clear()  # the confirmation email sent at registration
    c = app.test_client()
    known = c.post("/auth/forgot", json={"email": "A@Example.com"})
    unknown = c.post("/auth/forgot", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.get_json() == unknown.get_json() == {"ok": True}
    sent = app.config["MAIL_MEMORY"].sent
    assert [m.to for m in sent] == ["a@example.com"]
    assert "within an hour" in sent[0].text and "/reset-password?token=" in sent[0].html


def test_a_mail_failure_is_invisible_to_the_caller(app):
    register(app)

    class Down:
        def send(self, mail):
            raise OSError("smtp down")

    app.config["MAIL_BACKEND"], app.config["MAIL_MEMORY"] = "memory", Down()
    assert app.test_client().post("/auth/forgot", json={"email": "a@example.com"}).status_code == 202


def test_reset_changes_the_password_and_the_link_works_once(app):
    register(app)
    c = app.test_client()
    c.post("/auth/forgot", json={"email": "a@example.com"})
    token = token_from_last_email(app)
    assert c.post("/auth/reset", json={"token": token, "password": NEW_PW}).status_code == 200
    assert c.post("/auth/login", json={"email": "a@example.com", "password": PW}).status_code == 401
    assert c.post("/auth/login", json={"email": "a@example.com", "password": NEW_PW}).status_code == 200
    again = c.post("/auth/reset", json={"token": token, "password": "yet another phrase"})
    assert again.status_code == 400  # the link was bound to the old password, so it is spent
    assert c.post("/auth/login", json={"email": "a@example.com", "password": NEW_PW}).status_code == 200


def test_reset_rejects_bad_tokens_and_weak_passwords(app):
    register(app)
    user = User.query.one()
    token = accounts.reset_token(user)
    c = app.test_client()
    assert c.post("/auth/reset", json={"token": "garbage", "password": NEW_PW}).status_code == 400
    assert c.post("/auth/reset", json={"token": token[:-3] + "xyz", "password": NEW_PW}).status_code == 400
    assert c.post("/auth/reset", json={"password": NEW_PW}).status_code == 400
    assert c.post("/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    assert accounts.user_from_reset_token(token, max_age=-1) is None  # expired
    assert accounts.user_from_reset_token(token) is not None  # and the weak-password attempt did not spend it


def test_a_token_from_one_use_of_the_secret_does_not_work_with_another_salt(app):
    from itsdangerous import URLSafeTimedSerializer

    register(app)
    forged = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="something-else").dumps([1, "x" * 16])
    assert accounts.user_from_reset_token(forged) is None


def test_reset_signs_out_every_existing_session(app):
    laptop = register(app)
    phone = app.test_client()
    phone.post("/auth/login", json={"email": "a@example.com", "password": PW})
    assert laptop.get("/auth/me").get_json()["user"] and phone.get("/auth/me").get_json()["user"]
    token = accounts.reset_token(User.query.one())
    assert app.test_client().post("/auth/reset", json={"token": token, "password": NEW_PW}).status_code == 200
    assert laptop.get("/auth/me").get_json() == {"user": None} and phone.get("/auth/me").get_json() == {"user": None}
    assert laptop.get("/saved-searches").status_code == 401  # and the API refuses the old cookie


# ---- deleting an account ------------------------------------------------------------------

def test_delete_needs_the_password_and_a_session(app):
    c = register(app)
    assert app.test_client().delete("/auth/account", json={"password": PW}).status_code == 401
    assert c.delete("/auth/account", json={"password": "wrong password!!"}).status_code == 403
    assert c.delete("/auth/account", json={}).status_code == 403
    assert User.query.count() == 1


def make_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 780), "Funding study. " * 20, fontsize=11)
    return doc.tobytes()


def test_delete_removes_the_account_and_every_trace_of_its_data(app):
    upsert([N("s", "1", "A grant", status="posted")])
    keep = register(app, "keeper@example.com")
    c = register(app)
    opp = Opportunity.query.one()
    c.put(f"/watchlist/{opp.id}")
    c.post("/saved-searches", json={"name": "s", "params": {"q": "grant"}})
    assert c.post("/documents", data={"file": (io.BytesIO(make_pdf()), "p.pdf")},
                  content_type="multipart/form-data").status_code == 201
    uid = User.query.filter_by(email="a@example.com").one().id
    db.session.add_all([Review(user_id=uid, topic="t", result={"papers": []}), LlmUsage(user_id=uid, day=db.func.current_date(), count=3),
                        DeadlineReminder(user_id=uid, opportunity_id=opp.id, days=7)])
    keeper_id = User.query.filter_by(email="keeper@example.com").one().id
    keep.put(f"/watchlist/{opp.id}")
    db.session.add(Review(user_id=keeper_id, topic="mine", result={"papers": []}))
    db.session.commit()
    assert DocChunk.query.count() > 0

    assert c.delete("/auth/account", json={"password": PW}).status_code == 204
    assert c.get("/auth/me").get_json() == {"user": None}
    assert User.query.filter_by(email="a@example.com").count() == 0
    for model in (Document, SavedSearch, LlmUsage, DeadlineReminder):
        assert model.query.filter_by(user_id=uid).count() == 0
    assert DocChunk.query.count() == 0  # the deleted user's document chunks went with their document
    assert WatchedOpportunity.query.filter_by(user_id=uid).count() == 0
    assert Opportunity.query.count() == 1  # the shared grant data is not touched
    assert WatchedOpportunity.query.filter_by(user_id=keeper_id).count() == 1  # nor is anyone else's data
    assert Review.query.filter_by(user_id=keeper_id).count() == 1 and Review.query.filter_by(user_id=uid).count() == 0
    assert c.delete("/auth/account", json={"password": PW}).status_code == 401  # already gone


# ---- email verification -------------------------------------------------------------------

def link_token(mail):
    return re.search(r"token=([\w.\-]+)", mail.text).group(1)


def test_register_sends_a_confirmation_link_and_following_it_verifies(app):
    c = register(app)
    assert c.get("/auth/me").get_json()["user"]["email_verified"] is False
    sent = app.config["MAIL_MEMORY"].sent
    assert [m.to for m in sent] == ["a@example.com"] and "/verify-email?token=" in sent[0].html
    anon = app.test_client()  # opened on another device: no login needed
    assert anon.post("/auth/verify", json={"token": link_token(sent[0])}).get_json() == {"ok": True, "email": "a@example.com"}
    assert c.get("/auth/me").get_json()["user"]["email_verified"] is True
    assert anon.post("/auth/verify", json={"token": link_token(sent[0])}).status_code == 200  # harmless to repeat


def test_bad_expired_or_stale_confirmation_links_are_refused(app):
    register(app)
    c = app.test_client()
    assert c.post("/auth/verify", json={"token": "garbage"}).status_code == 400
    assert c.post("/auth/verify", json={}).status_code == 400
    user = User.query.one()
    token = accounts.verify_token(user)
    assert accounts.user_from_verify_token(token, max_age=-1) is None  # expired
    user.email = "new@example.com"  # the address changed after the link was sent
    db.session.commit()
    assert c.post("/auth/verify", json={"token": token}).status_code == 400
    assert User.query.one().email_verified is False


def test_resend_needs_login_and_stops_once_verified(app):
    assert app.test_client().post("/auth/resend-verification").status_code == 401
    c = register(app)
    sent = app.config["MAIL_MEMORY"].sent
    assert c.post("/auth/resend-verification").status_code == 202 and len(sent) == 2
    c.post("/auth/verify", json={"token": link_token(sent[1])})
    assert c.post("/auth/resend-verification").get_json() == {"ok": True, "already_verified": True} and len(sent) == 2


def test_alerts_and_reminders_need_a_verified_address(app):
    c = register(app)
    assert c.patch("/auth/preferences", json={"reminders": True}).status_code == 403
    sid = c.post("/saved-searches", json={"name": "x", "params": {"q": "imaging"}}).get_json()["id"]
    assert c.patch(f"/saved-searches/{sid}", json={"alerts": True}).status_code == 403
    assert c.patch(f"/saved-searches/{sid}", json={"alerts": False}).status_code == 200  # turning off is always allowed
    User.query.one().email_verified = True
    db.session.commit()
    assert c.patch("/auth/preferences", json={"reminders": True}).get_json() == {"reminders": True}
    assert c.patch(f"/saved-searches/{sid}", json={"alerts": True}).status_code == 200


def test_unverified_users_with_alerts_already_on_get_no_mail(app):
    from grantlens_api import alerts as alerts_mod

    register(app)
    user = User.query.one()
    user.reminders = True  # e.g. switched on before verification existed
    db.session.commit()
    stats, mails = alerts_mod.send_alerts(app.config["MAIL_MEMORY"], "http://app.test", dry_run=True)
    assert stats.users == 0 and mails == []
