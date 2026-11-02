from flask import Blueprint, jsonify, request

from ..alerts import unsubscribe_all, user_from_token

bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@bp.post("/unsubscribe")
def unsubscribe():
    """Works without a login (the link is in the email). POST so link previewers can't trigger it;
    the token may be in the query string, as RFC 8058 one-click unsubscribe requires."""
    token = request.args.get("token") or (request.get_json(silent=True) or {}).get("token", "")
    user = user_from_token(str(token))
    if user is None:
        return jsonify(error="this unsubscribe link is not valid"), 400
    unsubscribe_all(user)
    return jsonify(ok=True)
