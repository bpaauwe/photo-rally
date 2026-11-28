import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rally import throttle

W = throttle.WINDOW_S


def new_db():
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE login_failure (id INTEGER PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, ts INTEGER NOT NULL);")
    return db


def fail(db, user, ip, t):
    throttle.record_failure(db, user, ip, now=t)


class ThrottleTests(unittest.TestCase):
    def test_allowed_below_the_limit(self):
        db = new_db()
        for i in range(throttle.MAX_PER_IP - 1):
            fail(db, "admin", "1.1.1.1", 1000 + i)
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=1010), 0)

    def test_ip_limit_locks_until_the_oldest_counted_failure_ages_out(self):
        db = new_db()
        for i in range(5):
            fail(db, f"guess{i}", "1.1.1.1", 1000 + i * 10)       # different usernames, same address
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=1050), 1000 + W - 1050)
        self.assertEqual(throttle.locked_seconds(db, "admin", "2.2.2.2", now=1050), 0)    # other addresses unaffected
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=1000 + W), 0)  # first failure aged out

    def test_username_limit_applies_across_addresses(self):
        db = new_db()
        for i in range(10):
            fail(db, "admin", f"9.9.9.{i}", 2000 + i)
        self.assertGreater(throttle.locked_seconds(db, "admin", "5.5.5.5", now=2020), 0)
        self.assertEqual(throttle.locked_seconds(db, "someone-else", "5.5.5.5", now=2020), 0)

    def test_partial_expiry_restores_access_one_failure_at_a_time(self):
        db = new_db()
        for i in range(7):
            fail(db, "admin", "1.1.1.1", 3000 + i * 100)          # locked after the 5th
        # the 5 most recent are at 3200..3600 -> lock ends when 3200 ages out
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=3600), 3200 + W - 3600)
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=3200 + W), 0)

    def test_old_rows_are_purged_when_recording(self):
        db = new_db()
        fail(db, "a", "1.1.1.1", 100)
        fail(db, "a", "1.1.1.1", 100 + W + 5)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM login_failure").fetchone()[0], 1)

    def test_clear_ip(self):
        db = new_db()
        for i in range(5):
            fail(db, "admin", "1.1.1.1", 4000 + i)
        throttle.clear_ip(db, "1.1.1.1")
        self.assertEqual(throttle.locked_seconds(db, "admin", "1.1.1.1", now=4010), 0)

    def test_message_rounds_up_minutes(self):
        self.assertIn("1 minute.", throttle.lock_message(1))
        self.assertIn("2 minutes", throttle.lock_message(61))
        self.assertIn("15 minutes", throttle.lock_message(900))


if __name__ == "__main__":
    unittest.main()
