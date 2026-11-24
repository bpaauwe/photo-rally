import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rally.services.geo import haversine_m, move, offset_m
from rally.services.scoring import bias_stats, rank_teams, score_team, with_ranks

# 0.001 degrees of latitude is about 111.2 m
D = 0.001


def obj(i, lat, lon, adj=None):
    return {"id": i, "code": str(i), "lat": lat, "lon": lon,
            "adj_lat": adj[0] if adj else None, "adj_lon": adj[1] if adj else None}


def mark(i, obj_id, lat, lon, ts):
    return {"id": i, "object_id": obj_id, "lat": lat, "lon": lon, "server_ts": ts}


RULES = dict(cap_m=200, missing_penalty_m=250, round_to_m=0, mark_policy="last")


class GeoTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(haversine_m(38.7, -121.0, 38.7, -121.0), 0)

    def test_one_milli_degree_lat(self):
        self.assertAlmostEqual(haversine_m(38.0, -121.0, 38.0 + D, -121.0), 111.2, delta=0.5)


class ScoringTests(unittest.TestCase):
    def test_exact_mark_scores_zero(self):
        r = score_team([obj(1, 38, -121)], [mark(1, 1, 38, -121, "t1")], **RULES)
        self.assertAlmostEqual(r["total"], 0)

    def test_missing_gets_penalty(self):
        r = score_team([obj(1, 38, -121)], [], **RULES)
        self.assertEqual((r["total"], r["missing"]), (250, 1))

    def test_cap_applies(self):
        r = score_team([obj(1, 38, -121)], [mark(1, 1, 38 + 5 * D, -121, "t1")], **RULES)
        self.assertEqual(r["total"], 200)

    def test_adjusted_coordinate_wins(self):
        o = obj(1, 38, -121, adj=(38 + D, -121))
        r = score_team([o], [mark(1, 1, 38 + D, -121, "t1")], **RULES)
        self.assertAlmostEqual(r["total"], 0, places=3)

    def test_policies(self):
        o = [obj(1, 38, -121)]
        ms = [mark(1, 1, 38 + D, -121, "t1"), mark(2, 1, 38 + 0.0002, -121, "t2"),
              mark(3, 1, 38 + 0.0005, -121, "t3")]
        last = score_team(o, ms, **{**RULES, "mark_policy": "last"})["total"]
        first = score_team(o, ms, **{**RULES, "mark_policy": "first"})["total"]
        best = score_team(o, ms, **{**RULES, "mark_policy": "best"})["total"]
        self.assertAlmostEqual(first, 111.2, delta=0.5)
        self.assertAlmostEqual(last, 55.6, delta=0.5)
        self.assertAlmostEqual(best, 22.2, delta=0.5)

    def test_rounding(self):
        r = score_team([obj(1, 38, -121)], [mark(1, 1, 38 + D, -121, "t1")],
                       **{**RULES, "round_to_m": 5})
        self.assertEqual(r["total"], 110)

    def test_unlocated_object_skipped(self):
        r = score_team([obj(1, None, None)], [], **RULES)
        self.assertEqual(len(r["objects"]), 0)

    def test_ranking_tiebreak_fewer_missing(self):
        a = {"total": 250, "missing": 1, "best": 0, "objects": []}
        b = {"total": 250, "missing": 0, "best": 50, "objects": []}
        self.assertEqual([k for k, _ in rank_teams({"a": a, "b": b})], ["b", "a"])


class RankAndBiasTests(unittest.TestCase):
    def test_competition_ranks_with_ties(self):
        r = lambda t: {"total": t, "missing": 0, "best": 5, "objects": []}
        ranked = with_ranks(rank_teams({"a": r(10), "b": r(20), "c": r(20), "d": r(30)}))
        self.assertEqual([(x["team_id"], x["rank"], x["tied"]) for x in ranked],
                         [("a", 1, False), ("b", 2, True), ("c", 2, True), ("d", 4, False)])

    def test_capped_flag_and_row_fields(self):
        o = obj(1, 38, -121)
        r = score_team([o], [mark(1, 1, 38 + 5 * D, -121, "t1")], **RULES)["objects"][0]
        self.assertTrue(r["capped"])
        self.assertAlmostEqual(r["lat"], 38 + 5 * D)
        self.assertEqual(r["n_marks"], 1)

    def test_offset_round_trip(self):
        lat, lon = move(38.7, -121.0, 30.0, -40.0)
        e, n = offset_m(38.7, -121.0, lat, lon)
        self.assertAlmostEqual(e, 30.0, delta=0.01)
        self.assertAlmostEqual(n, -40.0, delta=0.01)
        self.assertAlmostEqual(haversine_m(38.7, -121.0, lat, lon), 50.0, delta=0.3)

    def test_bias_flagged_when_marks_cluster_off_pin(self):
        ref = (38.7, -121.0)
        pts = [move(*ref, e, 25 + n) for e, n in [(-2, 0), (1, 2), (3, -1), (0, 1), (-1, -2), (2, 0)]]
        b = bias_stats(ref, pts)
        self.assertTrue(b["flagged"])
        self.assertAlmostEqual(b["north_m"], 25, delta=2)
        self.assertAlmostEqual(b["bearing_deg"], 0, delta=5)
        self.assertAlmostEqual(haversine_m(*ref, *b["suggested"]), b["bias_m"], delta=0.5)

    def test_bias_not_flagged_when_centered_or_few(self):
        ref = (38.7, -121.0)
        centered = [move(*ref, e, n) for e, n in [(20, 0), (-20, 0), (0, 20), (0, -20), (5, 5), (-5, -5)]]
        self.assertFalse(bias_stats(ref, centered)["flagged"])
        self.assertFalse(bias_stats(ref, [move(*ref, 0, 40)] * 3)["flagged"])
        self.assertIsNone(bias_stats(ref, []))


if __name__ == "__main__":
    unittest.main()
