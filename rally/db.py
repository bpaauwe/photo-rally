import os
import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        if current_app.config["DB_WAL"]:
            db.execute("PRAGMA journal_mode = WAL")
        g.db = db
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(current_app.config["DATABASE"]), exist_ok=True)
    os.makedirs(current_app.config["PHOTO_DIR"], exist_ok=True)
    schema = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(schema) as f:
        get_db().executescript(f.read())


@click.command("init-db")
def init_db_command():
    """Create tables (safe to re-run)."""
    init_db()
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
