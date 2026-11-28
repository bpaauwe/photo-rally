"""Pure scoring functions: no database or Flask imports, so they are easy to test.

Marks and objects are plain mappings (sqlite3.Row or dict). Scores are computed
on read from raw marks, so changing a rule or an organizer pin re-scores everything.
"""
import math
from statistics import median

from .geo import haversine_m, move, offset_m, reference_point


def round_to(value, step):
    return value if not step else round(value / step) * step


def _get(m, key):
    try:
        return m[key]
    except (KeyError, IndexError):
        return None


def pick_mark(marks, ref, policy):
    """Choose which of a team's marks for one object counts."""
    if not marks:
        return None
    ordered = sorted(marks, key=lambda m: (m["server_ts"], m["id"]))
    if policy == "first":
        return ordered[0]
    if policy == "best":
        return min(ordered, key=lambda m: haversine_m(ref[0], ref[1], m["lat"], m["lon"]))
    return ordered[-1]  # 'last'


def score_team(objects, marks, *, cap_m, missing_penalty_m, round_to_m=0, mark_policy="last"):
    """Return {'total', 'missing', 'best', 'objects': [...]} for one team.

    `marks` is every mark the team has made (any object). Objects with no
    organizer coordinate are skipped, since they cannot be scored yet.
    """
    by_obj = {}
    for m in marks:
        by_obj.setdefault(m["object_id"], []).append(m)

    rows, total, missing = [], 0.0, 0
    for obj in objects:
        ref = reference_point(obj)
        if ref is None:
            continue
        mine = by_obj.get(obj["id"], [])
        chosen = pick_mark(mine, ref, mark_policy)
        row = {"object_id": obj["id"], "code": obj["code"], "name": _get(obj, "name"), "n_marks": len(mine),
               "lat": None, "lon": None, "accuracy_m": None, "server_ts": None, "capped": False}
        if chosen is None:
            error, raw, is_missing = missing_penalty_m, None, True
            missing += 1
        else:
            raw = round_to(haversine_m(ref[0], ref[1], chosen["lat"], chosen["lon"]), round_to_m)
            error, is_missing = min(raw, cap_m), False
            row.update(lat=chosen["lat"], lon=chosen["lon"], accuracy_m=_get(chosen, "accuracy_m"),
                       server_ts=_get(chosen, "server_ts"), capped=raw > cap_m)
        total += error
        row.update(raw_m=raw, error_m=error, missing=is_missing)
        rows.append(row)

    scored = [r["error_m"] for r in rows if not r["missing"]]
    return {"total": total, "missing": missing,
            "best": min(scored) if scored else None, "objects": rows}


def _rank_key(res):
    return (res["total"], res["missing"], res["best"] if res["best"] is not None else float("inf"))


def rank_teams(results):
    """results: {team_id: score_team(...)}. Sort by total, then fewer missing, then best single."""
    return sorted(results.items(), key=lambda kv: _rank_key(kv[1]))


def with_ranks(ordered):
    """Add competition ranks (1, 2, 2, 4) to rank_teams output. Teams equal on every tiebreak share a rank."""
    out, prev_key, rank = [], None, 0
    for i, (tid, res) in enumerate(ordered, 1):
        key = _rank_key(res)
        if key != prev_key:
            rank = i
        out.append({"rank": rank, "team_id": tid, "result": res, "tied": False})
        prev_key = key
    for item in out:
        item["tied"] = sum(1 for o in out if o["rank"] == item["rank"]) > 1
    return out


def bias_stats(ref, points):
    """Is the organizer's pin systematically off? points: [(lat, lon)] of teams' marks.

    Looks at where the typical (median) mark sits relative to the pin. If it is well away from the
    pin compared with how scattered the marks are, the pin itself is a likely culprit.
    """
    if not points:
        return None
    offs = [offset_m(ref[0], ref[1], la, lo) for la, lo in points]
    mx, my = median(o[0] for o in offs), median(o[1] for o in offs)
    bias = math.hypot(mx, my)
    spread = median(math.hypot(o[0] - mx, o[1] - my) for o in offs)
    return {"n": len(points), "east_m": mx, "north_m": my, "bias_m": bias, "spread_m": spread,
            "bearing_deg": (math.degrees(math.atan2(mx, my)) + 360) % 360,
            "suggested": move(ref[0], ref[1], mx, my),
            "flagged": len(points) >= 5 and bias >= 15 and bias >= 0.75 * spread}
