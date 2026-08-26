#!/usr/bin/env python3
"""
Adds courses.related_module to an existing database.

CREATE TABLE IF NOT EXISTS won't add a column to a table that already exists,
so a running deployment needs this once.

    python3 migrate_related_module.py

Safe to run repeatedly: the column is added only if missing. Run
sync_course_text.py afterwards to fill it from data/courses_data.js.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def main():
    conn = db.get_conn()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(courses)")]
    if "related_module" in cols:
        print("  already present: courses.related_module")
    else:
        conn.execute("ALTER TABLE courses ADD COLUMN related_module TEXT")
        conn.commit()
        print("  added: courses.related_module")
    filled = conn.execute(
        "SELECT count(*) FROM courses WHERE related_module IS NOT NULL AND related_module != ''"
    ).fetchone()[0]
    total = conn.execute("SELECT count(*) FROM courses").fetchone()[0]
    conn.close()
    print(f"\n{filled} of {total} courses have a related module set.")
    if not filled:
        print("Run: python3 sync_course_text.py --confirm")


if __name__ == "__main__":
    main()
