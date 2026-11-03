"""Automatic expiry of data that should not live forever. Run `flask retention` on a schedule (e.g. daily).

Uploaded documents are the most sensitive thing stored (extracted text of a user's own files), so they expire.
Usage counters and sent-reminder markers are bookkeeping that is useless after a while. Saved searches, the watchlist
and reviews are things people curate on purpose and are never expired automatically.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .extensions import db
from .models import DeadlineReminder, DocChunk, Document, LlmUsage


@dataclass
class Purged:
    documents: int = 0
    usage_rows: int = 0
    reminder_rows: int = 0


def purge(document_days: int, usage_days: int, reminder_days: int, now: datetime | None = None,
          dry_run: bool = False) -> Purged:
    """Delete what is older than each limit; a limit of 0 or less turns that cleanup off."""
    now = now or datetime.now(UTC)
    out = Purged()
    if document_days > 0:
        old = Document.query.filter(Document.created_at < now - timedelta(days=document_days))
        ids = [d for (d,) in old.with_entities(Document.id)]
        out.documents = len(ids)
        if ids and not dry_run:  # explicit, so it also works where the database does not enforce ON DELETE CASCADE
            DocChunk.query.filter(DocChunk.document_id.in_(ids)).delete(synchronize_session=False)
            Document.query.filter(Document.id.in_(ids)).delete(synchronize_session=False)
    if usage_days > 0:
        rows = LlmUsage.query.filter(LlmUsage.day < (now - timedelta(days=usage_days)).date())
        out.usage_rows = rows.count()
        if not dry_run:
            rows.delete(synchronize_session=False)
    if reminder_days > 0:
        rows = DeadlineReminder.query.filter(DeadlineReminder.sent_at < now - timedelta(days=reminder_days))
        out.reminder_rows = rows.count()
        if not dry_run:
            rows.delete(synchronize_session=False)
    if not dry_run:
        db.session.commit()
    return out
