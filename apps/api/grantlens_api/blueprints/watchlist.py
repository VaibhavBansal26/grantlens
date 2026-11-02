from datetime import date

from flask import Blueprint, g, jsonify
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Opportunity, WatchedOpportunity
from ..retrieval.clean import clean_text
from .auth import login_required

bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")
MAX_PER_USER = 500


def _item(o: Opportunity, added) -> dict:
    return {
        "id": o.id, "title": clean_text(o.title), "agency": o.agency, "status": o.status,
        "close_date": o.close_date.isoformat() if o.close_date else None,
        "days_left": (o.close_date - date.today()).days if o.close_date else None,
        "amount_max": o.amount_max, "added_at": added.isoformat(),
    }


@bp.get("")
@login_required
def list_watched():
    rows = (
        db.session.query(Opportunity, WatchedOpportunity.created_at)
        .join(WatchedOpportunity, WatchedOpportunity.opportunity_id == Opportunity.id)
        .filter(WatchedOpportunity.user_id == g.user.id)
        .all()
    )
    items = [_item(o, added) for o, added in rows]
    # soonest deadline first; grants with no close date go last
    items.sort(key=lambda i: (i["close_date"] is None, i["close_date"] or "", i["title"]))
    return jsonify(items=items)


@bp.put("/<int:opp_id>")
@login_required
def add(opp_id: int):
    if db.session.get(Opportunity, opp_id) is None:
        return jsonify(error="not found"), 404
    if WatchedOpportunity.query.filter_by(user_id=g.user.id).count() >= MAX_PER_USER:
        return jsonify(error=f"limit of {MAX_PER_USER} watched grants reached"), 409
    db.session.add(WatchedOpportunity(user_id=g.user.id, opportunity_id=opp_id))
    try:
        db.session.commit()
    except IntegrityError:  # already watching: adding twice is a no-op
        db.session.rollback()
    return "", 204


@bp.delete("/<int:opp_id>")
@login_required
def remove(opp_id: int):
    WatchedOpportunity.query.filter_by(user_id=g.user.id, opportunity_id=opp_id).delete()
    db.session.commit()
    return "", 204
