from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Index, UniqueConstraint

from .extensions import db

EMBED_DIM = 384  # BAAI/bge-small-en-v1.5


def _now() -> datetime:
    return datetime.now(UTC)


class Opportunity(db.Model):
    __tablename__ = "opportunity"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_opportunity_source_ext"),
        Index(
            "ix_opportunity_embedding", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(64), nullable=False)
    number = db.Column(db.String(128))
    title = db.Column(db.Text, nullable=False)
    abstract = db.Column(db.Text)
    agency = db.Column(db.String(255))
    categories = db.Column(JSON, default=list)
    eligibility = db.Column(JSON, default=list)
    funding_instruments = db.Column(JSON, default=list)
    amount_min = db.Column(db.BigInteger)
    amount_max = db.Column(db.BigInteger)
    open_date = db.Column(db.Date)
    close_date = db.Column(db.Date)
    status = db.Column(db.String(32), index=True)
    url = db.Column(db.Text)
    raw_json = db.Column(JSON)
    embedding = db.Column(Vector(EMBED_DIM).with_variant(JSON(), "sqlite"))
    content_hash = db.Column(db.String(64), nullable=False)
    first_seen_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)


class Award(db.Model):
    """A past, funded project (NIH RePORTER / NSF). Kept apart from open opportunities."""

    __tablename__ = "award"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_award_source_ext"),)

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(64), nullable=False)
    project_number = db.Column(db.String(128))
    title = db.Column(db.Text, nullable=False)
    abstract = db.Column(db.Text)
    agency = db.Column(db.String(255))
    organization = db.Column(db.String(255))
    investigators = db.Column(JSON, default=list)
    keywords = db.Column(JSON, default=list)
    amount = db.Column(db.BigInteger)
    fiscal_year = db.Column(db.Integer, index=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    url = db.Column(db.Text)
    raw_json = db.Column(JSON)
    content_hash = db.Column(db.String(64), nullable=False)
    first_seen_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)


class User(db.Model):
    __tablename__ = "user_account"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    reminders = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())


class SavedSearch(db.Model):
    __tablename__ = "saved_search"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_account.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    params = db.Column(JSON, nullable=False)  # the /search query params, as {name: [values]}
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    last_seen_at = db.Column(db.DateTime(timezone=True), default=_now)  # "new" = first seen after
    alerts = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    last_alerted_at = db.Column(db.DateTime(timezone=True))  # emails cover matches after this


class WatchedOpportunity(db.Model):
    __tablename__ = "watched_opportunity"
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id", name="uq_watch_user_opp"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_account.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"),
                               nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)


class DeadlineReminder(db.Model):
    """One row per reminder email sent, so a watched grant is reminded once per threshold."""

    __tablename__ = "deadline_reminder"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", "days", name="uq_reminder_user_opp_days"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_account.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"),
                               nullable=False)
    days = db.Column(db.Integer, nullable=False)  # threshold: 7 or 1
    sent_at = db.Column(db.DateTime(timezone=True), default=_now)


class Document(db.Model):
    """A PDF a user uploaded for Q&A. Only extracted text is kept, never the file."""

    __tablename__ = "document"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_account.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    page_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)


class DocChunk(db.Model):
    __tablename__ = "doc_chunk"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    idx = db.Column(db.Integer, nullable=False)  # order within the document
    page = db.Column(db.Integer, nullable=False)  # 1-based page the chunk starts on
    text = db.Column(db.Text, nullable=False)
    embedding = db.Column(Vector(EMBED_DIM).with_variant(JSON(), "sqlite"))


class LlmUsage(db.Model):
    """How many AI requests a user made on a given UTC day (cost guard)."""

    __tablename__ = "llm_usage"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_llm_usage_user_day"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_account.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    count = db.Column(db.Integer, nullable=False, default=0)
