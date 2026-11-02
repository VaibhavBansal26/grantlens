import click
from flask import Flask

from .ingest import upsert
from .sources.grants_gov import GrantsGovSource
from .sources.nih_reporter import NihReporterSource
from .sources.nsf import NsfSource

SOURCES = {"grants_gov": GrantsGovSource, "nih_reporter": NihReporterSource, "nsf": NsfSource}


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
        from .extensions import db
        from .models import Opportunity
        from .retrieval.embedder import embed_documents
        from .retrieval.text import doc_text

        done = 0
        while True:
            rows = Opportunity.query.filter(Opportunity.embedding.is_(None)).limit(batch).all()
            if not rows:
                break
            vecs = embed_documents([doc_text(r.title, r.abstract) for r in rows])
            for row, vec in zip(rows, vecs, strict=True):
                row.embedding = vec
            db.session.commit()
            done += len(rows)
            click.echo(f"embedded {done}")

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
