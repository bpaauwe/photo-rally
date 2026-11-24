"""Scoring results: standings, per-team and per-object detail, bias check, CSV export."""
import csv
import io
import re
from collections import defaultdict
from statistics import mean, median

from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   url_for, request)

from .auth import organizer_required
from .db import get_db
from .services import scoring
from .services.geo import reference_point

bp = Blueprint("results", __name__, url_prefix="/admin/rally/<int:rally_id>/results")

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(deg):
    return COMPASS[int((deg + 22.5) // 45) % 8]


def fmt_m(x):
    if x is None:
        return "\u2014"
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def compute(rally):
    """Everything the results pages need, derived from raw marks on every call."""
    db, rid = get_db(), rally["id"]
    objects = db.execute(
        "SELECT * FROM object WHERE rally_id = ? "
        "ORDER BY (code GLOB '[0-9]*') DESC, CAST(code AS INTEGER), code", (rid,)).fetchall()
    scored = [o for o in objects if reference_point(o)]
    teams = db.execute("SELECT * FROM team WHERE rally_id = ? ORDER BY name", (rid,)).fetchall()
    marks = db.execute("SELECT m.* FROM mark m JOIN team t ON t.id = m.team_id WHERE t.rally_id = ?",
                       (rid,)).fetchall()
    by_team, by_pair = defaultdict(list), defaultdict(list)
    for m in marks:
        by_team[m["team_id"]].append(m)
        by_pair[(m["team_id"], m["object_id"])].append(m)

    rules = dict(cap_m=rally["cap_m"], missing_penalty_m=rally["missing_penalty_m"],
                 round_to_m=rally["round_to_m"], mark_policy=rally["mark_policy"])
    results = {t["id"]: scoring.score_team(scored, by_team[t["id"]], **rules) for t in teams}
    team_by_id = {t["id"]: t for t in teams}
    ranked = [{**r, "team": team_by_id[r["team_id"]]}
              for r in scoring.with_ranks(scoring.rank_teams(results))]
    rows_by = {tid: {r["object_id"]: r for r in res["objects"]} for tid, res in results.items()}

    per_object = {}
    for o in scored:
        ref = reference_point(o)
        errs = [rows_by[t["id"]][o["id"]]["error_m"] for t in teams if not rows_by[t["id"]][o["id"]]["missing"]]
        last_pts = []
        for t in teams:      # bias uses each team's last mark so 'best mark' scoring can't hide an offset
            ms = by_pair.get((t["id"], o["id"]))
            if ms:
                last = scoring.pick_mark(ms, ref, "last")
                last_pts.append((last["lat"], last["lon"]))
        per_object[o["id"]] = {"ref": ref, "n_marked": len(errs), "mean": mean(errs) if errs else None,
                               "median": median(errs) if errs else None,
                               "bias": scoring.bias_stats(ref, last_pts)}
    return {"rules": rules, "objects": scored, "n_unscored": len(objects) - len(scored), "teams": teams,
            "team_by_id": team_by_id, "ranked": ranked, "results": results, "rows_by": rows_by,
            "per_object": per_object}


def _rally(rally_id):
    r = get_db().execute("SELECT * FROM rally WHERE id = ?", (rally_id,)).fetchone()
    if r is None:
        abort(404)
    return r


@bp.route("/")
@organizer_required
def index(rally_id):
    rally = _rally(rally_id)
    return render_template("admin/results.html", rally=rally, d=compute(rally))


@bp.route("/team/<int:tid>")
@organizer_required
def team(rally_id, tid):
    rally = _rally(rally_id)
    d = compute(rally)
    if tid not in d["team_by_id"]:
        abort(404)
    entry = next(r for r in d["ranked"] if r["team_id"] == tid)
    return render_template("admin/results_team.html", rally=rally, d=d, entry=entry)


@bp.route("/object/<int:oid>")
@organizer_required
def object_detail(rally_id, oid):
    rally = _rally(rally_id)
    d = compute(rally)
    obj = next((o for o in d["objects"] if o["id"] == oid), None)
    if obj is None:
        abort(404)
    stats = d["per_object"][oid]
    rows = [{"team": r["team"], "row": d["rows_by"][r["team_id"]][oid]} for r in d["ranked"]]
    marks = [{"team": x["team"]["name"], "lat": x["row"]["lat"], "lon": x["row"]["lon"],
              "err": float(f"{x['row']['error_m']:.1f}"), "capped": x["row"]["capped"]}
             for x in rows if not x["row"]["missing"]]
    bias = stats["bias"]
    map_data = {"ref": {"lat": stats["ref"][0], "lon": stats["ref"][1]},
                "orig": {"lat": obj["lat"], "lon": obj["lon"]} if obj["adj_lat"] is not None and obj["lat"] is not None else None,
                "adjusted": obj["adj_lat"] is not None, "marks": marks,
                "suggested": {"lat": bias["suggested"][0], "lon": bias["suggested"][1]} if bias else None}
    return render_template("admin/results_object.html", rally=rally, d=d, obj=obj, stats=stats,
                           rows=rows, map_data=map_data)


@bp.route("/object/<int:oid>/adjust", methods=("POST",))
@organizer_required
def adjust(rally_id, oid):
    """Move the scoring pin to the median of the teams' marks, or put it back. Scores update on read."""
    rally = _rally(rally_id)
    d = compute(rally)
    obj = next((o for o in d["objects"] if o["id"] == oid), None)
    if obj is None:
        abort(404)
    db = get_db()
    if request.form.get("action") == "apply":
        bias = d["per_object"][oid]["bias"]
        if not bias:
            flash("No marks to base an adjustment on.")
        else:
            db.execute("UPDATE object SET adj_lat = ?, adj_lon = ? WHERE id = ?", (*bias["suggested"], oid))
            db.commit()
            flash(f"Pin for {obj['code']} moved to the median of the marks. Scores have been recalculated.")
    elif request.form.get("action") == "clear":
        db.execute("UPDATE object SET adj_lat = NULL, adj_lon = NULL WHERE id = ?", (oid,))
        db.commit()
        flash(f"Adjustment for {obj['code']} removed. Scores have been recalculated.")
    return redirect(url_for("results.object_detail", rally_id=rally_id, oid=oid))


def _safe_cell(s):
    """Stop spreadsheet programs treating a team name as a formula."""
    s = str(s)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@bp.route("/export.csv")
@organizer_required
def export_csv(rally_id):
    rally = _rally(rally_id)
    d = compute(rally)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Rank", "Team", "Total (m)", "Missing", "Best (m)"] + [o["code"] for o in d["objects"]])
    for r in d["ranked"]:
        res = r["result"]
        by = d["rows_by"][r["team_id"]]
        w.writerow([r["rank"], _safe_cell(r["team"]["name"]), fmt_m(res["total"]), res["missing"],
                    fmt_m(res["best"]) if res["best"] is not None else ""]
                   + ["missing" if by[o["id"]]["missing"] else fmt_m(by[o["id"]]["error_m"]) for o in d["objects"]])
    name = re.sub(r"\s+", "_", re.sub(r"[^\w\- ]+", "", rally["name"])).strip("_") or "rally"
    return Response(out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}_results.csv"'})
