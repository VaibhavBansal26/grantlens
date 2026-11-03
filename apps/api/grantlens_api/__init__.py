from flask import Flask

from .config import Config
from .extensions import db, limiter, migrate
from .hardening import harden


def create_app(config: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    harden(app)
    limiter.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)

    from .blueprints import (
        admin,
        alerts,
        auth,
        deadlines,
        documents,
        fit,
        health,
        literature,
        match,
        opportunities,
        reviews,
        saved,
        search,
        watchlist,
    )

    app.register_blueprint(health.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(opportunities.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(saved.bp)
    app.register_blueprint(deadlines.bp)
    app.register_blueprint(watchlist.bp)
    app.register_blueprint(alerts.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(fit.bp)
    app.register_blueprint(reviews.bp)
    app.register_blueprint(literature.bp)
    app.register_blueprint(match.bp)
    app.register_blueprint(admin.bp)

    from . import cli, models  # noqa: F401

    cli.register(app)
    return app
