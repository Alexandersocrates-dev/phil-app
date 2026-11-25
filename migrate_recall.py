#!/usr/bin/env python3
"""Adds the recall rating to an existing database.

    python3 migrate_recall.py

Safe to run repeatedly: the column is added only if missing.

mood_rating is deliberately left alone. Sessions recorded before this change
carry a mood rating and nothing else, and rewriting those as recall ratings
would be inventing data — the two measure different things. Old records keep
showing mood; new ones show what the pupil remembered.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def main():
    conn = db.get_conn()
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(session_records)")}
    if "recall_rating" in existing:
        print("  already present: recall_rating")
        added = 0
    else:
        conn.execute("ALTER TABLE session_records ADD COLUMN recall_rating INTEGER")
        print("  added: recall_rating")
        added = 1
    conn.commit()
    with_mood = conn.execute(
        "SELECT COUNT(*) c FROM session_records WHERE mood_rating IS NOT NULL").fetchone()["c"]
    conn.close()
    print()
    print(f"{added} column(s) added.")
    print(f"{with_mood} existing record(s) keep their mood rating; nothing was rewritten.")


if __name__ == "__main__":
    main()
