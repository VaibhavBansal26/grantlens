from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db


def create_app(config: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    CORS(app)
    db.init_app(app)

    from .blueprints import health

    app.register_blueprint(health.bp)
    return app
