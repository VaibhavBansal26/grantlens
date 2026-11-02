from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .. import match
from ..literature import openalex

bp = Blueprint("match", __name__)


@bp.post("/match")
def match_endpoint():
    """Body: {"text": "..."} or {"orcid": "0000-..."}; optional {"status": [...], "k": 15}."""
    body = request.get_json(silent=True) or {}
    text, orcid = str(body.get("text") or "").strip(), str(body.get("orcid") or "").strip()
    if bool(text) == bool(orcid):
        return jsonify(error="send either text or orcid"), 400
    if len(text) > match.MAX_TEXT:
        return jsonify(error=f"text is limited to {match.MAX_TEXT} characters"), 400
    statuses = body.get("status")
    if statuses is not None and (
        not isinstance(statuses, list) or not set(statuses) <= {"posted", "forecasted", "closed", "archived"}
    ):
        return jsonify(error="status must be a list of posted, forecasted, closed, archived"), 400
    papers, name = None, None
    if orcid:
        try:
            name, papers = openalex.works_by_orcid(orcid)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except openalex.OpenAlexError as e:
            return jsonify(error=str(e)), 502
        if not papers:
            return jsonify(error="no publications found for that ORCID iD"), 404
        text = match.profile_text(papers)
    results = match.match_grants(text, papers, k=min(int(body.get("k", 15)), 30), statuses=statuses)
    return jsonify(
        profile={"name": name, "papers": [asdict(p) for p in papers or []], "text_used": text},
        results=[match.as_json(m) for m in results],
    )
