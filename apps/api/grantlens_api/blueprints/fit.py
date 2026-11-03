from flask import Blueprint, current_app, g, jsonify, request

from .. import fit, match, usage
from ..extensions import db, limiter
from ..literature import openalex
from ..llm import LLMError, LLMNotConfigured, get_llm
from ..models import Opportunity
from .auth import login_required

bp = Blueprint("fit", __name__)
MIN_TEXT, MAX_TEXT = 40, 4000


@bp.post("/opportunities/<int:opp_id>/fit")
@limiter.limit("10/minute")
@login_required
def fit_endpoint(opp_id: int):
    """Body: {"text": "about me / my project"} or {"orcid": "0000-..."}."""
    opp = db.session.get(Opportunity, opp_id)
    if opp is None:
        return jsonify(error="not found"), 404
    body = request.get_json(silent=True) or {}
    text, orcid = str(body.get("text") or "").strip(), str(body.get("orcid") or "").strip()
    if bool(text) == bool(orcid):
        return jsonify(error="send either text or orcid"), 400
    if text and not MIN_TEXT <= len(text) <= MAX_TEXT:
        return jsonify(error=f"describe yourself in {MIN_TEXT} to {MAX_TEXT} characters"), 400
    try:
        llm = get_llm(current_app.config)
    except LLMNotConfigured as e:
        return jsonify(error=str(e)), 503
    if orcid:
        try:
            _, papers = openalex.works_by_orcid(orcid)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except openalex.OpenAlexError as e:
            return jsonify(error=str(e)), 502
        if not papers:
            return jsonify(error="no publications found for that ORCID iD"), 404
        text = match.profile_text(papers)
    if not usage.consume(g.user.id):
        return jsonify(error="you have reached today's limit of AI requests; try again tomorrow"), 429
    try:
        result = fit.assess(opp, text, llm)
    except LLMError as e:
        usage.refund(g.user.id)
        return jsonify(error=str(e)), 502
    return jsonify(result.as_json())
