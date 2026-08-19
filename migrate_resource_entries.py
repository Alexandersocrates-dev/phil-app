#!/usr/bin/env python3
"""
Creates the resource_entries table on an existing database.

Holds what a pupil writes on a resource — the blank cells of a table, the fields
of a plan, the ticks on a checklist — so it survives past the session and can be
looked at again later.

    python3 migrate_resource_entries.py

Safe to run repeatedly: CREATE TABLE IF NOT EXISTS, and nothing else is touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

SQL = """
CREATE TABLE IF NOT EXISTS resource_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL REFERENCES enrolments(id),
    week_id INTEGER NOT NULL REFERENCES weeks(id),
    resource_slug TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value TEXT,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(enrolment_id, week_id, resource_slug, field_key)
);
CREATE INDEX IF NOT EXISTS idx_resource_entries_enrolment
    ON resource_entries(enrolment_id, week_id);
"""


def main():
    conn = db.get_conn()
    before = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.executescript(SQL)
    conn.commit()
    after = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    created = after - before
    count = conn.execute("SELECT COUNT(*) FROM resource_entries").fetchone()[0]
    conn.close()
    print("created:", ", ".join(sorted(created)) if created else "nothing (already present)")
    print(f"resource_entries now holds {count} entr{'y' if count == 1 else 'ies'}.")


if __name__ == "__main__":
    main()
