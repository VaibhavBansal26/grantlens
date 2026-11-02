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
    @click.option("--limit", type=int, default=None, help="Max records (for trial runs)")
    def sync(source: str, query: str | None, limit: int | None) -> None:
        """Pull opportunities from a source and upsert them."""
        kwarg = {"grants_gov": "keyword", "nih_reporter": "text", "nsf": "keyword"}[source]
        src = SOURCES[source](**({kwarg: query} if query else {}))
        stats = upsert(src.fetch(limit=limit))
        click.echo(
            f"{source}: inserted={stats.inserted} updated={stats.updated} "
            f"unchanged={stats.unchanged}"
        )
