from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)

from .db import get_db

bp = Blueprint("play", __name__, url_prefix="/play")


@bp.before_app_request
def load_team():
    tid = session.get("team_id")
    g.team = (
        get_db().execute(
            "SELECT t.*, r.name AS rally_name, r.status AS rally_status "
            "FROM team t JOIN rally r ON r.id = t.rally_id WHERE t.id = ?", (tid,)
        ).fetchone() if tid else None
    )


@bp.route("/join", methods=("GET", "POST"))
def join():
    if request.method == "POST":
        code = request.form["code"].strip().upper().replace(" ", "")
        team = get_db().execute("SELECT id FROM team WHERE join_code = ?", (code,)).fetchone()
        if team:
            session["team_id"] = team["id"]
            session.permanent = True
            return redirect(url_for("play.home"))
        flash("That code wasn't found. Check it and try again.")
    return render_template("play/join.html")


@bp.route("/")
def home():
    if g.team is None:
        return redirect(url_for("play.join"))
    # TODO: instructions, object list, mark flow
    return render_template("play/home.html")
