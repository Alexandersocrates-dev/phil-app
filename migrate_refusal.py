#!/usr/bin/env python3
"""Adds the refusal columns to an existing database.

    python3 migrate_refusal.py

Safe to run repeatedly: each column is added only if missing. The enrolment
columns are nullable because a course that ran to its end has no reason to give.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

COLUMNS = {
    "session_records": [
        ("refused_to_engage", "INTEGER NOT NULL DEFAULT 0"),
        ("refusal_note", "TEXT"),
    ],
    "enrolments": [
        ("end_reason", "TEXT"),
        ("end_note", "TEXT"),
        ("ended_at", "TEXT"),
    ],
}


def main():
    conn = db.get_conn()
    added = 0
    for table, columns in COLUMNS.items():
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, spec in columns:
            if name in existing:
                print("  already present: %s.%s" % (table, name))
                continue
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, spec))
            added += 1
            print("  added: %s.%s" % (table, name))
    conn.commit()
    conn.close()
    print()
    print("%d column(s) added." % added)


if __name__ == "__main__":
    main()
