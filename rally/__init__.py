import os

from flask import Flask, redirect, send_from_directory, url_for

from . import admin, auth, cards, db, objects, play, results, sheets
from .services import instructions
from .config import INSTANCE_DIR, Config


def create_app(config=None):
    app = Flask(__name__, instance_path=INSTANCE_DIR)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.init_db()        # create/upgrade tables at startup; safe to repeat
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(play.bp)
    app.register_blueprint(sheets.bp)
    app.register_blueprint(objects.bp)
    app.register_blueprint(results.bp)
    app.register_blueprint(cards.bp)
    app.register_blueprint(objects.photo_bp)
    app.add_template_filter(instructions.rich, "rich")
    app.add_template_filter(instructions.css_text, "css_text")
    app.add_template_filter(instructions.pretty_date, "pretty_date")
    app.add_template_filter(results.fmt_m, "m")
    app.add_template_filter(results.compass, "compass")

    @app.route("/favicon.ico")
    def favicon():
        """Browsers ask for /favicon.ico at the site root even when a <link> points elsewhere."""
        return send_from_directory(os.path.join(app.static_folder, "icons"), "favicon.ico",
                                   mimetype="image/x-icon")

    @app.errorhandler(413)
    def too_large(_e):
        return "That upload is too large (limit 8 MB).", 413

    @app.route("/")
    def index():
        return redirect(url_for("play.join"))

    return app
