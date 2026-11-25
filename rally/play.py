"""Participant side: join by team code, view instructions and objects, mark positions."""
import functools
import math
import os
import re
import sqlite3

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

from .db import get_db
from . import results as results_mod
from .services import instructions as ins

bp = Blueprint("play", __name__, url_prefix="/play")

UUID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# Never select an object's coordinates here: participants must not see the organizer's pins.
OBJECT_LIST_SQL = ("SELECT id, code, name, photo_path FROM object "
                   "WHERE rally_id = ? AND (lat IS NOT NULL OR adj_lat IS NOT NULL) "
                   "ORDER BY (code GLOB '[0-9]*') DESC, CAST(code AS INTEGER), code")


@bp.before_app_request
def load_team():
    tid = session.get("team_id")
    g.team = (
        get_db().execute(
            "SELECT t.*, r.name AS rally_name, r.status AS rally_status "
            "FROM team t JOIN rally r ON r.id = t.rally_id WHERE t.id = ?", (tid,)
        ).fetchone() if tid else None
    )


def team_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.team is None:
            return redirect(url_for("play.join"))
        return view(**kwargs)
    return wrapped


def _closed_for_viewing():
    return g.team["rally_status"] == "draft"


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
@team_required
def home():
    objs, marks = [], {}
    if not _closed_for_viewing():
        db = get_db()
        objs = db.execute(OBJECT_LIST_SQL, (g.team["rally_id"],)).fetchall()
        marks = {r["object_id"]: r["n"] for r in db.execute(
            "SELECT object_id, COUNT(*) AS n FROM mark WHERE team_id = ? GROUP BY object_id", (g.team["id"],))}
    return render_template("play/home.html", objs=objs, marks=marks)


@bp.route("/instructions")
@team_required
def instructions():
    if _closed_for_viewing():
        return redirect(url_for("play.home"))
    rows = [dict(r) for r in get_db().execute(
        "SELECT kind, mileage, text, note FROM instruction WHERE rally_id = ? ORDER BY seq",
        (g.team["rally_id"],))]
    return render_template("play/instructions.html", rows=ins.build_rows(rows))


@bp.route("/object/<int:oid>")
@team_required
def object_page(oid):
    if _closed_for_viewing():
        return redirect(url_for("play.home"))
    db = get_db()
    obj = db.execute(
        'SELECT id, code, name, "desc", where_note, photo_path FROM object '
        "WHERE id = ? AND rally_id = ? AND (lat IS NOT NULL OR adj_lat IS NOT NULL)",
        (oid, g.team["rally_id"])).fetchone()
    if obj is None:
        abort(404)
    n = db.execute("SELECT COUNT(*) FROM mark WHERE team_id = ? AND object_id = ?",
                   (g.team["id"], oid)).fetchone()[0]
    return render_template("play/object.html", obj=obj, n_marks=n,
                           can_mark=g.team["rally_status"] == "running")


@bp.route("/sw.js")
def service_worker():
    """Served from /play/ so its scope covers the participant pages. Never cached, so updates arrive."""
    resp = send_from_directory(os.path.join(current_app.static_folder, "js"), "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.route("/manifest.webmanifest")
def manifest():
    icon = lambda f, size: {"src": url_for("static", filename=f"icons/{f}"), "sizes": f"{size}x{size}", "type": "image/png"}
    resp = jsonify({"name": "Photo Rally", "short_name": "Photo Rally", "start_url": url_for("play.home"),
                    "scope": url_for("play.home"), "display": "standalone", "theme_color": "#ffffff",
                    "background_color": "#ffffff",
                    "icons": [icon("android-chrome-192x192.png", 192), icon("android-chrome-512x512.png", 512)]})
    resp.mimetype = "application/manifest+json"
    return resp


@bp.route("/offline-manifest")
def offline_manifest():
    """URLs the phone should save so the rally works without signal. Contains no coordinates."""
    if g.team is None:
        return jsonify(ok=False), 401
    pages, media = [url_for("play.home")], []
    if not _closed_for_viewing():
        pages.append(url_for("play.instructions"))
        for o in get_db().execute(OBJECT_LIST_SQL, (g.team["rally_id"],)):
            pages.append(url_for("play.object_page", oid=o["id"]))
            if o["photo_path"]:
                media.append(url_for("photo.get", name=o["photo_path"]))
        if g.team["rally_status"] == "final":
            pages.append(url_for("play.results"))
    assets = [url_for("static", filename=f) for f in
              ("css/style.css", "js/gps.js", "js/play.js", "icons/android-chrome-192x192.png", "icons/apple-touch-icon.png")]
    resp = jsonify(ok=True, pages=pages, media=media, assets=assets)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/results")
@team_required
def results():
    """Standings, shown to teams only once the organizer sets the rally to 'final'."""
    if g.team["rally_status"] != "final":
        return redirect(url_for("play.home"))
    db = get_db()
    rally = db.execute("SELECT * FROM rally WHERE id = ?", (g.team["rally_id"],)).fetchone()
    d = results_mod.compute(rally)
    mine = d["results"][g.team["id"]]
    return render_template("play/results.html", ranked=d["ranked"], mine=mine,
                           names={o["id"]: o["name"] for o in d["objects"]})


def _fail(msg, code=400):
    return jsonify(ok=False, error=msg), code


def _number(data, key, lo, hi, required=True):
    v = data.get(key)
    if v is None and not required:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(key)
    return float(v)


@bp.route("/mark", methods=("POST",))
def mark():
    """Store one mark. Idempotent on client_uuid so phones can safely retry."""
    if g.team is None:
        return _fail("Join your team first.", 401)
    if g.team["rally_status"] != "running":
        return _fail("Marking isn't open for this rally.", 403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _fail("Bad request.")
    try:
        lat = _number(data, "lat", -90, 90)
        lon = _number(data, "lon", -180, 180)
        acc = _number(data, "accuracy_m", 0, 100000, required=False)
        n_samples = _number(data, "n_samples", 0, 100000, required=False)
        oid = _number(data, "object_id", 1, 2**31)
    except ValueError as e:
        return _fail(f"Invalid {e}.")
    uuid = data.get("client_uuid")
    if not isinstance(uuid, str) or not UUID_RE.match(uuid):
        return _fail("Invalid client_uuid.")
    client_ts = data.get("client_ts")
    client_ts = client_ts[:40] if isinstance(client_ts, str) else None

    db = get_db()
    if db.execute("SELECT 1 FROM object WHERE id = ? AND rally_id = ?",
                  (int(oid), g.team["rally_id"])).fetchone() is None:
        return _fail("Unknown object.")
    try:
        db.execute("INSERT INTO mark (team_id, object_id, lat, lon, accuracy_m, n_samples, client_ts, client_uuid) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (g.team["id"], int(oid), lat, lon, acc, None if n_samples is None else int(n_samples),
                    client_ts, uuid))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        same = db.execute("SELECT 1 FROM mark WHERE client_uuid = ? AND team_id = ? AND object_id = ?",
                          (uuid, g.team["id"], int(oid))).fetchone()
        if not same:
            return _fail("Duplicate id.", 409)
    n = db.execute("SELECT COUNT(*) FROM mark WHERE team_id = ? AND object_id = ?",
                   (g.team["id"], int(oid))).fetchone()[0]
    return jsonify(ok=True, marks=n)
