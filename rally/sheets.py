"""Instruction sheet: editor, import/export and print view."""
import re

from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   request, url_for)

from .auth import organizer_required
from .db import get_db
from .services import instructions as ins

bp = Blueprint("sheets", __name__, url_prefix="/admin/rally/<int:rally_id>/instructions")


def _rally(rally_id):
    r = get_db().execute("SELECT * FROM rally WHERE id = ?", (rally_id,)).fetchone()
    if r is None:
        abort(404)
    return r


def _load_rows(rally_id):
    return [dict(r) for r in get_db().execute(
        "SELECT kind, mileage, text, note FROM instruction WHERE rally_id = ? ORDER BY seq", (rally_id,))]


def _save_rows(rally_id, rows, header, subtitle, event_date):
    db = get_db()
    name = header.get("title")
    db.execute("DELETE FROM instruction WHERE rally_id = ?", (rally_id,))
    db.executemany(
        "INSERT INTO instruction (rally_id, seq, kind, mileage, text, note) VALUES (?,?,?,?,?,?)",
        [(rally_id, i, r["kind"], r["mileage"], r["text"], r["note"]) for i, r in enumerate(rows, 1)])
    db.execute("UPDATE rally SET subtitle = ?, event_date = ?, name = COALESCE(NULLIF(?, ''), name) WHERE id = ?",
               (header.get("subtitle", subtitle).strip(), header.get("date", event_date).strip(), name or "", rally_id))
    db.commit()


def _page(rally, text, errors=(), warnings=(), unsaved=False, subtitle=None, event_date=None):
    return render_template(
        "admin/instructions.html", rally=rally, text=text, errors=errors, warnings=warnings,
        unsaved=unsaved, subtitle=rally["subtitle"] if subtitle is None else subtitle,
        event_date=rally["event_date"] if event_date is None else event_date,
        preview=ins.build_rows(_load_rows(rally["id"])))


@bp.route("/", methods=("GET", "POST"))
@organizer_required
def edit(rally_id):
    rally = _rally(rally_id)
    if request.method == "GET":
        return _page(rally, ins.to_text(_load_rows(rally_id)))
    text = request.form.get("sheet", "")
    subtitle, event_date = request.form.get("subtitle", ""), request.form.get("event_date", "")
    rows, header, errors, warnings = ins.parse_sheet(text)
    if errors:
        return _page(rally, text, errors, warnings, unsaved=True, subtitle=subtitle, event_date=event_date)
    _save_rows(rally_id, rows, header, subtitle, event_date)
    n = sum(1 for r in rows if r["kind"] == "instr")
    flash(f"Saved {n} instructions.")
    for w in warnings[:5]:
        flash(w)
    return redirect(url_for("sheets.edit", rally_id=rally_id))


@bp.route("/import", methods=("POST",))
@organizer_required
def import_file(rally_id):
    """Load a .txt or .csv into the editor. Nothing is saved until the organizer presses Save."""
    rally = _rally(rally_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a .txt or .csv file first.")
        return redirect(url_for("sheets.edit", rally_id=rally_id))
    data = f.read()
    try:
        raw = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = data.decode("latin-1")
    text = ins.csv_to_text(raw) if f.filename.lower().endswith(".csv") else raw.replace("\r\n", "\n")
    flash(f"Loaded {f.filename}. Review it, then press Save.")
    return _page(rally, text, unsaved=True)


@bp.route("/export.txt")
@organizer_required
def export_txt(rally_id):
    rally = _rally(rally_id)
    header = {"title": rally["name"], "subtitle": rally["subtitle"], "date": rally["event_date"]}
    name = re.sub(r"\s+", "_", re.sub(r"[^\w\- ]+", "", rally["name"])).strip("_") or "rally"
    return Response(ins.to_text(_load_rows(rally_id), header), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.txt"'})


@bp.route("/print")
@organizer_required
def print_view(rally_id):
    rally = _rally(rally_id)
    show_leg = request.args.get("leg", "1") == "1"
    organizer = request.args.get("notes", "0") == "1"
    label = "Organizer Copy" if organizer else "Route Instructions"
    return render_template(
        "admin/sheet_print.html", rally=rally, rows=ins.build_rows(_load_rows(rally_id)),
        show_leg=show_leg, organizer=organizer, label=label,
        footer_left=f"{rally['name']} - {label}", footer_right=ins.pretty_date(rally["event_date"]))
