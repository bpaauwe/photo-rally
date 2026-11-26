import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rally.services import qr

try:
    import cv2
    import numpy as np
except ImportError:            # decoding checks need OpenCV; the structural checks below don't
    cv2 = None


def matrix_from_svg(svg):
    """Rebuild the module matrix from the SVG path (the exact thing that gets printed)."""
    dim = int(re.search(r'viewBox="0 0 (\d+) \d+"', svg).group(1))
    quiet = 4
    n = dim - 2 * quiet
    m = [[False] * n for _ in range(n)]
    for x, y, w in re.findall(r"M(\d+) (\d+)h(\d+)v1h-\d+z", svg):
        for k in range(int(w)):
            m[int(y) - quiet][int(x) - quiet + k] = True
    return m


def decode(m):
    n, scale, quiet = len(m), 8, 4
    img = np.full(((n + 2 * quiet) * scale,) * 2, 255, np.uint8)
    for y in range(n):
        for x in range(n):
            if m[y][x]:
                img[(y + quiet) * scale:(y + quiet + 1) * scale, (x + quiet) * scale:(x + quiet + 1) * scale] = 0
    return cv2.QRCodeDetectorAruco().detectAndDecode(img)[0]


class StructureTests(unittest.TestCase):
    def test_size_grows_with_text(self):
        self.assertEqual(len(qr.make_matrix("hi")), 21)                 # version 1
        self.assertEqual(len(qr.make_matrix("x" * 213)), 10 * 4 + 17)   # version 10

    def test_too_long_is_rejected(self):
        with self.assertRaises(ValueError):
            qr.make_matrix("x" * 214)

    def test_finder_patterns_and_timing(self):
        m = qr.make_matrix("https://example.com/play/join/K7M2QX")
        n = len(m)
        for ox, oy in ((0, 0), (n - 7, 0), (0, n - 7)):
            self.assertTrue(all(m[oy][ox + i] and m[oy + 6][ox + i] for i in range(7)))
            self.assertTrue(m[oy + 3][ox + 3] and not m[oy + 1][ox + 1])
        self.assertTrue(all(m[6][i] == (i % 2 == 0) for i in range(8, n - 8)))

    def test_deterministic(self):
        self.assertEqual(qr.make_matrix("abc"), qr.make_matrix("abc"))

    def test_svg_is_escaped_and_sized(self):
        s = str(qr.svg("hello", label='a "label" <x>'))
        self.assertIn("&lt;x&gt;", s)
        self.assertNotIn('<x>', s)
        self.assertIn('viewBox="0 0 29 29"', s)                         # 21 modules + quiet zone of 4 each side


@unittest.skipIf(cv2 is None, "OpenCV not installed")
class DecodeTests(unittest.TestCase):
    def test_urls_round_trip_through_the_printed_svg(self):
        for url in ("https://example.com/rally/play/join/K7M2QX", "http://localhost:5000/play/join",
                    "https://a-much-longer-host-name.example.org/some/sub/folder/play/join/ABCDEF"):
            self.assertEqual(decode(matrix_from_svg(str(qr.svg(url)))), url)

    def test_every_length_and_every_mask(self):
        for n in range(1, 214, 7):
            text = ("0123456789abcdefghijklmnopqrstuvwxyz/:.-" * 6)[:n]
            for mask in range(8):
                self.assertEqual(decode(qr.make_matrix(text, mask=mask)), text, (n, mask))


if __name__ == "__main__":
    unittest.main()
