from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import jobs, reviews, usage
from ..extensions import db, limiter
from ..llm import LLMNotConfigured, get_llm
from ..models import Job, Review
from .auth import login_required

bp = Blueprint("reviews", __name__, url_prefix="/reviews")
MAX_REVIEWS = 20


def _mine(review_id: int) -> Review | None:
    return Review.query.filter_by(id=review_id, user_id=g.user.id).first()


def _full(r: Review) -> dict:
    return {"id": r.id, "topic": r.topic, "created_at": r.created_at.isoformat(), **r.result}


@bp.get("")
@login_required
def list_reviews():
    rows = Review.query.filter_by(user_id=g.user.id).order_by(Review.created_at.desc())
    recent = datetime.now(UTC) - timedelta(minutes=15)
    pending = Job.query.filter(Job.user_id == g.user.id, Job.kind == "review").filter(
        Job.status.in_(jobs.ACTIVE) | ((Job.status == "failed") & (Job.finished_at > recent))).order_by(Job.id)
    return jsonify(reviews=[
        {"id": r.id, "topic": r.topic, "created_at": r.created_at.isoformat(), "papers": len(r.result["papers"])}
        for r in rows
    ], pending=[_job_view(j) for j in pending])


@bp.post("")
@limiter.limit("10/hour")
@login_required
def create():
    """Body: {"topic": "...", "year_from": 2019, "max_papers": 20}."""
    body = request.get_json(silent=True) or {}
    topic = str(body.get("topic") or "").strip()
    if not 3 <= len(topic) <= 300:
        return jsonify(error="give a topic of 3 to 300 characters"), 400
    year_from, max_papers = body.get("year_from"), body.get("max_papers", 20)
    if year_from is not None and not (isinstance(year_from, int) and 1900 <= year_from <= date.today().year):
        return jsonify(error="year_from must be a year, like 2019"), 400
    if not isinstance(max_papers, int) or not 5 <= max_papers <= reviews.MAX_PAPERS:
        return jsonify(error=f"max_papers must be between 5 and {reviews.MAX_PAPERS}"), 400
    try:
        get_llm(current_app.config)  # fail now, not in the background, if AI answers are not configured
    except LLMNotConfigured as e:
        return jsonify(error=str(e)), 503
    if Review.query.filter_by(user_id=g.user.id).count() + jobs.active_count(g.user.id) >= MAX_REVIEWS:
        return jsonify(error=f"limit of {MAX_REVIEWS} saved reviews reached; delete one first"), 409
    if jobs.active_count(g.user.id) >= jobs.MAX_ACTIVE_PER_USER:
        return jsonify(error="two reviews are already being built; wait for one to finish"), 409
    if not usage.consume(g.user.id):
        return jsonify(error="you have reached today's limit of AI requests; try again tomorrow"), 429
    job = jobs.enqueue(g.user.id, "review", {"topic": topic, "year_from": year_from, "max_papers": max_papers})
    jobs.start(job)
    db.session.refresh(job)
    return jsonify(job=_job_view(job)), 202


def _job_view(j: Job) -> dict:
    return {"id": j.id, "topic": j.params.get("topic"), "status": j.status, "review_id": j.result_id, "error": j.error}


@bp.get("/jobs/<int:job_id>")
@login_required
def job_status(job_id: int):
    """Poll this after POST /reviews until status is done (review_id is set) or failed (error says why)."""
    job = Job.query.filter_by(id=job_id, user_id=g.user.id).first()
    return (jsonify(job=_job_view(job)), 200) if job else (jsonify(error="not found"), 404)


@bp.get("/<int:review_id>")
@login_required
def get(review_id: int):
    row = _mine(review_id)
    return (jsonify(_full(row)), 200) if row else (jsonify(error="not found"), 404)


def _download(row: Review, text: str, mimetype: str, ext: str) -> Response:
    return Response(text, mimetype=mimetype,
                    headers={"Content-Disposition": f'attachment; filename="review-{row.id}.{ext}"'})


@bp.get("/<int:review_id>.bib")
@login_required
def bibtex(review_id: int):
    row = _mine(review_id)
    if row is None:
        return jsonify(error="not found"), 404
    return _download(row, reviews.to_bibtex(row.result["papers"]), "application/x-bibtex", "bib")


@bp.get("/<int:review_id>.md")
@login_required
def markdown(review_id: int):
    row = _mine(review_id)
    if row is None:
        return jsonify(error="not found"), 404
    return _download(row, reviews.to_markdown(row.topic, row.result), "text/markdown", "md")


@bp.delete("/<int:review_id>")
@login_required
def delete(review_id: int):
    row = _mine(review_id)
    if row is None:
        return jsonify(error="not found"), 404
    db.session.delete(row)
    db.session.commit()
    return "", 204
