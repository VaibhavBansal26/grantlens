"""Email digests: new matches for saved searches (opt-in) and deadline reminders for the watchlist."""
import html
from dataclasses import dataclass, field
from datetime import UTC, datetime

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.datastructures import MultiDict

from .extensions import db
from .mail import Mail, Mailer
from .models import (
    DeadlineReminder,
    Opportunity,
    SavedSearch,
    User,
    WatchedOpportunity,
)
from .retrieval.clean import clean_text
from .retrieval.service import Hit, search

MAX_PER_SEARCH = 10
REMINDER_DAYS = (7, 1)  # remind once when within a week, and once more on the last day


def params_to_args(params: dict) -> MultiDict:
    return MultiDict((k, v) for k, vals in params.items() for v in vals)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def new_matches(saved: SavedSearch, since: datetime) -> list[Hit]:
    """Top matches that entered the corpus after `since`."""
    from .blueprints.search import parse_search

    req = parse_search(params_to_args(saved.params))
    hits = search(req.query, k=50, filters=req.filters, mode=req.mode)
    first_seen = dict(
        db.session.query(Opportunity.id, Opportunity.first_seen_at).filter(
            Opportunity.id.in_([h.id for h in hits])
        )
    )
    return [h for h in hits if first_seen.get(h.id) and _aware(first_seen[h.id]) > _aware(since)]


def unsubscribe_token(user_id: int) -> str:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="unsubscribe").dumps(user_id)


def user_from_token(token: str) -> User | None:
    try:
        uid = URLSafeSerializer(current_app.config["SECRET_KEY"], salt="unsubscribe").loads(token)
    except BadSignature:
        return None
    return db.session.get(User, uid)


def unsubscribe_all(user: User) -> None:
    user.reminders = False
    SavedSearch.query.filter_by(user_id=user.id).update({"alerts": False})
    db.session.commit()


@dataclass
class Digest:
    user: User
    new: list[tuple[SavedSearch, list[Hit]]] = field(default_factory=list)
    reminders: list[tuple[Opportunity, int, int]] = field(default_factory=list)  # opp, days left, threshold

    @property
    def empty(self) -> bool:
        return not self.new and not self.reminders


def build_digest(user: User, now: datetime) -> Digest:
    digest = Digest(user)
    for saved in SavedSearch.query.filter_by(user_id=user.id, alerts=True).order_by(SavedSearch.id):
        hits = new_matches(saved, saved.last_alerted_at or saved.created_at)
        if hits:
            digest.new.append((saved, hits))
    if user.reminders:
        sent = {
            (r.opportunity_id, r.days)
            for r in DeadlineReminder.query.filter_by(user_id=user.id)
        }
        rows = (
            db.session.query(Opportunity)
            .join(WatchedOpportunity, WatchedOpportunity.opportunity_id == Opportunity.id)
            .filter(WatchedOpportunity.user_id == user.id, Opportunity.close_date.is_not(None))
            .order_by(Opportunity.close_date)
        )
        for o in rows:
            left = (o.close_date - now.date()).days
            if not 0 <= left <= max(REMINDER_DAYS):
                continue
            threshold = min(t for t in REMINDER_DAYS if left <= t)
            if (o.id, threshold) not in sent:
                digest.reminders.append((o, left, threshold))
    return digest


def render(digest: Digest, public_url: str) -> Mail:
    e = html.escape
    unsub = f"{public_url}/unsubscribe?token={unsubscribe_token(digest.user.id)}"
    text, body = [], []
    n_new = sum(len(h) for _, h in digest.new)
    if digest.new:
        text.append("NEW MATCHES FOR YOUR SAVED SEARCHES")
        body.append("<h2>New matches for your saved searches</h2>")
        for saved, hits in digest.new:
            text.append(f'\n"{saved.name}" ({len(hits)} new)')
            body.append(f"<h3>{e(saved.name)} <small>({len(hits)} new)</small></h3><ul>")
            for h in hits[:MAX_PER_SEARCH]:
                link = f"{public_url}/opportunity/{h.id}"
                closes = f", closes {h.close_date}" if h.close_date else ""
                text.append(f"- {clean_text(h.title)}{closes}\n  {link}")
                body.append(f'<li><a href="{e(link)}">{e(h.title)}</a>{e(closes)}</li>')
            if len(hits) > MAX_PER_SEARCH:
                more = f"...and {len(hits) - MAX_PER_SEARCH} more: {public_url}/saved"
                text.append(more)
                body.append(f"<li>{e(more)}</li>")
            body.append("</ul>")
    if digest.reminders:
        text.append("\nDEADLINES COMING UP ON YOUR WATCHLIST")
        body.append("<h2>Deadlines coming up on your watchlist</h2><ul>")
        for o, left, _ in digest.reminders:
            when = "today" if left == 0 else f"in {left} day{'s' if left != 1 else ''}"
            link = f"{public_url}/opportunity/{o.id}"
            text.append(f"- {clean_text(o.title)}: closes {when} ({o.close_date})\n  {link}")
            body.append(
                f'<li><a href="{e(link)}">{e(clean_text(o.title))}</a>: closes {e(when)} ({o.close_date})</li>'
            )
        body.append("</ul>")
    footer = f"You get this because you turned on email alerts. Stop all alerts: {unsub}"
    text.append(f"\n--\n{footer}")
    body.append(f'<hr><p><small>You get this because you turned on email alerts. '
                f'<a href="{e(unsub)}">Stop all alerts</a></small></p>')
    parts = []
    if n_new:
        parts.append(f"{n_new} new grant{'s' if n_new != 1 else ''}")
    if digest.reminders:
        k = len(digest.reminders)
        parts.append(f"{k} deadline{'s' if k != 1 else ''} soon")
    return Mail(
        to=digest.user.email, subject="GrantLens: " + ", ".join(parts),
        text="\n".join(text), html="".join(body),
        headers={
            "List-Unsubscribe": f"<{public_url}/api/alerts/unsubscribe?token={unsubscribe_token(digest.user.id)}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


@dataclass
class Stats:
    users: int = 0
    sent: int = 0
    failed: int = 0
    nothing_new: int = 0


def send_alerts(mailer: Mailer, public_url: str, now: datetime | None = None,
                dry_run: bool = False) -> tuple[Stats, list[Mail]]:
    now = now or datetime.now(UTC)
    stats, mails = Stats(), []
    wanted = db.session.query(User.id).filter(
        User.email_verified.is_(True),
        User.reminders.is_(True)
        | User.id.in_(db.session.query(SavedSearch.user_id).filter(SavedSearch.alerts.is_(True))),
    )
    for (uid,) in wanted.all():
        user = db.session.get(User, uid)
        stats.users += 1
        digest = build_digest(user, now)
        if digest.empty:
            stats.nothing_new += 1
            continue
        mail = render(digest, public_url)
        mails.append(mail)
        if dry_run:
            continue
        try:
            mailer.send(mail)
        except Exception:
            current_app.logger.exception("alert email to user %s failed", uid)
            stats.failed += 1
            continue
        # Only after a successful send: advance the cursors so nothing is repeated or lost.
        for saved, _ in digest.new:
            saved.last_alerted_at = now
        for o, _, threshold in digest.reminders:
            db.session.add(DeadlineReminder(user_id=uid, opportunity_id=o.id, days=threshold))
        db.session.commit()
        stats.sent += 1
    return stats, mails
