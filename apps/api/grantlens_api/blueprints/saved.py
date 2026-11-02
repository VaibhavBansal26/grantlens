from dataclasses import asdict
from datetime import UTC, datetime

from flask import Blueprint, g, jsonify, request
from werkzeug.datastructures import MultiDict

from ..extensions import db
from ..models import Opportunity, SavedSearch
from ..retrieval.service import search
from .auth import login_required
from .search import parse_search

bp = Blueprint("saved", __name__, url_prefix="/saved-searches")
MAX_PER_USER = 50
ALLOWED = {"q", "mode", "status", "agency", "closes_after", "closes_before", "min_amount", "max_amount"}


def _args(params: dict) -> MultiDict:
    return MultiDict((k, v) for k, vals in params.items() for v in vals)


def _mine(search_id: int) -> SavedSearch | None:
    return SavedSearch.query.filter_by(id=search_id, user_id=g.user.id).first()


def _view(s: SavedSearch) -> dict:
    return {"id": s.id, "name": s.name, "params": s.params, "created_at": s.created_at.isoformat()}


@bp.get("")
@login_required
def list_saved():
    rows = SavedSearch.query.filter_by(user_id=g.user.id).order_by(SavedSearch.created_at.desc())
    return jsonify(saved=[_view(s) for s in rows])


@bp.post("")
@login_required
def create():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()[:120]
    raw = body.get("params") or {}
    if not name:
        return jsonify(error="name is required"), 400
    if not isinstance(raw, dict):
        return jsonify(error="params must be an object"), 400
    params = {
        k: [str(x) for x in (v if isinstance(v, list) else [v])]
        for k, v in raw.items() if k in ALLOWED and v not in ("", None, [])
    }
    try:
        parse_search(_args(params))  # reject searches that /search would reject
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if SavedSearch.query.filter_by(user_id=g.user.id).count() >= MAX_PER_USER:
        return jsonify(error=f"limit of {MAX_PER_USER} saved searches reached"), 409
    saved = SavedSearch(user_id=g.user.id, name=name, params=params)
    db.session.add(saved)
    db.session.commit()
    return jsonify(_view(saved)), 201


@bp.delete("/<int:search_id>")
@login_required
def delete(search_id: int):
    saved = _mine(search_id)
    if saved is None:
        return jsonify(error="not found"), 404
    db.session.delete(saved)
    db.session.commit()
    return "", 204


@bp.get("/<int:search_id>/new")
@login_required
def new_matches(search_id: int):
    """Top matches first seen by the system after the user last looked at this search."""
    saved = _mine(search_id)
    if saved is None:
        return jsonify(error="not found"), 404
    req = parse_search(_args(saved.params))
    hits = search(req.query, k=50, filters=req.filters, mode=req.mode)
    since = saved.last_seen_at
    first_seen = {
        o.id: o.first_seen_at
        for o in db.session.query(Opportunity.id, Opportunity.first_seen_at).filter(
            Opportunity.id.in_([h.id for h in hits])
        )
    }

    def is_new(h) -> bool:
        seen = first_seen.get(h.id)
        return bool(seen) and seen.replace(tzinfo=seen.tzinfo or UTC) > since.replace(tzinfo=since.tzinfo or UTC)

    new = [asdict(h) for h in hits if is_new(h)]
    return jsonify(count=len(new), results=new)


@bp.post("/<int:search_id>/seen")
@login_required
def mark_seen(search_id: int):
    saved = _mine(search_id)
    if saved is None:
        return jsonify(error="not found"), 404
    saved.last_seen_at = datetime.now(UTC)
    db.session.commit()
    return "", 204
