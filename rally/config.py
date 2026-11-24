import os
import secrets

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


def _secret_key():
    """Env var wins; otherwise generate once and persist in instance/."""
    env = os.environ.get("RALLY_SECRET_KEY")
    if env:
        return env
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


class Config:
    SECRET_KEY = _secret_key()
    DATABASE = os.environ.get("RALLY_DB", os.path.join(INSTANCE_DIR, "rally.sqlite3"))
    PHOTO_DIR = os.environ.get("RALLY_PHOTOS", os.path.join(INSTANCE_DIR, "photos"))
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024       # 8 MB upload cap
    # WAL can misbehave on some network filesystems; default off, test before enabling.
    DB_WAL = os.environ.get("RALLY_DB_WAL", "0") == "1"
    SESSION_COOKIE_SECURE = os.environ.get("RALLY_INSECURE_COOKIES", "0") != "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 3
