from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, migrate


def create_app(config: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    if app.config["SESSION_COOKIE_SECURE"] and app.config["SECRET_KEY"] == "dev":
        raise RuntimeError("set SECRET_KEY before running in production")
    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)

    from .blueprints import (
        alerts,
        auth,
        deadlines,
        documents,
        fit,
        health,
        literature,
        match,
        opportunities,
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
    app.register_blueprint(literature.bp)
    app.register_blueprint(match.bp)

    from . import cli, models  # noqa: F401

    cli.register(app)
    return app
