from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from grantlens_api import create_app, syncer
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.models import Opportunity, SyncRun, SyncSchedule, User
from grantlens_api.sources.base import NormalizedOpportunity as N

PW = "correct horse battery"


class FakeSource:
    created: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeSource.created.append(kwargs)

    def fetch(self, limit=None):
        items = [N("fake", str(i), f"Fake grant {i}", status="posted") for i in range(5)]
        return iter(items[:limit] if limit else items)


class BrokenSource(FakeSource):
    def fetch(self, limit=None):
        raise RuntimeError("upstream down")


@pytest.fixture
def app(monkeypatch):
    app = create_app(TestConfig)
    FakeSource.created = []
    monkeypatch.setitem(syncer.SOURCES, "grants_gov", FakeSource)
    monkeypatch.setattr(syncer, "embed_missing", lambda *a, **k: 5)
    with app.app_context():
        db.create_all()
        yield app


def login(app, email="a@example.com", admin=False):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    if admin:
        User.query.filter_by(email=email).one().is_admin = True
        db.session.commit()
    return c


def test_needs_admin(app):
    anon = app.test_client()
    assert anon.get("/admin/sync").status_code == 401
    c = login(app)
    assert c.get("/admin/sync").status_code == 403
    assert c.post("/admin/sync/run", json={"source": "grants_gov"}).status_code == 403
    assert c.post("/admin/sync/schedules", json={"source": "grants_gov", "interval_hours": 24}).status_code == 403
    assert c.get("/auth/me").get_json()["user"]["is_admin"] is False


def test_run_now_loads_grants_and_records_result(app):
    c = login(app, admin=True)
    assert c.get("/auth/me").get_json()["user"]["is_admin"] is True
    r = c.post("/admin/sync/run", json={"source": "grants_gov", "params": {"query": "cancer", "limit": 3}})
    assert r.status_code == 202
    assert FakeSource.created == [{"keyword": "cancer"}]
    run = SyncRun.query.one()
    assert (run.status, run.inserted, run.fetched, run.embedded, run.trigger) == ("done", 3, 3, 5, "manual")
    assert Opportunity.query.count() == 3
    view = c.get("/admin/sync").get_json()
    assert view["corpus"]["opportunities"] == 3
    assert view["runs"][0]["status"] == "done"
    assert view["scheduler"] is False  # TestConfig is not worker mode


def test_failed_load_is_recorded_not_raised(app, monkeypatch):
    monkeypatch.setitem(syncer.SOURCES, "grants_gov", BrokenSource)
    c = login(app, admin=True)
    assert c.post("/admin/sync/run", json={"source": "grants_gov"}).status_code == 202
    run = SyncRun.query.one()
    assert run.status == "failed" and "upstream down" in run.error


def test_one_load_at_a_time(app):
    c = login(app, admin=True)
    syncer.enqueue("grants_gov", {}, "manual")
    assert c.post("/admin/sync/run", json={"source": "grants_gov"}).status_code == 409


@pytest.mark.parametrize("body", [
    {"source": "nope"},
    {"source": "grants_gov", "params": {"limit": 0}},
    {"source": "grants_gov", "params": {"limit": "lots"}},
    {"source": "grants_gov", "params": {"statuses": "posted|bogus"}},
    {"source": "grants_gov", "params": {"query": "x" * 201}},
])
def test_bad_params_rejected(app, body):
    c = login(app, admin=True)
    assert c.post("/admin/sync/run", json=body).status_code == 400
    assert SyncRun.query.count() == 0


def test_params_are_cleaned_per_source():
    assert syncer.clean_params("nsf", {"days": 30, "statuses": "posted", "junk": 1}) == {"days": 30}
    assert syncer.clean_params("grants_gov", {"days": 30, "statuses": ["posted", "forecasted"]}) == {
        "statuses": "posted|forecasted"}


def test_schedule_crud_and_limits(app):
    c = login(app, admin=True)
    r = c.post("/admin/sync/schedules", json={"source": "grants_gov", "interval_hours": 24, "params": {"limit": 50}})
    assert r.status_code == 201
    sid = r.get_json()["schedule"]["id"]
    assert c.post("/admin/sync/schedules", json={"source": "grants_gov", "interval_hours": 0}).status_code == 400
    assert c.patch(f"/admin/sync/schedules/{sid}", json={"enabled": False, "interval_hours": 6}).get_json()[
        "schedule"] == {"id": sid, "source": "grants_gov", "params": {"limit": 50}, "interval_hours": 6,
                        "enabled": False, "last_run_at": None}
    assert c.patch("/admin/sync/schedules/999", json={}).status_code == 404
    assert c.delete(f"/admin/sync/schedules/{sid}").status_code == 204
    assert SyncSchedule.query.count() == 0
    for _ in range(syncer.MAX_SCHEDULES):
        c.post("/admin/sync/schedules", json={"source": "nsf", "interval_hours": 24})
    assert c.post("/admin/sync/schedules", json={"source": "nsf", "interval_hours": 24}).status_code == 409


def test_fire_due_respects_interval_enabled_and_active(app):
    now = datetime.now(UTC)
    due = SyncSchedule(source="grants_gov", params={}, interval_hours=24)
    recent = SyncSchedule(source="grants_gov", params={}, interval_hours=24, last_run_at=now - timedelta(hours=1))
    old = SyncSchedule(source="grants_gov", params={}, interval_hours=24, last_run_at=now - timedelta(hours=25))
    off = SyncSchedule(source="grants_gov", params={}, interval_hours=24, enabled=False)
    db.session.add_all([due, recent, old, off])
    db.session.commit()
    assert syncer.fire_due(now) == 2
    assert {r.schedule_id for r in SyncRun.query.all()} == {due.id, old.id}
    assert syncer.fire_due(now) == 0  # just fired, and the runs are still queued
    assert SyncRun.query.filter_by(trigger="schedule").count() == 2


def test_tick_runs_queued_loads_one_at_a_time(app):
    syncer.enqueue("grants_gov", {"limit": 2}, "manual")
    syncer.enqueue("grants_gov", {"limit": 2}, "manual")
    assert syncer.tick() is True
    assert sorted(r.status for r in SyncRun.query.all()) == ["done", "queued"]
    assert syncer.tick() is True
    assert syncer.tick() is False


def test_reap_fails_stuck_load(app):
    run = syncer.enqueue("grants_gov", {}, "manual")
    run.status, run.started_at = "running", datetime.now(UTC) - timedelta(hours=4)
    db.session.commit()
    assert syncer.reap() == 1
    assert db.session.get(SyncRun, run.id).status == "failed"
