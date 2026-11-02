from dataclasses import asdict, dataclass
from datetime import date

from flask import Blueprint, jsonify, request
from werkzeug.datastructures import MultiDict

from ..retrieval.filters import Filters
from ..retrieval.service import search

bp = Blueprint("search", __name__)


@dataclass
class SearchRequest:
    query: str
    mode: str
    filters: Filters
    k: int
    rerank: bool


def parse_search(args: MultiDict) -> SearchRequest:
    """Shared by /search and saved searches. Raises ValueError with a user-facing message."""
    query = (args.get("q") or "").strip()
    if not query:
        raise ValueError("q is required")
    mode = args.get("mode", "hybrid")
    if mode not in ("bm25", "dense", "hybrid"):
        raise ValueError("mode must be bm25, dense or hybrid")

    def day(name: str) -> date | None:
        value = args.get(name)
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            raise ValueError("invalid date, expected YYYY-MM-DD") from None

    filters = Filters(
        status=args.getlist("status") or None,
        agency=args.get("agency") or None,
        closes_after=day("closes_after"),
        closes_before=day("closes_before"),
        min_amount=args.get("min_amount", type=int),
        max_amount=args.get("max_amount", type=int),
    )
    return SearchRequest(
        query, mode, filters, min(args.get("k", 10, type=int), 50), args.get("rerank") == "1"
    )


@bp.get("/search")
def search_endpoint():
    try:
        req = parse_search(request.args)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    hits = search(req.query, k=req.k, filters=req.filters, mode=req.mode, rerank=req.rerank)
    return jsonify(query=req.query, mode=req.mode, results=[asdict(h) for h in hits])
