from dataclasses import asdict
from datetime import date

from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import reviews, usage
from ..extensions import db
from ..llm import LLMError, LLMNotConfigured, get_llm
from ..models import Review
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
    return jsonify(reviews=[
        {"id": r.id, "topic": r.topic, "created_at": r.created_at.isoformat(), "papers": len(r.result["papers"])}
        for r in rows
    ])


@bp.post("")
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
        llm = get_llm(current_app.config)
    except LLMNotConfigured as e:
        return jsonify(error=str(e)), 503
    if Review.query.filter_by(user_id=g.user.id).count() >= MAX_REVIEWS:
        return jsonify(error=f"limit of {MAX_REVIEWS} saved reviews reached; delete one first"), 409
    if not usage.consume(g.user.id):
        return jsonify(error="you have reached today's limit of AI requests; try again tomorrow"), 429
    try:
        built = reviews.build(topic, llm, year_from, max_papers)
    except LLMError as e:
        usage.refund(g.user.id)
        return jsonify(error=str(e)), 502
    if not built.papers:
        usage.refund(g.user.id)
        if not built.literature_available:
            return jsonify(error="the literature service could not be reached; try again later"), 502
        return jsonify(error="no papers with abstracts were found for that topic; try broader words"), 404
    row = Review(user_id=g.user.id, topic=topic, result=asdict(built))
    db.session.add(row)
    db.session.commit()
    return jsonify(_full(row)), 201


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
