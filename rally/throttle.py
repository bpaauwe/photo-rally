"""Slow down password guessing on the organizer login.

Failed attempts are kept in SQLite (so every worker process sees them) and counted in a sliding window.
Two limits apply, and either one blocks further attempts until enough old failures have aged out:
  - 5 failures from one address, whatever usernames were tried (stops one machine guessing).
  - 10 failures against one username from anywhere (stops guessing spread across many addresses).
Attempts made while locked out are not recorded, so an attacker cannot extend the lockout by persisting.
"""
import time

from flask import request

WINDOW_S = 15 * 60
MAX_PER_IP = 5
MAX_PER_USER = 10


def client_ip():
    return request.remote_addr or "unknown"


def locked_seconds(db, username, ip, now=None):
    """Seconds until another attempt is allowed (0 if allowed now)."""
    now = int(time.time() if now is None else now)
    cut = now - WINDOW_S
    ip_times = [r[0] for r in db.execute("SELECT ts FROM login_failure WHERE ip = ? AND ts > ? ORDER BY ts", (ip, cut))]
    user_times = [r[0] for r in db.execute("SELECT ts FROM login_failure WHERE username = ? AND ts > ? ORDER BY ts", (username, cut))]
    wait = 0
    # Locked while the count is at the limit; it drops below the limit when the Nth-most-recent failure ages out.
    if len(ip_times) >= MAX_PER_IP:
        wait = max(wait, ip_times[-MAX_PER_IP] + WINDOW_S - now)
    if len(user_times) >= MAX_PER_USER:
        wait = max(wait, user_times[-MAX_PER_USER] + WINDOW_S - now)
    return max(0, wait)


def record_failure(db, username, ip, now=None):
    now = int(time.time() if now is None else now)
    db.execute("DELETE FROM login_failure WHERE ts <= ?", (now - WINDOW_S,))      # keep the table tiny
    db.execute("INSERT INTO login_failure (username, ip, ts) VALUES (?, ?, ?)", (username, ip, now))
    db.commit()


def clear_ip(db, ip):
    db.execute("DELETE FROM login_failure WHERE ip = ?", (ip,))
    db.commit()


def lock_message(seconds):
    minutes = max(1, -(-seconds // 60))
    return f"Too many failed attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
