"""Instruction sheet text format: parsing, display model, CSV conversion.

Format (adapted from the TSD Rally Sheets tool; one instruction per line, fields split by |):

    Title: / Subtitle: / Date:      optional header lines before the first instruction
    mileage | instruction | note    mileage is cumulative odometer miles; may be blank while measuring
    NOTE | text                     a line with no number or mileage
    # comment                       ignored
    **bold**  *italic*  \\n         inline markup and line breaks inside the instruction text

`note` (third field) is organizer-only: it prints only on the organizer copy.
Pure functions, no Flask or database imports.
"""
import csv
import io
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from markupsafe import Markup, escape

# --- markup (same rules as the TSD tool) -----------------------------------
BOLD_ITALIC_RE = re.compile(r"\*\*\*(.+?)\*\*\*")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<![\s*])\*(?![\w*])")


def apply_markup(escaped, bold_italic, bold, italic):
    s = BOLD_ITALIC_RE.sub(bold_italic, escaped)
    s = BOLD_RE.sub(bold, s)
    return ITALIC_RE.sub(italic, s)


def rich(text):
    """Escape, then turn ***x***, **x**, *x* into bold-italic, bold, italic."""
    return Markup(apply_markup(str(escape(text)), r"<strong><em>\1</em></strong>",
                               r"<strong>\1</strong>", r"<em>\1</em>"))


def css_text(s):
    """Text safe inside a CSS content:"..." string."""
    return Markup(re.sub(r'["\\<>\r\n]', "", s or ""))


def pretty_date(s):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            d = datetime.strptime((s or "").strip(), fmt).date()
            return f"{d:%A, %B} {d.day}, {d.year}"
        except ValueError:
            pass
    return s or ""


def split_lines(text):
    """Literal \\n in the text starts a new line; trailing blank lines are dropped."""
    lines = [p.strip() for p in (text or "").split("\\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines or [""]


# --- parsing ----------------------------------------------------------------
HEADER_RE = re.compile(r"^(title|subtitle|date)\s*:\s*(.*)$", re.I)
SECTION_RE = re.compile(r"^\[[^\]]*\]$")


def parse_sheet(text):
    """Return (rows, header, errors, warnings).

    rows: dicts with kind ('instr'|'note'), mileage (float|None), text, note.
    Lines with errors are skipped and reported; callers should not save when errors exist.
    """
    rows, header, errors, warnings = [], {}, [], []
    last = None
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not rows:
            m = HEADER_RE.match(line)
            if m:
                header[m.group(1).lower()] = m.group(2).strip()
                continue
        if SECTION_RE.match(line):
            warnings.append(f"Line {n}: section header {line} ignored (this app uses one continuous sheet).")
            continue
        parts = [p.strip() for p in line.split("|")]
        if parts[0].upper() == "NOTE":
            body = parts[1] if len(parts) > 1 else ""
            if body:
                rows.append({"kind": "note", "mileage": None, "text": body, "note": ""})
            else:
                errors.append(f"Line {n}: NOTE needs text after the |.")
            continue
        mile_txt = parts[0].lstrip("@").strip()
        mileage = None
        if mile_txt:
            try:
                mileage = float(mile_txt)
            except ValueError:
                errors.append(f"Line {n}: mileage '{parts[0]}' is not a number.")
                continue
            if mileage < 0:
                errors.append(f"Line {n}: mileage can't be negative.")
                continue
        instr = parts[1] if len(parts) > 1 else ""
        if not instr:
            errors.append(f"Line {n}: no instruction text.")
            continue
        if mileage is not None:
            if last is not None and mileage < last - 1e-9:
                warnings.append(f"Line {n}: mileage {mile_txt} is lower than the one before it ({last:g}).")
            last = mileage
        rows.append({"kind": "instr", "mileage": mileage, "text": instr,
                     "note": parts[2] if len(parts) > 2 else ""})
    return rows, header, errors, warnings


def fmt_mileage_input(m):
    """Mileage as typed in the editor: at least 2 decimals, up to 3."""
    s = f"{m:.3f}"
    return s[:-1] if s.endswith("0") else s


def to_text(rows, header=None):
    out = [f"{k.capitalize()}: {v}" for k, v in (header or {}).items() if v]
    if out:
        out.append("")
    for r in rows:
        if r["kind"] == "note":
            out.append(f"NOTE | {r['text']}")
        else:
            m = "" if r["mileage"] is None else fmt_mileage_input(r["mileage"])
            line = f"{m} | {r['text']}"
            if r["note"]:
                line += f" | {r['note']}"
            out.append(line)
    return "\n".join(out) + ("\n" if out else "")


# --- display model ----------------------------------------------------------
def _round2(m):
    return Decimal(str(m)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_rows(rows):
    """Rows ready to print: instruction numbers (notes get none), mileage and leg to 1/100 mile."""
    out, n, prev = [], 0, None
    for r in rows:
        if r["kind"] == "note":
            out.append({"cls": "note", "num": "", "mile": "", "leg": "",
                        "lines": split_lines(r["text"]), "note": ""})
            continue
        n += 1
        m = None if r["mileage"] is None else _round2(r["mileage"])
        leg = ""
        if m is not None:
            if prev is not None:
                leg = f"{max(m - prev, Decimal('0')):.2f}"
            prev = m
        out.append({"cls": "", "num": n, "mile": "" if m is None else f"{m:.2f}", "leg": leg,
                    "lines": split_lines(r["text"]), "note": r["note"]})
    return out


# --- CSV --------------------------------------------------------------------
def csv_to_text(raw):
    """CSV with columns mileage, instruction, note (header row optional) -> editor text.
    Rows 'Title,x' / 'Subtitle,x' / 'Date,x' set the header; 'NOTE,text' is a note line."""
    out = []
    for rec in csv.reader(io.StringIO(raw)):
        cells = [re.sub(r"\r\n|\r|\n", r"\\n", c).replace("|", "/").strip() for c in rec]
        if not any(cells):
            continue
        first = cells[0].lower()
        second = cells[1] if len(cells) > 1 else ""
        if first in ("title", "subtitle", "date"):
            out.append(f"{cells[0]}: {second}")
        elif first == "note":
            out.append(f"NOTE | {second}")
        elif first == "mileage":
            continue
        else:
            out.append(" | ".join(cells[:3]))
    return "\n".join(out)
