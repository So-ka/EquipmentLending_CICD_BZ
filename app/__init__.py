import os
from pathlib import Path

from flask import Flask, g

from . import db
from .api import api, register_error_handlers
from .web import web


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or db.db_path()
    # Only used to sign flash messages; set SECRET_KEY in real deployments.
    app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.json.sort_keys = False
    app.config["OPENAPI_PATH"] = Path(__file__).resolve().parent.parent / "openapi.yaml"

    db.init_db(app.config["DB_PATH"])

    @app.before_request
    def _open_db():
        g.db = db.connect(app.config["DB_PATH"])

    @app.teardown_request
    def _close_db(exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    register_error_handlers(app)
    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(web)
    return app
