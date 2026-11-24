import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rally.services.instructions import (build_rows, csv_to_text, parse_sheet,
                                         rich, split_lines, to_text)

SAMPLE = """Title: Fall Photo Rally
Date: 2026-11-21

# comment
0.00 | START: right on Main St
1.20 | **Left** at stop sign onto Oak Rd | watch for dogs
NOTE | Farm equipment on road
3.456 | Right at T
"""


class ParseTests(unittest.TestCase):
    def test_basic(self):
        rows, header, errors, warnings = parse_sheet(SAMPLE)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(header, {"title": "Fall Photo Rally", "date": "2026-11-21"})
        self.assertEqual([r["kind"] for r in rows], ["instr", "instr", "note", "instr"])
        self.assertEqual(rows[1]["note"], "watch for dogs")

    def test_errors_and_warnings(self):
        rows, _, errors, warnings = parse_sheet("abc | x\n2.0 | ok\n1.0 | backward\n[RALLY]\n3.0 |\nNOTE |")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(errors), 3)
        self.assertEqual(len(warnings), 2)

    def test_blank_mileage_allowed(self):
        rows, _, errors, _ = parse_sheet(" | Left at Y")
        self.assertEqual((errors, rows[0]["mileage"]), ([], None))

    def test_round_trip(self):
        rows, header, *_ = parse_sheet(SAMPLE)
        rows2, header2, errors, _ = parse_sheet(to_text(rows, header))
        self.assertEqual((rows2, header2, errors), (rows, header, []))


class DisplayTests(unittest.TestCase):
    def test_numbering_and_legs(self):
        rows, *_ = parse_sheet(SAMPLE)
        out = build_rows(rows)
        self.assertEqual([r["num"] for r in out], [1, 2, "", 3])
        self.assertEqual([r["mile"] for r in out], ["0.00", "1.20", "", "3.46"])   # 3.456 -> 3.46
        self.assertEqual([r["leg"] for r in out], ["", "1.20", "", "2.26"])

    def test_half_rounds_up(self):
        out = build_rows(parse_sheet("1.005 | a")[0])
        self.assertEqual(out[0]["mile"], "1.01")

    def test_lines_and_markup(self):
        self.assertEqual(split_lines("a\\nb\\n"), ["a", "b"])
        self.assertEqual(str(rich("**x** & <b>")), "<strong>x</strong> &amp; &lt;b&gt;")


class CsvTests(unittest.TestCase):
    def test_csv(self):
        text = csv_to_text('Title,My Rally\nmileage,instruction,note\n0.0,Start\n1.2,"Left\nat stop",hint\nNOTE,Careful\n')
        rows, header, errors, _ = parse_sheet(text)
        self.assertEqual((errors, header), ([], {"title": "My Rally"}))
        self.assertEqual(rows[1]["text"], "Left\\nat stop")
        self.assertEqual(rows[2]["kind"], "note")


if __name__ == "__main__":
    unittest.main()
