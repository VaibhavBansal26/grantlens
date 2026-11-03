"""Loading grants from the sources, on demand or on a schedule, outside the web request.

An admin clicks "Load now" (or sets a schedule); that queues a `sync_run` row. The `flask worker` process claims it, pulls
the records, upserts them, and embeds the new ones so they are searchable by meaning as well as by keyword. Only one load
runs at a time, so the sources are not hit in parallel. The queue is the database, like jobs.py.
"""
import logging
import threading
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta

from flask import Flask, current_app
from sqlalchemy import update

from .extensions import db
from .ingest import SyncStats, upsert
from .models import Opportunity, SyncRun, SyncSchedule
from .sources.grants_gov import GrantsGovSource
from .sources.nih_reporter import NihReporterSource
from .sources.nsf import NsfSource

log = logging.getLogger("grantlens")
SOURCES = {"grants_gov": GrantsGovSource, "nih_reporter": NihReporterSource, "nsf": NsfSource}
KEYWORD_ARG = {"grants_gov": "keyword", "nih_reporter": "text", "nsf": "keyword"}
GRANTS_GOV_STATUSES = ("posted", "forecasted", "closed", "archived")
STALE_AFTER = timedelta(hours=3)  # a load that has run this long is not coming back
ACTIVE = ("queued", "running")
MAX_SCHEDULES = 10
MAX_LIMIT = 200_000
EMBED_BATCH = 64


class BadParams(ValueError):
    """The request's parameters are not valid; the message is shown to the admin."""


def clean_params(source: str, raw: dict) -> dict:
    """Validate what the admin sent; returns only the keys the source understands."""
    if source not in SOURCES:
        raise BadParams("unknown source")
    out: dict = {}
    if (query := str(raw.get("query") or "").strip()):
        if len(query) > 200:
            raise BadParams("keyword is too long")
        out["query"] = query
    for key, low, high in (("limit", 1, MAX_LIMIT), ("days", 1, 3650)):
        if raw.get(key) in (None, ""):
            continue
        try:
            value = int(raw[key])
        except (TypeError, ValueError):
            raise BadParams(f"{key} must be a whole number") from None
        if not low <= value <= high:
            raise BadParams(f"{key} must be between {low} and {high}")
        out[key] = value
    if source == "grants_gov":
        out.pop("days", None)
        statuses = raw.get("statuses")
        if statuses:
            parts = [str(s) for s in (statuses if isinstance(statuses, list) else str(statuses).split("|"))]
            if not parts or any(s not in GRANTS_GOV_STATUSES for s in parts):
                raise BadParams(f"statuses must be some of: {', '.join(GRANTS_GOV_STATUSES)}")
            out["statuses"] = "|".join(dict.fromkeys(parts))
    else:
        out.pop("statuses", None)
    return out


def build_source(source: str, params: dict):
    kwargs: dict = {}
    if params.get("query"):
        kwargs[KEYWORD_ARG[source]] = params["query"]
    if source == "grants_gov":
        if params.get("statuses"):
            kwargs["statuses"] = params["statuses"]
    elif params.get("days"):
        kwargs["since"] = date.today() - timedelta(days=params["days"])
    return SOURCES[source](**kwargs)


def active_run() -> SyncRun | None:
    return SyncRun.query.filter(SyncRun.status.in_(ACTIVE)).order_by(SyncRun.id).first()


def enqueue(source: str, params: dict, trigger: str, user_id: int | None = None,
            schedule_id: int | None = None) -> SyncRun:
    run = SyncRun(source=source, params=params, trigger=trigger, user_id=user_id, schedule_id=schedule_id)
    db.session.add(run)
    db.session.commit()
    return run


def claim(run_id: int | None = None) -> SyncRun | None:
    """Atomically move the oldest queued load to running, unless one is already running."""
    if SyncRun.query.filter_by(status="running").first():
        return None
    query = SyncRun.query.filter_by(status="queued")
    if run_id is not None:
        query = query.filter_by(id=run_id)
    for row in query.order_by(SyncRun.id).limit(3).all():
        won = db.session.execute(
            update(SyncRun).where(SyncRun.id == row.id, SyncRun.status == "queued")
            .values(status="running", started_at=datetime.now(UTC))
        ).rowcount
        db.session.commit()
        if won:
            return db.session.get(SyncRun, row.id)
    return None


