"""Flask application factory."""
import logging
import os

from flask import Flask

from . import db


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["JSON_SORT_KEYS"] = False

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    )

    db.init_db()

    from . import routes
    app.register_blueprint(routes.bp)
    return app
