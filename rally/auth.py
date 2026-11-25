import functools
import sqlite3

import click
from flask.cli import with_appcontext
from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.before_app_request
def load_user():
    uid = session.get("user_id")
    g.user = (
        get_db().execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
        if uid else None
    )


def organizer_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        user = get_db().execute(
            "SELECT * FROM user WHERE username = ?", (request.form["username"],)
        ).fetchone()
        if user and check_password_hash(user["pw_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            nxt = request.args.get("next", "")
            # only allow same-site relative redirects
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("admin.rallies")
            return redirect(nxt)
        flash("Username or password is incorrect.")
    return render_template("login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


MIN_PASSWORD = 8
MAX_USERNAME = 64


@bp.route("/account", methods=("GET", "POST"))
@organizer_required
def account():
    """Change your own username or password. Both need the current password."""
    if request.method == "POST":
        action = request.form.get("action")
        db = get_db()
        if not check_password_hash(g.user["pw_hash"], request.form.get("current_password", "")):
            flash("Your current password is incorrect.")
        elif action == "username":
            new = request.form.get("username", "").strip()
            if not new or len(new) > MAX_USERNAME:
                flash(f"Choose a username of 1 to {MAX_USERNAME} characters.")
            elif new == g.user["username"]:
                flash("That is already your username.")
            else:
                try:
                    db.execute("UPDATE user SET username = ? WHERE id = ?", (new, g.user["id"]))
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That username is already taken.")
                else:
                    flash(f"Your username is now '{new}'.")
                    return redirect(url_for("auth.account"))
        elif action == "password":
            new, again = request.form.get("new_password", ""), request.form.get("confirm_password", "")
            if len(new) < MIN_PASSWORD:
                flash(f"Choose a password of at least {MIN_PASSWORD} characters.")
            elif new != again:
                flash("The two new passwords don't match.")
            else:
                db.execute("UPDATE user SET pw_hash = ? WHERE id = ?", (generate_password_hash(new), g.user["id"]))
                db.commit()
                uid = g.user["id"]
                session.clear()                    # fresh session after a credential change
                session["user_id"] = uid
                session.permanent = True
                flash("Your password has been changed.")
                return redirect(url_for("auth.account"))
        else:
            flash("Unknown action.")
    return render_template("account.html")


@click.command("set-password")
@click.argument("username")
@click.password_option()
@with_appcontext
def set_password_command(username, password):
    """Set a new password for an organizer (use this if you've forgotten yours)."""
    db = get_db()
    cur = db.execute("UPDATE user SET pw_hash = ? WHERE username = ?",
                     (generate_password_hash(password), username))
    db.commit()
    if cur.rowcount == 0:
        raise click.ClickException(f"No organizer named '{username}'.")
    click.echo(f"Password updated for '{username}'.")


@click.command("create-user")
@click.argument("username")
@click.password_option()
@with_appcontext
def create_user_command(username, password):
    """Create an organizer account."""
    get_db().execute(
        "INSERT INTO user (username, pw_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    get_db().commit()
    click.echo(f"Created organizer '{username}'.")


@bp.record_once
def _register_cli(state):
    state.app.cli.add_command(create_user_command)
    state.app.cli.add_command(set_password_command)
