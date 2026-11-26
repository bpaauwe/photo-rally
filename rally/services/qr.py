"""Minimal QR code generator: byte mode, error correction level M, versions 1-10 (up to 213 bytes).

Pure Python with no dependencies, so it runs on any shared host. Output is an inline SVG,
which stays sharp at any print size. Follows ISO/IEC 18004; verified by decoding in tests.
"""
from markupsafe import Markup, escape

# version -> (error-correction codewords per block, [(blocks, data codewords per block), ...]) for level M
_BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
           5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
           9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])}
_ALIGN = {2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38],
          8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
MAX_BYTES = 213
_FORMAT_BITS_M = 0          # error-correction level M

# --- Reed-Solomon over GF(256), primitive polynomial 0x11D ---
_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i], _LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _divisor(degree):
    g = [1]
    for i in range(degree):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g[1:]


def _remainder(data, degree):
    div, rem = _divisor(degree), [0] * degree
    for b in data:
        factor = b ^ rem.pop(0)
        rem.append(0)
        for i, c in enumerate(div):
            rem[i] ^= _mul(c, factor)
    return rem


def _codewords(data, version):
    ec, groups = _BLOCKS[version]
    capacity = sum(n * d for n, d in groups) * 8
    bits = []

    def put(val, n):
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))
    put(0b0100, 4)
    put(len(data), 8 if version < 10 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad = 0
    while len(bits) < capacity:
        put((0xEC, 0x11)[pad % 2], 8)
        pad += 1
    cw = [int("".join(map(str, bits[k:k + 8])), 2) for k in range(0, len(bits), 8)]
    blocks, pos = [], 0
    for n, d in groups:
        for _ in range(n):
            blocks.append(cw[pos:pos + d])
            pos += d
    ecs = [_remainder(b, ec) for b in blocks]
    out = [b[i] for i in range(max(map(len, blocks))) for b in blocks if i < len(b)]
    return out + [e[i] for i in range(ec) for e in ecs]


def _format_cells(size, mask):
    data = _FORMAT_BITS_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412
    bit = lambda i: (bits >> i) & 1 == 1
    cells = [(8, i, bit(i)) for i in range(6)] + [(8, 7, bit(6)), (8, 8, bit(7)), (7, 8, bit(8))]
    cells += [(14 - i, 8, bit(i)) for i in range(9, 15)]
    cells += [(size - 1 - i, 8, bit(i)) for i in range(8)]
    cells += [(8, size - 15 + i, bit(i)) for i in range(8, 15)]
    cells.append((8, size - 8, True))          # the always-dark module
    return cells


_MASKS = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
          lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
          lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
          lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)


def _penalty(m):
    size, score = len(m), 0
    lines = [row for row in m] + [[m[y][x] for y in range(size)] for x in range(size)]
    for line in lines:
        run = 1
        for i in range(1, size):
            if line[i] == line[i - 1]:
                run += 1
            else:
                score += 3 + run - 5 if run >= 5 else 0
                run = 1
        score += 3 + run - 5 if run >= 5 else 0
        s = "".join("1" if v else "0" for v in line)
        score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for y in range(size - 1):
        for x in range(size - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark, total = sum(v for row in m for v in row), size * size
    return score + ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10


def make_matrix(text, mask=None):
    """Rows of booleans (True = dark module) for the QR code of `text`.

    `mask` forces one of the 8 mask patterns (for testing); normally the best one is chosen."""
    data = text.encode("utf-8")
    for version in range(1, 11):
        capacity = sum(n * d for n, d in _BLOCKS[version][1]) * 8
        if 4 + (8 if version < 10 else 16) + 8 * len(data) <= capacity:
            break
    else:
        raise ValueError(f"Text is too long for this QR code generator (limit {MAX_BYTES} bytes).")
    size = version * 4 + 17
    mod = [[False] * size for _ in range(size)]
    func = [[False] * size for _ in range(size)]

    def setf(x, y, dark):
        mod[y][x] = dark
        func[y][x] = True
    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < size and 0 <= cy + dy < size:
                    setf(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _ALIGN.get(version, [])
    for i, cx in enumerate(pos):
        for j, cy in enumerate(pos):
            if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    for x, y, dark in _format_cells(size, 0):             # reserve the format area
        setf(x, y, dark)
    if version >= 7:
        rem = version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = version << 12 | rem
        for i in range(18):
            a, b, dark = size - 11 + i % 3, i // 3, (bits >> i) & 1 == 1
            setf(a, b, dark)
            setf(b, a, dark)

    cw, i = _codewords(data, version), 0
    for right in range(size - 1, 0, -2):
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = (size - 1 - vert) if ((right + 1) & 2) == 0 else vert
                if not func[y][x] and i < len(cw) * 8:
                    mod[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1

    best, best_score = None, None
    for mask_no, rule in enumerate(_MASKS):
        if mask is not None and mask_no != mask:
            continue
        cand = [[mod[y][x] ^ (not func[y][x] and rule(x, y)) for x in range(size)] for y in range(size)]
        for x, y, dark in _format_cells(size, mask_no):
            cand[y][x] = dark
        score = _penalty(cand)
        if best is None or score < best_score:
            best, best_score = cand, score
    return best


def svg(text, label="QR code", quiet=4):
    """The QR code as an inline SVG (black on white, with the required quiet zone)."""
    m = make_matrix(text)
    n = len(m)
    dim = n + 2 * quiet
    parts = []
    for y, row in enumerate(m):
        x = 0
        while x < n:
            if row[x]:
                start = x
                while x < n and row[x]:
                    x += 1
                parts.append(f"M{start + quiet} {y + quiet}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges" '
        f'role="img" aria-label="{escape(label)}"><rect width="{dim}" height="{dim}" fill="#fff"/>'
        f'<path d="{"".join(parts)}" fill="#000"/></svg>')
