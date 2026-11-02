from dataclasses import asdict
from datetime import date

from flask import Blueprint, jsonify, request

from ..retrieval.filters import Filters
from ..retrieval.service import search

bp = Blueprint("search", __name__)


def _date(name: str) -> date | None:
    value = request.args.get(name)
    return date.fromisoformat(value) if value else None


@bp.get("/search")
def search_endpoint():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(error="q is required"), 400
    mode = request.args.get("mode", "hybrid")
    if mode not in ("bm25", "dense", "hybrid"):
        return jsonify(error="mode must be bm25, dense or hybrid"), 400
    try:
        filters = Filters(
            status=request.args.getlist("status") or None,
            agency=request.args.get("agency"),
            closes_after=_date("closes_after"),
            closes_before=_date("closes_before"),
            min_amount=request.args.get("min_amount", type=int),
            max_amount=request.args.get("max_amount", type=int),
        )
        k = min(request.args.get("k", 10, type=int), 50)
    except ValueError:
        return jsonify(error="invalid date, expected YYYY-MM-DD"), 400
    hits = search(query, k=k, filters=filters, mode=mode, rerank=request.args.get("rerank") == "1")
    return jsonify(query=query, mode=mode, results=[asdict(h) for h in hits])