def embed_missing(batch: int = EMBED_BATCH, on_progress=None) -> int:
    """Embed opportunities that have no embedding yet; returns how many were done."""
    from .retrieval.embedder import embed_documents
    from .retrieval.text import doc_text

    done = 0
    while True:
        rows = Opportunity.query.filter(Opportunity.embedding.is_(None)).limit(batch).all()
        if not rows:
            return done
        vecs = embed_documents([doc_text(r.title, r.abstract) for r in rows])
        for row, vec in zip(rows, vecs, strict=True):
            row.embedding = vec
        db.session.commit()
        done += len(rows)
        if on_progress:
            on_progress(done)


def _counted(items: Iterable, run: SyncRun) -> Iterator:
    """Pass records through, keeping run.fetched current (saved with the next batch commit)."""
    for run.fetched, item in enumerate(items, 1):
        yield item


def execute(run: SyncRun) -> None:
    """Run a claimed load to completion. Never raises: the outcome is recorded on the row."""
    try:
        source = build_source(run.source, run.params)
        stats: SyncStats = upsert(_counted(source.fetch(limit=run.params.get("limit")), run))
        run.inserted, run.updated, run.unchanged = stats.inserted, stats.updated, stats.unchanged
        db.session.commit()
        run.embedded = embed_missing(on_progress=lambda n: (setattr(run, "embedded", n), db.session.commit()))
        run.status, run.error = "done", None
    except Exception as e:
        log.exception("sync failed", extra={"fields": {"run": run.id, "source": run.source}})
        db.session.rollback()
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e!s}"[:300] or "failed"
    run.finished_at = datetime.now(UTC)
    db.session.commit()


def reap(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    stuck = SyncRun.query.filter(SyncRun.status == "running", SyncRun.started_at < now - STALE_AFTER).all()
    for run in stuck:
        run.status, run.error, run.finished_at = "failed", "this took too long and was stopped", now
    db.session.commit()
    return len(stuck)


def fire_due(now: datetime | None = None) -> int:
    """Queue a load for each enabled schedule whose interval has passed. Safe with several workers: the UPDATE that
    moves `last_run_at` forward can succeed for only one of them."""
    now = now or datetime.now(UTC)
    started = 0
    for sch in SyncSchedule.query.filter_by(enabled=True).order_by(SyncSchedule.id).all():
        last = sch.last_run_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is not None and now < last + timedelta(hours=sch.interval_hours):
            continue
        if SyncRun.query.filter(SyncRun.schedule_id == sch.id, SyncRun.status.in_(ACTIVE)).first():
            continue
        unchanged = (SyncSchedule.last_run_at.is_(None) if sch.last_run_at is None
                     else SyncSchedule.last_run_at == sch.last_run_at)
        won = db.session.execute(
            update(SyncSchedule).where(SyncSchedule.id == sch.id, unchanged).values(last_run_at=now)
        ).rowcount
        db.session.commit()
        if won:
            enqueue(sch.source, sch.params, "schedule", schedule_id=sch.id)
            started += 1
    return started


def start(run: SyncRun) -> None:
    """Get a queued load running according to JOBS_MODE (in "worker" mode the worker process picks it up)."""
    mode = current_app.config["JOBS_MODE"]
    if mode == "sync":
        execute(claim(run.id) or run)
    elif mode == "thread":
        app, run_id = current_app._get_current_object(), run.id
        threading.Thread(target=_run_in_thread, args=(app, run_id), daemon=True).start()


def _run_in_thread(app: Flask, run_id: int) -> None:
    with app.app_context():
        if run := claim(run_id):
            execute(run)
        db.session.remove()


def tick() -> bool:
    """One pass of the worker loop: start due schedules, run one queued load. True if a load ran."""
    reap()
    fire_due()
    run = claim()
    if run:
        execute(run)
    return run is not None
