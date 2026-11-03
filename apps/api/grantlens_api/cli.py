import click
from flask import Flask

from .ingest import upsert
from .syncer import SOURCES


def register(app: Flask) -> None:
    @app.cli.command("sync")
    @click.option("--source", type=click.Choice(sorted(SOURCES)), default="grants_gov")
    @click.option("--query", default=None, help="Keyword filter (NIH/NSF/Grants.gov)")
    @click.option("--since", type=click.DateTime(["%Y-%m-%d"]), default=None)
    @click.option("--until", type=click.DateTime(["%Y-%m-%d"]), default=None)
    @click.option("--statuses", default=None, help="Grants.gov only, e.g. 'closed|archived'")
    @click.option("--limit", type=int, default=None, help="Max records (for trial runs)")
    def sync(source, query, since, until, statuses, limit) -> None:
        """Pull opportunities from a source and upsert them."""
        kwarg = {"grants_gov": "keyword", "nih_reporter": "text", "nsf": "keyword"}[source]
        kwargs = {kwarg: query} if query else {}
        if source == "grants_gov" and statuses:
            kwargs["statuses"] = statuses
        if source != "grants_gov":
            kwargs |= {k: v.date() for k, v in (("since", since), ("until", until)) if v}
        src = SOURCES[source](**kwargs)
        stats = upsert(src.fetch(limit=limit))
        click.echo(
            f"{source}: inserted={stats.inserted} updated={stats.updated} "
            f"unchanged={stats.unchanged}"
        )

    @app.cli.command("quality")
    def quality() -> None:
        """Print null rates and duplicate-title counts per source."""
        from .quality import report

        click.echo("\n".join(report()))

    @app.cli.command("embed")
    @click.option("--batch", type=int, default=64)
    def embed(batch: int) -> None:
        """Embed opportunities that have no embedding yet."""
        from .syncer import embed_missing

        embed_missing(batch, on_progress=lambda n: click.echo(f"embedded {n}"))

    @app.cli.command("make-admin")
    @click.argument("email")
    @click.option("--revoke", is_flag=True, help="Remove admin rights instead")
    def make_admin(email: str, revoke: bool) -> None:
        """Let a registered user load grants and manage schedules at /admin. Only this command can grant it."""
        from .extensions import db
        from .models import User

        user = User.query.filter_by(email=email.strip().lower()).first()
        if user is None:
            raise click.ClickException("no account with that email; register it first")
        user.is_admin = not revoke
        db.session.commit()
        click.echo(f"{user.email}: admin={user.is_admin}")

    @app.cli.command("send-alerts")
    @click.option("--dry-run", is_flag=True, help="Print what would be sent; send and record nothing")
    def send_alerts_cmd(dry_run: bool) -> None:
        """Email saved-search matches and watchlist deadline reminders. Run on a schedule (e.g. daily)."""
        from .alerts import send_alerts
        from .mail import get_mailer

        cfg = app.config
        stats, mails = send_alerts(get_mailer(cfg), cfg["PUBLIC_URL"], dry_run=dry_run)
        if dry_run:
            for m in mails:
                click.echo(f"--- to {m.to}: {m.subject}\n{m.text}\n")
        click.echo(
            f"users={stats.users} sent={stats.sent} failed={stats.failed} "
            f"nothing_new={stats.nothing_new}{' (dry run)' if dry_run else ''}"
        )

    @app.cli.command("retention")
    @click.option("--dry-run", is_flag=True, help="Count what would be deleted; delete nothing")
    def retention_cmd(dry_run: bool) -> None:
        """Delete expired documents and old bookkeeping rows. Run on a schedule (e.g. daily)."""
        from .retention import purge

        cfg = app.config
        out = purge(cfg["RETENTION_DOCUMENT_DAYS"], cfg["RETENTION_USAGE_DAYS"], cfg["RETENTION_REMINDER_DAYS"],
                    dry_run=dry_run)
        click.echo(f"documents={out.documents} usage_rows={out.usage_rows} reminder_rows={out.reminder_rows} job_rows={out.job_rows}"
                   f"{' (dry run)' if dry_run else ''}")

    @app.cli.command("worker")
    @click.option("--once", is_flag=True, help="Run what is queued, then exit")
    def worker_cmd(once: bool) -> None:
        """Run background jobs (literature reviews). Start one of these next to the API when JOBS_MODE=worker."""
        from .jobs import work

        done = work(app, once=once)
        if once:
            click.echo(f"jobs run: {done}")
