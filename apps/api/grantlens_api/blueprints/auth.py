import re
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 10
# Compared against when the email is unknown, so login time doesn't reveal which emails exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = db.session.get(User, session["uid"]) if "uid" in session else None
        if user is None:
            session.pop("uid", None)
            return jsonify(error="login required"), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def _credentials() -> tuple[str, str]:
    body = request.get_json(silent=True) or {}
    return str(body.get("email", "")).strip().lower(), str(body.get("password", ""))


@bp.post("/register")
def register():
    email, password = _credentials()
    if len(email) > 254 or not EMAIL.match(email):
        return jsonify(error="enter a valid email address"), 400
    if len(password) < MIN_PASSWORD:
        return jsonify(error=f"password must be at least {MIN_PASSWORD} characters"), 400
    user = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="that email is already registered"), 409
    session.clear()
    session["uid"] = user.id
    return jsonify(id=user.id, email=user.email), 201


@bp.post("/login")
def login():
    email, password = _credentials()
    user = User.query.filter_by(email=email).first()
    ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if not (user and ok):
        return jsonify(error="incorrect email or password"), 401
    session.clear()
    session["uid"] = user.id
    return jsonify(id=user.id, email=user.email)


@bp.post("/logout")
def logout():
    session.clear()
    return "", 204


@bp.get("/me")
def me():
    user = db.session.get(User, session["uid"]) if "uid" in session else None
    return jsonify(user=None if user is None else {"id": user.id, "email": user.email})
