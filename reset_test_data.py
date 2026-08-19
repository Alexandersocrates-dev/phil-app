#!/usr/bin/env python3
"""
Clears test establishments, mentors and pupils, leaving Phil staff and all
course content intact. Then optionally creates one full-plan establishment to
test with.

    python3 reset_test_data.py --dry-run     # show what would go
    python3 reset_test_data.py --confirm     # actually delete
    python3 reset_test_data.py --confirm --seed "Demo Academy" mentor@example.com

KEPT, always:
  - users with role phil_staff
  - courses, weeks, legal documents
  - anything not tied to an establishment

REMOVED:
  - every establishment and its subscription
  - every pupil, enrolment, session record, certificate, draft
  - every admin, mentor and parent user
  - notifications, support requests, course requests, seat alerts, invoices

Take a Railway backup before running with --confirm. This cannot be undone.
"""
import os
import sys
import sqlite3
import datetime
import secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import auth as authlib  # noqa: E402

# Child rows first: SQLite enforces foreign keys, so anything referencing a
# table has to go before the table it points at.
DELETE_ORDER = [
    ("session_drafts", "enrolment_id IN (SELECT id FROM enrolments)"),
    ("certificates", "enrolment_id IN (SELECT id FROM enrolments)"),
    ("session_records", "enrolment_id IN (SELECT id FROM enrolments)"),
    ("session_schedule", "enrolment_id IN (SELECT id FROM enrolments)"),
    ("completion_reflections", "enrolment_id IN (SELECT id FROM enrolments)"),
    ("enrolments", "1=1"),
    ("pupil_parent_links", "1=1"),
    ("parent_access_requests", "1=1"),
    ("pupils", "1=1"),
    ("seat_alerts", "1=1"),
    ("invoices", "subscription_id IN (SELECT id FROM subscriptions)"),
    ("subscriptions", "1=1"),
    ("course_requests", "1=1"),
    ("support_requests", "1=1"),
    ("notifications", "1=1"),
    ("sessions", "user_id IN (SELECT id FROM users WHERE role != 'phil_staff')"),
    ("users", "role != 'phil_staff'"),
    ("establishments", "1=1"),
]


def counts(conn):
    out = {}
    for table, where in DELETE_ORDER:
        try:
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
        except sqlite3.Error as exc:
            out[table] = f"error: {exc}"
    return out


def preserved(conn):
    return {
        "phil_staff users": conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='phil_staff'").fetchone()[0],
        "courses": conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "weeks": conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0],
    }


def seed(conn, school_name, mentor_email):
    """Creates one establishment on a full school plan, with an admin who can
    also mentor. Full plan, not pilot, so all five weeks are available."""
    now = db.now()
    cur = conn.execute(
        "INSERT INTO establishments (type,name,status,created_at) VALUES ('school',?,'active',?)",
        (school_name, now))
    estab_id = cur.lastrowid
    conn.execute(
        """INSERT INTO subscriptions (establishment_id, plan_type, included_seats, pupil_cap,
           status, payment_method, created_at)
           VALUES (?, 'school', 15, NULL, 'active', 'invoice', ?)""",
        (estab_id, now))
    password = secrets.token_urlsafe(9)
    # Use the app's own helper rather than writing the hash by hand, so the
    # password is stored exactly as a real signup would store it.
    authlib.create_user(conn, estab_id, "admin", "Test Admin", mentor_email, password)
    return school_name, mentor_email, password


def main():
    dry = "--dry-run" in sys.argv or "--confirm" not in sys.argv
    conn = db.get_conn()
    conn.execute("PRAGMA foreign_keys = ON")

    print("WILL DELETE" if not dry else "WOULD DELETE (dry run)")
    for table, n in counts(conn).items():
        if n:
            print(f"  {n:>5}  {table}")
    print("\nKEPT")
    for k, v in preserved(conn).items():
        print(f"  {v:>5}  {k}")

    if dry:
        print("\nNothing written. Re-run with --confirm to delete.")
        conn.close()
        return

    for table, where in DELETE_ORDER:
        conn.execute(f"DELETE FROM {table} WHERE {where}")
    conn.commit()
    print("\nDeleted.")

    if "--seed" in sys.argv:
        i = sys.argv.index("--seed")
        name = sys.argv[i + 1]
        email = sys.argv[i + 2]
        school, addr, pw = seed(conn, name, email)
        conn.commit()
        print(f"\nCreated {school}")
        print(f"  sign in : {addr}")
        print(f"  password: {pw}")
        print("  plan    : school, active, 15 seats (not a pilot)")
        print("\nChange that password after signing in.")

    left = conn.execute("SELECT COUNT(*) FROM establishments").fetchone()[0]
    staff = conn.execute("SELECT COUNT(*) FROM users WHERE role='phil_staff'").fetchone()[0]
    print(f"\nNow: {left} establishment(s), {staff} Phil staff account(s), "
          f"{conn.execute('SELECT COUNT(*) FROM courses').fetchone()[0]} courses.")
    conn.close()


if __name__ == "__main__":
    main()
