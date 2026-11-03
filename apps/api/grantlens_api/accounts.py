"""Account lifecycle: password-reset links and deleting a user's data."""
import hashlib
import logging

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .extensions import db
from .mail import Mail, get_mailer
from .models import (
    DeadlineReminder,
    DocChunk,
    Document,
    LlmUsage,
    Review,
    SavedSearch,
    User,
    WatchedOpportunity,
)

RESET_MAX_AGE = 3600  # seconds a reset link stays valid
log = logging.getLogger("grantlens")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def reset_token(user: User) -> str:
    # Bound to the current password hash, so a link stops working the moment it has been used.
    return _serializer().dumps([user.id, _fingerprint(user)])


def user_from_reset_token(token: str, max_age: int = RESET_MAX_AGE) -> User | None:
    try:
        uid, fingerprint = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None
    user = db.session.get(User, uid)
    return user if user and user.password_hash and _fingerprint(user) == fingerprint else None


def send_reset_email(user: User) -> None:
    link = f"{current_app.config['PUBLIC_URL']}/reset-password?token={reset_token(user)}"
    text = (f"Someone asked to reset the password for this GrantLens account.\n\nChoose a new password "
            f"within an hour: {link}\n\nIf this was not you, ignore this email; nothing changes.")
    html = (f'<p>Someone asked to reset the password for this GrantLens account.</p>'
            f'<p><a href="{link}">Choose a new password</a> within an hour.</p>'
            f"<p>If this was not you, ignore this email; nothing changes.</p>")
    try:
        get_mailer(current_app.config).send(Mail(user.email, "Reset your GrantLens password", text, html))
    except Exception:
        log.exception("password reset email failed", extra={"fields": {"user": user.id}})


def delete_user_data(user: User) -> None:
    """Remove the account and everything tied to it. Explicit, so it also works where the database
    does not enforce ON DELETE CASCADE (SQLite in tests)."""
    doc_ids = [d for (d,) in db.session.query(Document.id).filter_by(user_id=user.id)]
    if doc_ids:
        DocChunk.query.filter(DocChunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
    for model in (Document, SavedSearch, WatchedOpportunity, DeadlineReminder, Review, LlmUsage):
        model.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.delete(user)
    db.session.commit()
