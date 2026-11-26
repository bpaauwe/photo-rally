"""Printable team cards: one QR code per team (opens a join confirmation), plus an event QR."""
from flask import Blueprint, abort, render_template, request

from . import links
from .auth import organizer_required
from .db import get_db
from .services import qr

PER_PAGE = (2, 4, 6, 8)          # cards per printed sheet; each has its own layout in the template
DEFAULT_PER = 6

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

    per = request.args.get("per", type=int)
    per = per if per in PER_PAGE else DEFAULT_PER

    join_url = f"{base}/play/join"
    items = []
    if show in ("event", "all"):
        items.append({"kind": "event", "svg": qr.svg(join_url, "QR code for the rally app")})
    if show in ("teams", "all"):
        rows = db.execute("SELECT * FROM team WHERE rally_id = ? ORDER BY name", (rally_id,)).fetchall()
        for t in rows:
            if team_id is None or t["id"] == team_id:
                items.append({"kind": "team", "team": t,
                              "svg": qr.svg(f"{base}/play/join/{t['join_code']}", f"QR code to join {t['name']}")})
    sheets = [items[i:i + per] for i in range(0, len(items), per)]      # one printed page each
    return render_template(
        "admin/team_cards.html", rally=rally, sheets=sheets, n_items=len(items), per=per, per_options=PER_PAGE,
        show=show, team_id=team_id, base=base, bad_base=bool(typed) and links.clean_base(typed) is None,
        secure=links.is_secure_enough(base), join_display=join_url.split("://", 1)[1])
