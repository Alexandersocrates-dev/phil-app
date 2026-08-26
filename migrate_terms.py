#!/usr/bin/env python3
"""
Adds the terms table to an existing database.

The app never runs init_db, and CREATE TABLE IF NOT EXISTS won't create a table
in a database built before it was added to the schema, so an existing
deployment needs this once.

    python3 migrate_terms.py

Safe to run repeatedly: the table is created only if missing, and nothing else
is touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

TABLE = """
CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    name TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_terms_establishment
    ON terms (establishment_id, date_from);
"""


def main():
    conn = db.get_conn()
    existing = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "terms" in existing:
        print("  already present: terms")
    else:
        conn.executescript(TABLE)
        conn.commit()
        print("  created: terms")
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(terms)")]
    conn.close()
    print("\nterms has:", ", ".join(cols))


if __name__ == "__main__":
    main()
