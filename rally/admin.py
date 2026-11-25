import secrets
import sqlite3

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from .auth import organizer_required
from .db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Unambiguous characters only (no 0/O, 1/I/L) so codes survive being read aloud.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_join_code(n=6):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def get_rally_or_404(rally_id):
    row = get_db().execute("SELECT * FROM rally WHERE id = ?", (rally_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/")
@organizer_required
def rallies():
    rows = get_db().execute("SELECT * FROM rally ORDER BY created_at DESC").fetchall()
    return render_template("admin/rallies.html", rallies=rows)


@bp.route("/rally/new", methods=("GET", "POST"))
@organizer_required
def rally_new():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Give the rally a name.")
        else:
            db = get_db()
            cur = db.execute("INSERT INTO rally (name) VALUES (?)", (name,))
            db.commit()
            return redirect(url_for("admin.rally_detail", rally_id=cur.lastrowid))
    return render_template("admin/rally_form.html")


@bp.route("/rally/<int:rally_id>")
@organizer_required
def rally_detail(rally_id):
    rally = get_rally_or_404(rally_id)
    db = get_db()
    teams = db.execute(
        "SELECT t.*, (SELECT COUNT(*) FROM mark m WHERE m.team_id = t.id) AS n_marks "
        "FROM team t WHERE rally_id = ? ORDER BY name", (rally_id,)).fetchall()
    n_obj = db.execute("SELECT COUNT(*) FROM object WHERE rally_id = ?", (rally_id,)).fetchone()[0]
    n_ins = db.execute("SELECT COUNT(*) FROM instruction WHERE rally_id = ? AND kind = 'instr'", (rally_id,)).fetchone()[0]
    return render_template("admin/rally_detail.html", rally=rally, teams=teams,
                           n_obj=n_obj, n_ins=n_ins)


MAX_NAME = 120


@bp.route("/rally/<int:rally_id>/rename", methods=("POST",))
@organizer_required
def rally_rename(rally_id):
    rally = get_rally_or_404(rally_id)
    name = request.form.get("name", "").strip()
    if not name or len(name) > MAX_NAME:
        flash(f"Choose a name of 1 to {MAX_NAME} characters.")
    elif name == rally["name"]:
        flash("That is already the name.")
    else:
        db = get_db()
        db.execute("UPDATE rally SET name = ? WHERE id = ?", (name, rally_id))
        db.commit()
        flash(f"Renamed to '{name}'.")
    return redirect(url_for("admin.rally_detail", rally_id=rally_id))


STATUSES = ("draft", "published", "running", "scoring", "final")


@bp.route("/rally/<int:rally_id>/status", methods=("POST",))
@organizer_required
def rally_status(rally_id):
    get_rally_or_404(rally_id)
    status = request.form.get("status")
    if status not in STATUSES:
        flash("Unknown status.")
    else:
        db = get_db()
        db.execute("UPDATE rally SET status = ? WHERE id = ?", (status, rally_id))
        db.commit()
        flash(f"Rally status is now '{status}'.")
    return redirect(url_for("admin.rally_detail", rally_id=rally_id))


@bp.route("/rally/<int:rally_id>/rules", methods=("POST",))
@organizer_required
def rally_rules(rally_id):
    get_rally_or_404(rally_id)
    back = redirect(url_for("admin.rally_detail", rally_id=rally_id))
    try:
        cap = float(request.form["cap_m"])
        pen = float(request.form["missing_penalty_m"])
        rnd = float(request.form["round_to_m"])
    except ValueError:
        flash("Distances must be numbers.")
        return back
    policy = request.form["mark_policy"]
    if policy not in ("first", "last", "best") or min(cap, pen, rnd) < 0 or pen < cap:
        flash("Check the rules: penalty must be at least the cap, and nothing negative.")
        return back
    db = get_db()
    db.execute("UPDATE rally SET cap_m=?, missing_penalty_m=?, round_to_m=?, mark_policy=? WHERE id=?",
               (cap, pen, rnd, policy, rally_id))
    db.commit()
    flash("Scoring rules saved.")
    return back


@bp.route("/rally/<int:rally_id>/teams", methods=("POST",))
@organizer_required
def team_add(rally_id):
    get_rally_or_404(rally_id)
    back = redirect(url_for("admin.rally_detail", rally_id=rally_id))
    name = request.form["name"].strip()
    if not name:
        flash("Give the team a name.")
        return back
    db = get_db()
    for _ in range(10):  # retry on the (unlikely) join-code collision
        try:
            db.execute("INSERT INTO team (rally_id, name, join_code) VALUES (?,?,?)",
                       (rally_id, name, new_join_code()))
            db.commit()
            break
        except sqlite3.IntegrityError as exc:
            db.rollback()
            if "team.name" in str(exc):
                flash(f"A team named '{name}' already exists.")
                break
    return back
