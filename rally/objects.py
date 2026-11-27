"""Photo spot editor: photo, organizer GPS capture, adjusted pin, link to the instruction sheet."""
import os
import secrets
import sqlite3

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, send_from_directory, url_for)

from .auth import organizer_required
from .db import get_db
from .services import instructions as ins

bp = Blueprint("objects", __name__, url_prefix="/admin/rally/<int:rally_id>/objects")
photo_bp = Blueprint("photo", __name__)

COLS = ('code, name, "desc", where_note, lat, lon, acc_m, samples, spread_m, '
        'adj_lat, adj_lon, after_instruction_seq')


# --- photos -----------------------------------------------------------------
def sniff_image(data):
    """File extension for JPEG / PNG / WebP bytes, else None (we never trust the filename)."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_photo(fs):
    data = fs.read()
    ext = sniff_image(data)
    if not ext:
        raise ValueError("That file isn't a JPEG, PNG or WebP image.")
    name = secrets.token_hex(16) + ext          # unguessable, so photos can't be enumerated
    os.makedirs(current_app.config["PHOTO_DIR"], exist_ok=True)
    with open(os.path.join(current_app.config["PHOTO_DIR"], name), "wb") as f:
        f.write(data)
    return name


def remove_photo(name):
    if name:
        try:
            os.remove(os.path.join(current_app.config["PHOTO_DIR"], os.path.basename(name)))
        except OSError:
            pass


@photo_bp.route("/photo/<name>")
def get(name):
    """Organizers, and teams in the same rally, may view a photo spot's photo."""
    obj = get_db().execute("SELECT rally_id FROM object WHERE photo_path = ?", (name,)).fetchone()
    if obj is None:
        abort(404)
    if g.user is None and not (g.team is not None and g.team["rally_id"] == obj["rally_id"]):
        abort(404)
    resp = send_from_directory(current_app.config["PHOTO_DIR"], name)
    resp.headers["Cache-Control"] = "private, max-age=86400"   # filenames change when the photo does
    return resp


# --- helpers ----------------------------------------------------------------
def _rally(rally_id):
    r = get_db().execute("SELECT * FROM rally WHERE id = ?", (rally_id,)).fetchone()
    if r is None:
        abort(404)
    return r


def _object(rally_id, oid):
    o = get_db().execute("SELECT * FROM object WHERE id = ? AND rally_id = ?", (oid, rally_id)).fetchone()
    if o is None:
        abort(404)
    return o


def instruction_choices(rally_id):
    """(seq, label) for each numbered instruction, labelled with its sheet number and mileage."""
    rows = get_db().execute(
        "SELECT seq, kind, mileage, text FROM instruction WHERE rally_id = ? ORDER BY seq", (rally_id,)).fetchall()
    out, n = [], 0
    for r in rows:
        if r["kind"] != "instr":
            continue
        n += 1
        mile = "" if r["mileage"] is None else f" ({r['mileage']:.2f} mi)"
        out.append((r["seq"], f"#{n}{mile} {ins.split_lines(r['text'])[0][:50]}"))
    return out


def _num(form, key, lo, hi, label, errors):
    v = form.get(key, "").strip()
    if not v:
        return None
    try:
        x = float(v)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if not lo <= x <= hi:
        errors.append(f"{label} must be between {lo:g} and {hi:g}.")
        return None
    return x


def _parse(form):
    errors = []
    v = {"code": form.get("code", "").strip(), "name": form.get("name", "").strip(),
         "desc": form.get("desc", "").strip(), "where_note": form.get("where_note", "").strip()}
    if not v["code"]:
        errors.append("Give the photo spot a code (for example A or 7).")
    if not v["name"]:
        errors.append("Give the photo spot a name.")
    v["lat"] = _num(form, "lat", -90, 90, "Latitude", errors)
    v["lon"] = _num(form, "lon", -180, 180, "Longitude", errors)
    v["adj_lat"] = _num(form, "adj_lat", -90, 90, "Adjusted latitude", errors)
    v["adj_lon"] = _num(form, "adj_lon", -180, 180, "Adjusted longitude", errors)
    v["acc_m"] = _num(form, "acc_m", 0, 100000, "Accuracy", errors)
    v["spread_m"] = _num(form, "spread_m", 0, 100000, "Spread", errors)
    n = _num(form, "samples", 0, 100000, "Samples", errors)
    v["samples"] = None if n is None else int(n)
    s = _num(form, "after_instruction_seq", 1, 100000, "Instruction", errors)
    v["after_instruction_seq"] = None if s is None else int(s)
    if (v["lat"] is None) != (v["lon"] is None):
        errors.append("Enter both latitude and longitude, or neither.")
    if (v["adj_lat"] is None) != (v["adj_lon"] is None):
        errors.append("Enter both adjusted latitude and longitude, or neither.")
    return v, errors


