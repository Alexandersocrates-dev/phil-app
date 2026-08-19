#!/usr/bin/env python3
"""
Adds the review-point columns to an existing database.

The app never runs init_db, and CREATE TABLE IF NOT EXISTS won't alter a table
that already exists, so an existing deployment needs this once.

    python3 migrate_reviews.py

Safe to run repeatedly: each column is added only if missing, and nothing else
is touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

COLUMNS = [
    ("review_date", "TEXT"),
    ("review_note", "TEXT"),
    ("review_done", "INTEGER NOT NULL DEFAULT 0"),
]


def main():
    conn = db.get_conn()
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(enrolments)")}
    added = []
    for name, spec in COLUMNS:
        if name in existing:
            print(f"  already present: {name}")
            continue
        conn.execute(f"ALTER TABLE enrolments ADD COLUMN {name} {spec}")
        added.append(name)
        print(f"  added: {name}")
    conn.commit()
    after = {r["name"] for r in conn.execute("PRAGMA table_info(enrolments)")}
    conn.close()
    print(f"\n{len(added)} column(s) added.")
    print("enrolments now has:", ", ".join(sorted(after)))


if __name__ == "__main__":
    main()
