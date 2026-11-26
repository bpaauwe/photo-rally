"""Printable team cards: one QR code per team (opens a join confirmation), plus an event QR."""
from flask import Blueprint, abort, render_template, request

from . import links
from .auth import organizer_required
from .db import get_db
from .services import qr

bp = Blueprint("cards", __name__, url_prefix="/admin/rally/<int:rally_id>/cards")


@bp.route("/")
@organizer_required
def index(rally_id):
    db = get_db()
    rally = db.execute("SELECT * FROM rally WHERE id = ?", (rally_id,)).fetchone()
    if rally is None:
        abort(404)
    typed = request.args.get("base", "").strip()
    base = links.public_base(typed)
    show = request.args.get("show", "teams")
    if show not in ("teams", "event", "all"):
        show = "teams"
    team_id = request.args.get("team", type=int)

    teams = []
    if show in ("teams", "all"):
        rows = db.execute("SELECT * FROM team WHERE rally_id = ? ORDER BY name", (rally_id,)).fetchall()
        for t in rows:
            if team_id is None or t["id"] == team_id:
                url = f"{base}/play/join/{t['join_code']}"
                teams.append({"team": t, "svg": qr.svg(url, f"QR code to join {t['name']}")})
    join_url = f"{base}/play/join"
    return render_template(
        "admin/team_cards.html", rally=rally, teams=teams, show=show, team_id=team_id, base=base,
        bad_base=bool(typed) and links.clean_base(typed) is None, secure=links.is_secure_enough(base),
        join_url=join_url, join_display=join_url.split("://", 1)[1],
        event_svg=qr.svg(join_url, "QR code for the rally app") if show in ("event", "all") else None)
