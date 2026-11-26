"""Addresses printed into QR codes."""
import re

from flask import current_app, request

# Plain URL characters only, so the value can't carry markup or whitespace into a page or a QR code.
_BASE_RE = re.compile(r"^https?://[A-Za-z0-9._~:/\-\[\]@%]+$")
MAX_BASE = 150


def clean_base(value):
    """A tidy http(s) address with no trailing slash, or None if it isn't one."""
    s = (value or "").strip().rstrip("/")
    return s if s and len(s) <= MAX_BASE and _BASE_RE.match(s) else None


def public_base(override=None):
    """Address of this app as phones should reach it: the organizer's override, else the
    RALLY_PUBLIC_URL setting, else the address this request came in on (including any URL prefix)."""
    return clean_base(override) or clean_base(current_app.config.get("PUBLIC_URL")) or request.url_root.rstrip("/")


def is_secure_enough(base):
    """GPS and offline use need https, except on localhost."""
    return base.startswith("https://") or base.split("://", 1)[1].split("/")[0].split(":")[0] in ("localhost", "127.0.0.1")
