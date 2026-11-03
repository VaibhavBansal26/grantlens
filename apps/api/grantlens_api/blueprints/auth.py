import re
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import accounts
from ..extensions import db, limiter
from ..models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 10
# Compared against when the email is unknown, so login time doesn't reveal which emails exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _session_user() -> User | None:
    """The signed-in user, or None. A cookie issued before the last password reset no longer counts."""
    user = db.session.get(User, session["uid"]) if "uid" in session else None
    if user is None or session.get("sv") != user.session_version:
        session.clear()
        return None
    return user


def _sign_in(user: User) -> None:
    session.clear()
    session["uid"], session["sv"] = user.id, user.session_version


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = _session_user()
        if user is None:
            return jsonify(error="login required"), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def _credentials() -> tuple[str, str]:
    body = request.get_json(silent=True) or {}
    return str(body.get("email", "")).strip().lower(), str(body.get("password", ""))


def _attempted_email() -> str:
    return str((request.get_json(silent=True) or {}).get("email", "")).strip().lower()[:254]


def _valid_password(password: str) -> str | None:
    return None if len(password) >= MIN_PASSWORD else f"password must be at least {MIN_PASSWORD} characters"


@bp.post("/register")
@limiter.limit("5/hour;20/day")
def register():
    email, password = _credentials()
    if len(email) > 254 or not EMAIL.match(email):
        return jsonify(error="enter a valid email address"), 400
    if problem := _valid_password(password):
        return jsonify(error=problem), 400
    user = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="that email is already registered"), 409
    _sign_in(user)
    accounts.send_verification_email(user)
    return jsonify(id=user.id, email=user.email), 201


@bp.post("/login")
@limiter.limit("10/minute;100/hour")  # per address: slows brute force from one place
@limiter.limit("20/hour", key_func=_attempted_email)  # per account: and from many places at once
def login():
    email, password = _credentials()
    user = User.query.filter_by(email=email).first()
    ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if not (user and ok):
        return jsonify(error="incorrect email or password"), 401
    _sign_in(user)
    return jsonify(id=user.id, email=user.email)


@bp.post("/logout")
def logout():
    session.clear()
    return "", 204


@bp.get("/me")
def me():
    user = _session_user()
    return jsonify(
        user=None if user is None else {"id": user.id, "email": user.email, "reminders": user.reminders,
                                        "email_verified": user.email_verified,
                                        "is_admin": user.is_admin}
    )


@bp.post("/verify")
@limiter.limit("20/hour")
def verify():
    """Follows the emailed link. Needs no login (it may be opened on another device); the token is the proof."""
    user = accounts.user_from_verify_token(str((request.get_json(silent=True) or {}).get("token", "")))
    if user is None:
        return jsonify(error="this confirmation link is invalid or has expired"), 400
    if not user.email_verified:
        user.email_verified = True
        db.session.commit()
    return jsonify(ok=True, email=user.email)


@bp.post("/resend-verification")
@limiter.limit("5/hour")
@login_required
def resend_verification():
    if g.user.email_verified:
        return jsonify(ok=True, already_verified=True)
    accounts.send_verification_email(g.user)
    return jsonify(ok=True), 202


@bp.post("/forgot")
@limiter.limit("5/hour")
@limiter.limit("3/hour", key_func=_attempted_email)  # one mailbox can't be flooded with reset emails
def forgot():
    """Always answers the same, so the response never reveals which emails have accounts."""
    user = User.query.filter_by(email=_credentials()[0]).first()
    if user:
        accounts.send_reset_email(user)
    return jsonify(ok=True), 202


@bp.post("/reset")
@limiter.limit("10/hour")
def reset():
    body = request.get_json(silent=True) or {}
    user = accounts.user_from_reset_token(str(body.get("token", "")))
    if user is None:
        return jsonify(error="this reset link is invalid or has expired"), 400
    if problem := _valid_password(str(body.get("password", ""))):
        return jsonify(error=problem), 400
    user.password_hash = generate_password_hash(str(body["password"]))
    user.session_version += 1  # signs out every device, including whoever may have had the old password
    db.session.commit()
    session.clear()
    return jsonify(ok=True)


@bp.delete("/account")
@limiter.limit("5/hour")
@login_required
def delete_account():
    """Deletes the account and all its data. Needs the password again, so a stolen session can't do it."""
    password = str((request.get_json(silent=True) or {}).get("password", ""))
    if not check_password_hash(g.user.password_hash, password):
        return jsonify(error="incorrect password"), 403
    accounts.delete_user_data(g.user)
    session.clear()
    return "", 204


@bp.patch("/preferences")
@login_required
def preferences():
    body = request.get_json(silent=True) or {}
    if "reminders" in body:
        if not isinstance(body["reminders"], bool):
            return jsonify(error="reminders must be true or false"), 400
        if body["reminders"] and not g.user.email_verified:
            return jsonify(error="confirm your email address first"), 403
        g.user.reminders = body["reminders"]
        db.session.commit()
    return jsonify(reminders=g.user.reminders)
