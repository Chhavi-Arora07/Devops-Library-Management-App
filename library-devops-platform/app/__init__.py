"""Library management system."""
from flask import Flask

from .config import Config
from .db import Database
from .observability import init_observability
from .routes import bp


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__)
    app.config["LIBRARY"] = config
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    app.extensions["db"] = Database(config.database_url)
    init_observability(app)
    app.register_blueprint(bp)
    return app
