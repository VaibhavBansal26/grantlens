"""Background jobs: slow work (building a literature review takes 15 to 60 seconds) runs outside the web request.

The request validates, takes one AI request from the user's daily allowance, and queues a row in `job`. Something then
runs it, depending on JOBS_MODE: a `flask worker` process (production: keeps the slow work and its memory away from the
workers that serve search), a thread in the web process (development), or the request itself (tests). The browser polls
GET /reviews/jobs/<id>. The queue is the database, so there is nothing else to run.

A job that fails gives the allowance back. A job left "running" by a crashed worker is failed and refunded by `reap`.
"""
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from flask import Flask, current_app
from sqlalchemy import update

from . import reviews, usage
from .extensions import db
from .llm import LLMError, get_llm
from .models import Job, Review

log = logging.getLogger("grantlens")
MAX_ACTIVE_PER_USER = 2
STALE_AFTER = timedelta(minutes=15)  # a review that has run this long is not coming back
ACTIVE = ("queued", "running")


class JobFailed(Exception):
    """The job cannot produce a result; the message is shown to the user."""


def enqueue(user_id: int, kind: str, params: dict) -> Job:
    job = Job(user_id=user_id, kind=kind, params=params, status="queued")
    db.session.add(job)
    db.session.commit()
    return job


def active_count(user_id: int) -> int:
    return Job.query.filter(Job.user_id == user_id, Job.status.in_(ACTIVE)).count()


def claim(job_id: int | None = None) -> Job | None:
    """Atomically move one queued job to running. Safe with several workers: only one UPDATE can win a given row."""
    query = Job.query.filter_by(status="queued")
    if job_id is not None:
        query = query.filter_by(id=job_id)
    for row in query.order_by(Job.id).limit(5).all():
        won = db.session.execute(
            update(Job).where(Job.id == row.id, Job.status == "queued")
            .values(status="running", started_at=datetime.now(UTC))
        ).rowcount
        db.session.commit()
        if won:
            return db.session.get(Job, row.id)
    return None


def _build_review(job: Job) -> int:
    p = job.params
    try:
        built = reviews.build(p["topic"], get_llm(current_app.config), p.get("year_from"), p.get("max_papers", 20))
    except LLMError as e:
        raise JobFailed(str(e)) from e
    if not built.papers:
        if not built.literature_available:
            raise JobFailed("the literature service could not be reached; try again later")
        raise JobFailed("no papers with abstracts were found for that topic; try broader words")
    row = Review(user_id=job.user_id, topic=p["topic"], result=asdict(built))
    db.session.add(row)
    db.session.commit()
    return row.id


HANDLERS: dict[str, Callable[[Job], int]] = {"review": _build_review}


def execute(job: Job) -> None:
    """Run a claimed job to completion. Never raises: the outcome is recorded on the row."""
    try:
        result_id = HANDLERS[job.kind](job)
        job.status, job.result_id, job.error = "done", result_id, None
    except JobFailed as e:
        db.session.rollback()
        job.status, job.error = "failed", str(e)[:300]
        usage.refund(job.user_id)
    except Exception:  # a bug must not leave the job "running" forever or the user's allowance spent
        log.exception("job crashed", extra={"fields": {"job": job.id, "kind": job.kind}})
        db.session.rollback()
        job.status, job.error = "failed", "something went wrong; try again"
        usage.refund(job.user_id)
    job.finished_at = datetime.now(UTC)
    db.session.commit()


def reap(now: datetime | None = None) -> int:
    """Fail (and refund) jobs a crashed worker left running."""
    now = now or datetime.now(UTC)
    stuck = Job.query.filter(Job.status == "running", Job.started_at < now - STALE_AFTER).all()
    for job in stuck:
        job.status, job.error, job.finished_at = "failed", "this took too long and was stopped; try again", now
        usage.refund(job.user_id)
    db.session.commit()
    return len(stuck)


def start(job: Job) -> None:
    """Get a queued job running according to JOBS_MODE (in "worker" mode the worker process picks it up)."""
    mode = current_app.config["JOBS_MODE"]
    if mode == "sync":
        execute(claim(job.id) or job)
    elif mode == "thread":
        app, job_id = current_app._get_current_object(), job.id
        threading.Thread(target=_run_in_thread, args=(app, job_id), daemon=True).start()


def _run_in_thread(app: Flask, job_id: int) -> None:
    with app.app_context():
        if job := claim(job_id):
            execute(job)
        db.session.remove()


def work(app: Flask, once: bool = False, poll: float = 2.0) -> int:
    """The `flask worker` loop: claim and run jobs until stopped (or, with `once`, until the queue is empty)."""
    done = 0
    while True:
        with app.app_context():
            reap()
            job = claim()
            if job:
                execute(job)
                done += 1
            db.session.remove()
        if job:
            continue
        if once:
            return done
        time.sleep(poll)
