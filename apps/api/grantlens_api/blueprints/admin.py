"""Admin: load grants from the sources now, or on a schedule. Admin rights come only from `flask make-admin`."""
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from .. import syncer
from ..extensions import db
from ..models import Award, Opportunity, SyncRun, SyncSchedule
from .auth import login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")
RECENT_RUNS = 15
MIN_HOURS, MAX_HOURS = 1, 24 * 30


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user.is_admin:
            return jsonify(error="admin only"), 403
        return view(*args, **kwargs)

    return wrapped


def _iso(dt):
    return dt.isoformat() if dt else None


def _run(r: SyncRun) -> dict:
    return {
        "id": r.id, "source": r.source, "params": r.params, "trigger": r.trigger, "status": r.status,
        "fetched": r.fetched, "inserted": r.inserted, "updated": r.updated, "unchanged": r.unchanged,
        "embedded": r.embedded, "error": r.error, "created_at": _iso(r.created_at),
        "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
    }


def _schedule(s: SyncSchedule) -> dict:
    return {"id": s.id, "source": s.source, "params": s.params, "interval_hours": s.interval_hours,
            "enabled": s.enabled, "last_run_at": _iso(s.last_run_at)}


def _body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _checked(body: dict) -> tuple[str, dict]:
    source = str(body.get("source", ""))
    return source, syncer.clean_params(source, body.get("params") if isinstance(body.get("params"), dict) else {})


def _hours(value) -> int:
    try:
        hours = int(value)
    except (TypeError, ValueError):
        raise syncer.BadParams("interval must be a whole number of hours") from None
    if not MIN_HOURS <= hours <= MAX_HOURS:
        raise syncer.BadParams(f"interval must be between {MIN_HOURS} and {MAX_HOURS} hours")
    return hours


@bp.errorhandler(syncer.BadParams)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.get("/sync")
@admin_required
def overview():
    runs = SyncRun.query.order_by(SyncRun.id.desc()).limit(RECENT_RUNS).all()
    schedules = SyncSchedule.query.order_by(SyncSchedule.id).all()
    return jsonify(
        runs=[_run(r) for r in runs],
        schedules=[_schedule(s) for s in schedules],
        corpus={
            "opportunities": Opportunity.query.count(),
            "awards": Award.query.count(),
            "waiting_for_embedding": Opportunity.query.filter(Opportunity.embedding.is_(None)).count(),
        },
        sources=sorted(syncer.SOURCES),
        statuses=list(syncer.GRANTS_GOV_STATUSES),
        # schedules are started by the worker process; in development there is none
        scheduler=current_app.config["JOBS_MODE"] == "worker",
    )


@bp.post("/sync/run")
@admin_required
def run_now():
    source, params = _checked(_body())
    if syncer.active_run():
        return jsonify(error="a load is already running; wait for it to finish"), 409
    run = syncer.enqueue(source, params, "manual", user_id=g.user.id)
    syncer.start(run)
    db.session.refresh(run)
    return jsonify(run=_run(run)), 202


@bp.post("/sync/schedules")
@admin_required
def add_schedule():
    body = _body()
    source, params = _checked(body)
    hours = _hours(body.get("interval_hours"))
    if SyncSchedule.query.count() >= syncer.MAX_SCHEDULES:
        return jsonify(error=f"limit of {syncer.MAX_SCHEDULES} schedules reached"), 409
    sch = SyncSchedule(source=source, params=params, interval_hours=hours)
    db.session.add(sch)
    db.session.commit()
    return jsonify(schedule=_schedule(sch)), 201


@bp.patch("/sync/schedules/<int:sid>")
@admin_required
def edit_schedule(sid: int):
    sch = db.session.get(SyncSchedule, sid)
    if sch is None:
        return jsonify(error="not found"), 404
    body = _body()
    if "enabled" in body:
        sch.enabled = bool(body["enabled"])
    if "interval_hours" in body:
        sch.interval_hours = _hours(body["interval_hours"])
    db.session.commit()
    return jsonify(schedule=_schedule(sch))


@bp.delete("/sync/schedules/<int:sid>")
@admin_required
def delete_schedule(sid: int):
    SyncSchedule.query.filter_by(id=sid).delete()
    db.session.commit()
    return "", 204
