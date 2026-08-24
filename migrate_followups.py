#!/usr/bin/env python3
"""
Adds the follow_ups table to an existing database.

The app never runs init_db, and CREATE TABLE IF NOT EXISTS won't create a table
in a database that was built before it was added to the schema, so an existing
deployment needs this once.

    python3 migrate_followups.py

Safe to run repeatedly: the table is created only if missing, and nothing else
is touched. No existing row is read or changed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

TABLE = """
CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL UNIQUE REFERENCES enrolments(id),
    date TEXT NOT NULL,
    helped TEXT NOT NULL CHECK(helped IN ('better','some','none','worse')),
    behaviour TEXT NOT NULL CHECK(behaviour IN ('no','sometimes','yes')),
    pupil_voice TEXT,
    next_step TEXT NOT NULL CHECK(next_step IN ('none','monitor','another_course','refer')),
    next_step_note TEXT,
    safeguarding_flag INTEGER NOT NULL DEFAULT 0,
    safeguarding_note TEXT NOT NULL DEFAULT '',
    recorded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
"""


def main():
    conn = db.get_conn()
    before = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "follow_ups" in before:
        print("  already present: follow_ups")
    else:
        conn.executescript(TABLE)
        conn.commit()
        print("  created: follow_ups")
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(follow_ups)")]
    conn.close()
    print("\nfollow_ups has:", ", ".join(cols))


if __name__ == "__main__":
    main()
