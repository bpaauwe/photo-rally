import os
import secrets
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext


def new_public_id():
    """Random token for participant URLs and the mark API (not derived from creation order)."""
    return secrets.token_hex(8)


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


def _migrate(db):
    """Bring a database from an earlier skeleton up to date (CREATE IF NOT EXISTS won't)."""
    def cols(table):
        return {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
    inst = cols("instruction")
    if inst and "mileage" not in inst:      # first-skeleton layout, never held real data
        db.execute("DROP TABLE instruction")
    rally = cols("rally")
    def add_column(table, existing, name, ddl):
        if existing and name not in existing:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            except sqlite3.OperationalError:    # another worker added it first
                pass
    add_column("rally", rally, "subtitle", "TEXT NOT NULL DEFAULT ''")
    add_column("rally", rally, "event_date", "TEXT NOT NULL DEFAULT ''")
    add_column("object", cols("object"), "spread_m", "REAL")
    add_column("object", cols("object"), "public_id", "TEXT")
    db.commit()


def init_db():
    os.makedirs(os.path.dirname(current_app.config["DATABASE"]), exist_ok=True)
    os.makedirs(current_app.config["PHOTO_DIR"], exist_ok=True)
    _migrate(get_db())
    schema = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(schema) as f:
        get_db().executescript(f.read())
    db = get_db()
    for (oid,) in db.execute("SELECT id FROM object WHERE public_id IS NULL").fetchall():   # spots from before tokens
        db.execute("UPDATE object SET public_id = ? WHERE id = ?", (new_public_id(), oid))
    db.commit()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create tables (safe to re-run)."""
    init_db()
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