def _form_page(rally, v, obj=None, errors=()):
    return render_template("admin/object_form.html", rally=rally, v=v, obj=obj, errors=errors,
                           choices=instruction_choices(rally["id"]))


# --- routes -----------------------------------------------------------------
@bp.route("/")
@organizer_required
def index(rally_id):
    rally = _rally(rally_id)
    objs = get_db().execute(
        "SELECT * FROM object WHERE rally_id = ? "
        "ORDER BY (code GLOB '[0-9]*') DESC, CAST(code AS INTEGER), code", (rally_id,)).fetchall()
    seq_label = dict(instruction_choices(rally_id))
    return render_template("admin/objects.html", rally=rally, objs=objs, seq_label=seq_label)


@bp.route("/new", methods=("GET", "POST"))
@organizer_required
def new(rally_id):
    rally = _rally(rally_id)
    if request.method == "GET":
        return _form_page(rally, {})
    v, errors = _parse(request.form)
    photo = request.files.get("photo")
    new_photo = None
    if not errors and photo and photo.filename:
        try:
            new_photo = save_photo(photo)
        except ValueError as e:
            errors.append(str(e))
    if errors:
        return _form_page(rally, request.form, errors=errors)
    db = get_db()
    try:
        db.execute(f"INSERT INTO object (rally_id, photo_path, {COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (rally_id, new_photo, v["code"], v["name"], v["desc"], v["where_note"], v["lat"], v["lon"],
                    v["acc_m"], v["samples"], v["spread_m"], v["adj_lat"], v["adj_lon"], v["after_instruction_seq"]))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        remove_photo(new_photo)
        return _form_page(rally, request.form, errors=[f"A photo spot with code '{v['code']}' already exists."])
    flash(f"Added photo spot {v['code']}.")
    return redirect(url_for("objects.index", rally_id=rally_id))


@bp.route("/<int:oid>", methods=("GET", "POST"))
@organizer_required
def edit(rally_id, oid):
    rally, obj = _rally(rally_id), _object(rally_id, oid)
    if request.method == "GET":
        return _form_page(rally, dict(obj), obj)
    v, errors = _parse(request.form)
    photo, old_photo, photo_path = request.files.get("photo"), obj["photo_path"], obj["photo_path"]
    new_photo = None
    if not errors and photo and photo.filename:
        try:
            new_photo = photo_path = save_photo(photo)
        except ValueError as e:
            errors.append(str(e))
    elif request.form.get("remove_photo"):
        photo_path = None
    if errors:
        return _form_page(rally, request.form, obj, errors)
    db = get_db()
    try:
        db.execute("UPDATE object SET photo_path=?, code=?, name=?, \"desc\"=?, where_note=?, lat=?, lon=?, "
                   "acc_m=?, samples=?, spread_m=?, adj_lat=?, adj_lon=?, after_instruction_seq=? WHERE id=?",
                   (photo_path, v["code"], v["name"], v["desc"], v["where_note"], v["lat"], v["lon"], v["acc_m"],
                    v["samples"], v["spread_m"], v["adj_lat"], v["adj_lon"], v["after_instruction_seq"], oid))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        remove_photo(new_photo)
        return _form_page(rally, request.form, obj, [f"A photo spot with code '{v['code']}' already exists."])
    if photo_path != old_photo:
        remove_photo(old_photo)
    flash(f"Saved photo spot {v['code']}.")
    return redirect(url_for("objects.index", rally_id=rally_id))


@bp.route("/<int:oid>/delete", methods=("POST",))
@organizer_required
def delete(rally_id, oid):
    obj = _object(rally_id, oid)
    db = get_db()
    db.execute("DELETE FROM object WHERE id = ?", (oid,))
    db.commit()
    remove_photo(obj["photo_path"])
    flash(f"Deleted photo spot {obj['code']}.")
    return redirect(url_for("objects.index", rally_id=rally_id))
