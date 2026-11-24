import functools

import click
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


@click.command("create-user")
@click.argument("username")
@click.password_option()
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
