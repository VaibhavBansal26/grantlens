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

    from .blueprints import auth, deadlines, health, opportunities, saved, search

    app.register_blueprint(health.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(opportunities.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(saved.bp)
    app.register_blueprint(deadlines.bp)

    from . import cli, models  # noqa: F401

    cli.register(app)
    return app
