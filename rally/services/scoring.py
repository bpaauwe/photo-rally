"""Pure scoring functions: no database or Flask imports, so they are easy to test.

Marks and objects are plain mappings (sqlite3.Row or dict). Scores are computed
on read from raw marks, so changing a rule or an organizer pin re-scores everything.
"""
from .geo import haversine_m, reference_point


def round_to(value, step):
    return value if not step else round(value / step) * step


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
        chosen = pick_mark(by_obj.get(obj["id"], []), ref, mark_policy)
        if chosen is None:
            error, raw, is_missing = missing_penalty_m, None, True
            missing += 1
        else:
            raw = haversine_m(ref[0], ref[1], chosen["lat"], chosen["lon"])
            error, is_missing = min(round_to(raw, round_to_m), cap_m), False
        total += error
        rows.append({"object_id": obj["id"], "code": obj["code"], "raw_m": raw,
                     "error_m": error, "missing": is_missing})

    scored = [r["error_m"] for r in rows if not r["missing"]]
    return {"total": total, "missing": missing,
            "best": min(scored) if scored else None, "objects": rows}


def rank_teams(results):
    """results: {team_id: score_team(...)}. Sort by total, then fewer missing, then best single."""
    return sorted(results.items(),
                  key=lambda kv: (kv[1]["total"], kv[1]["missing"],
                                  kv[1]["best"] if kv[1]["best"] is not None else float("inf")))
