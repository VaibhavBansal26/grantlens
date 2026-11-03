from dataclasses import asdict

from flask import Blueprint, jsonify, request

from ..extensions import limiter
from ..literature import openalex

bp = Blueprint("literature", __name__, url_prefix="/literature")


@bp.get("/search")
@limiter.limit("30/minute")
def search():
    q = (request.args.get("q") or "").strip()
    if not q or len(q) > 300:
        return jsonify(error="q is required (300 characters at most)"), 400
    limit = min(request.args.get("k", 10, type=int), 25)
    year_from = request.args.get("year_from", type=int)
    try:
        papers = openalex.search_works(q, limit=limit, year_from=year_from)
    except openalex.OpenAlexError as e:
        return jsonify(error=str(e)), 502
    return jsonify(query=q, results=[asdict(p) for p in papers])
