from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify
from sqlalchemy import func

from ..extensions import db
from ..models import Opportunity
from ..retrieval.clean import clean_text

bp = Blueprint("opportunities", __name__)


def _detail(o: Opportunity) -> dict:
    return {
        "id": o.id, "source": o.source, "number": o.number, "title": o.title,
        "abstract": clean_text(o.abstract) or None, "agency": o.agency, "status": o.status, "url": o.url,
        "categories": o.categories or [], "eligibility": o.eligibility or [],
        "funding_instruments": o.funding_instruments or [],
        "amount_min": o.amount_min, "amount_max": o.amount_max,
        "open_date": o.open_date.isoformat() if o.open_date else None,
        "close_date": o.close_date.isoformat() if o.close_date else None,
    }


@bp.get("/opportunities/<int:opp_id>")
def detail(opp_id: int):
    return jsonify(_detail(db.get_or_404(Opportunity, opp_id)))


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\n", "\\n")


@bp.get("/opportunities/<int:opp_id>.ics")
def deadline_ics(opp_id: int):
    o = db.get_or_404(Opportunity, opp_id)
    if not o.close_date:
        return jsonify(error="this opportunity has no close date"), 404
    day, nxt = o.close_date, o.close_date + timedelta(days=1)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GrantLens//EN", "BEGIN:VEVENT",
        f"UID:opportunity-{o.id}@grantlens",
        f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{nxt.strftime('%Y%m%d')}",
        f"SUMMARY:{_ics_escape('Deadline: ' + o.title)}",
        f"DESCRIPTION:{_ics_escape((o.number or '') + ' ' + (o.url or ''))}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return Response(
        "\r\n".join(lines) + "\r\n", mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="grant-{o.id}-deadline.ics"'},
    )


@bp.get("/facets")
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
