#!/usr/bin/env python3
"""
Adds the staff_only column to weeks, for the session-6 support plan.

Session 6 is written by the mentor after the course ends, with no pupil present.
It's flagged on the week rather than inferred from the number, so the meaning
survives if a course ever has a different shape.

    python3 migrate_staff_session.py

Safe to run repeatedly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def main():
    conn = db.get_conn()
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(weeks)")}
    if "staff_only" in existing:
        print("  already present: staff_only")
    else:
        conn.execute("ALTER TABLE weeks ADD COLUMN staff_only INTEGER NOT NULL DEFAULT 0")
        print("  added: staff_only")
    conn.commit()
    sixes = conn.execute("SELECT COUNT(*) FROM weeks WHERE week_number=6").fetchone()[0]
    flagged = conn.execute("SELECT COUNT(*) FROM weeks WHERE staff_only=1").fetchone()[0]
    conn.close()
    print(f"\nweek 6 rows: {sixes}, flagged staff-only: {flagged}")
    print("Run sync_course_text.py next to create or update the session 6 content.")


if __name__ == "__main__":
    main()
