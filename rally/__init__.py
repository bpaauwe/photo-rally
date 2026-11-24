from flask import Flask, redirect, url_for

from . import admin, auth, db, play, sheets
from .services import instructions
from .config import INSTANCE_DIR, Config


def create_app(config=None):
    app = Flask(__name__, instance_path=INSTANCE_DIR)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(play.bp)
    app.register_blueprint(sheets.bp)
    app.add_template_filter(instructions.rich, "rich")
    app.add_template_filter(instructions.css_text, "css_text")
    app.add_template_filter(instructions.pretty_date, "pretty_date")

    @app.route("/")
    def index():
        return redirect(url_for("play.join"))

    return app
