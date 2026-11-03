from flask import Blueprint, Response, jsonify
from sqlalchemy import func

from .. import ics
from ..extensions import db, limiter
from ..models import Opportunity
from ..retrieval.clean import clean_text

bp = Blueprint("opportunities", __name__)


def _detail(o: Opportunity) -> dict:
    return {
        "id": o.id, "source": o.source, "number": o.number, "title": clean_text(o.title),
        "abstract": clean_text(o.abstract) or None, "agency": o.agency, "status": o.status, "url": o.url,
        "categories": o.categories or [], "eligibility": o.eligibility or [],
        "funding_instruments": o.funding_instruments or [],
        "amount_min": o.amount_min, "amount_max": o.amount_max,
        "open_date": o.open_date.isoformat() if o.open_date else None,
        "close_date": o.close_date.isoformat() if o.close_date else None,
    }


@bp.get("/opportunities/<int:opp_id>")
@limiter.limit("120/minute")
def detail(opp_id: int):
    return jsonify(_detail(db.get_or_404(Opportunity, opp_id)))


@bp.get("/opportunities/<int:opp_id>.ics")
@limiter.limit("60/minute")
def deadline_ics(opp_id: int):
    o = db.get_or_404(Opportunity, opp_id)
    if not o.close_date:
        return jsonify(error="this opportunity has no close date"), 404
    return Response(
        ics.calendar([o]), mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="grant-{o.id}-deadline.ics"'},
    )


@bp.get("/facets")
@limiter.limit("60/minute")
def facets():
    statuses = db.session.query(Opportunity.status, func.count()).group_by(Opportunity.status)
    agencies = (
        db.session.query(Opportunity.agency, func.count())
        .filter(Opportunity.agency.is_not(None))
        .group_by(Opportunity.agency)
        .order_by(func.count().desc())
        .limit(40)
    )
    return jsonify(
        statuses=[{"value": s, "count": c} for s, c in statuses if s],
        agencies=[{"value": a, "count": c} for a, c in agencies],
    )
