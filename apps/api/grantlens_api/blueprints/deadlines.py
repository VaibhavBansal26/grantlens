from datetime import date, timedelta

from flask import Blueprint, Response, g, jsonify, request

from .. import ics
from ..models import Opportunity, SavedSearch, WatchedOpportunity
from ..retrieval.clean import clean_text
from ..retrieval.service import search
from .auth import login_required
from .saved import _args
from .search import parse_search

bp = Blueprint("deadlines", __name__)
LIMIT = 500
MAX_SPAN = timedelta(days=370)


def _window() -> tuple[date, date]:
    """?start & ?end (YYYY-MM-DD); default is the next 30 days."""
    try:
        start = date.fromisoformat(request.args["start"]) if "start" in request.args else date.today()
        end = date.fromisoformat(request.args["end"]) if "end" in request.args else start + timedelta(days=30)
    except ValueError:
        raise ValueError("invalid date, expected YYYY-MM-DD") from None
    if end < start or end - start > MAX_SPAN:
        raise ValueError("end must be on or after start, within 370 days")
    return start, end


def _opportunities(start: date, end: date) -> list[Opportunity]:
    statuses = request.args.getlist("status") or ["posted"]
    if request.args.get("scope") == "saved":
        rows: dict[int, Opportunity] = {}
        for s in SavedSearch.query.filter_by(user_id=g.user.id).limit(20):
            req = parse_search(_args(s.params))
            ids = [h.id for h in search(req.query, k=50, filters=req.filters, mode=req.mode)]
            if ids:
                q = Opportunity.query.filter(Opportunity.id.in_(ids), Opportunity.status.in_(statuses))
                rows.update({o.id: o for o in q if o.close_date and start <= o.close_date <= end})
        return sorted(rows.values(), key=lambda o: (o.close_date, o.id))[:LIMIT]
    if request.args.get("scope") == "watchlist":
        q = (
            Opportunity.query.join(
                WatchedOpportunity, WatchedOpportunity.opportunity_id == Opportunity.id
            )
            .filter(WatchedOpportunity.user_id == g.user.id)
            .filter(Opportunity.close_date >= start, Opportunity.close_date <= end)
        )
        if request.args.getlist("status"):
            q = q.filter(Opportunity.status.in_(request.args.getlist("status")))
        return q.order_by(Opportunity.close_date, Opportunity.id).limit(LIMIT).all()
    q = Opportunity.query.filter(
        Opportunity.close_date >= start, Opportunity.close_date <= end,
        Opportunity.status.in_(statuses),
    )
    if agency := request.args.get("agency"):
        q = q.filter(Opportunity.agency.ilike(f"%{agency}%"))
    return q.order_by(Opportunity.close_date, Opportunity.id).limit(LIMIT).all()


def _guard(view):
    """The personal scopes (saved, watchlist) need a login; the public scope does not."""
    def wrapped():
        if request.args.get("scope") in ("saved", "watchlist"):
            return login_required(view)()
        return view()

    wrapped.__name__ = view.__name__
    return wrapped


@bp.get("/deadlines")
@_guard
def deadlines():
    try:
        start, end = _window()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    rows = _opportunities(start, end)
    return jsonify(
        start=start.isoformat(), end=end.isoformat(), truncated=len(rows) >= LIMIT,
        deadlines=[
            {"id": o.id, "title": clean_text(o.title), "agency": o.agency, "status": o.status,
             "close_date": o.close_date.isoformat(), "amount_max": o.amount_max}
            for o in rows
        ],
    )


@bp.get("/deadlines.ics")
@_guard
def deadlines_ics():
    try:
        start, end = _window()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return Response(
        ics.calendar(_opportunities(start, end)), mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="grantlens-deadlines.ics"'},
    )
