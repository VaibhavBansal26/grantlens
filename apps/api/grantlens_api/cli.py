import click
from flask import Flask

from .ingest import upsert
from .sources.grants_gov import GrantsGovSource

SOURCES = {"grants_gov": GrantsGovSource}


def register(app: Flask) -> None:
    @app.cli.command("sync")
    @click.option("--source", type=click.Choice(sorted(SOURCES)), default="grants_gov")
    @click.option("--limit", type=int, default=None, help="Max records (for trial runs)")
    def sync(source: str, limit: int | None) -> None:
        """Pull opportunities from a source and upsert them."""
        stats = upsert(SOURCES[source]().fetch(limit=limit))
        click.echo(
            f"{source}: inserted={stats.inserted} updated={stats.updated} "
            f"unchanged={stats.unchanged}"
        )
