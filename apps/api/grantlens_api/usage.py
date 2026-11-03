"""Per-user daily cap on AI requests, so one account can't run up the bill."""
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import LlmUsage

DEFAULT_LIMIT = 50


def consume(user_id: int) -> bool:
    """Count one AI request for today; False (and no count) once the daily limit is reached."""
    limit = int(current_app.config.get("LLM_DAILY_LIMIT", DEFAULT_LIMIT))
    today = datetime.now(UTC).date()
    for _ in range(2):  # the second pass covers two first requests of the day racing to insert
        # one atomic UPDATE: the limit check and the increment cannot be split by another request
        res = db.session.execute(
            update(LlmUsage)
            .where(LlmUsage.user_id == user_id, LlmUsage.day == today, LlmUsage.count < limit)
            .values(count=LlmUsage.count + 1)
        )
        if res.rowcount:
            db.session.commit()
            return True
        if db.session.query(LlmUsage).filter_by(user_id=user_id, day=today).first():
            db.session.rollback()
            return False  # row exists and is at the limit
        try:
            db.session.add(LlmUsage(user_id=user_id, day=today, count=1))
            db.session.commit()
            return limit > 0
        except IntegrityError:
            db.session.rollback()
    return False


def refund(user_id: int) -> None:
    """Give the request back when the AI call failed before producing anything."""
    today = datetime.now(UTC).date()
    db.session.execute(
        update(LlmUsage)
        .where(LlmUsage.user_id == user_id, LlmUsage.day == today, LlmUsage.count > 0)
        .values(count=LlmUsage.count - 1)
    )
    db.session.commit()
