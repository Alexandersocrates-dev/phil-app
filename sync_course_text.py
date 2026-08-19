#!/usr/bin/env python3
"""
Pushes week content from data/courses_data.js into the database.

Course text lives in the database; courses_data.js is only the seed file, so
editing it changes nothing on a running app. This closes that gap, which makes
bulk content work possible — 139 weak session steps cannot reasonably be fixed
one at a time through an admin form.

    python3 sync_course_text.py --dry-run          # show every change
    python3 sync_course_text.py --dry-run --module 01
    python3 sync_course_text.py --confirm --module 01
    python3 sync_course_text.py --confirm          # all 20

Only ever updates the eight text fields of an existing week. It never creates,
deletes or reorders anything, and never touches enrolments or session records,
so a mistake costs a re-run rather than data.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "courses_data.js")

# file field -> database column
FIELDS = {
    "title": "title",
    "objective": "objective",
    "checkin": "checkin",
    "input": "input_content",
    "activity": "activity",
    "reflect": "reflect",
    "lookfor": "lookfor",
    "home": "home_activity",
}


def load_courses():
    with open(DATA, encoding="utf-8") as fh:
        src = fh.read()
    match = re.search(r"=\s*(\[.*\]);?\s*$", src, re.S)
    if not match:
        sys.exit("Could not find the course array in courses_data.js")
    return json.loads(match.group(1))


def main():
    dry = "--confirm" not in sys.argv
    only = None
    if "--module" in sys.argv:
        only = int(sys.argv[sys.argv.index("--module") + 1])

    courses = load_courses()
    conn = db.get_conn()
    changes = []

    for course in courses:
        if only is not None and course["num"] != only:
            continue
        row = conn.execute("SELECT id FROM courses WHERE module_number=?",
                           (course["num"],)).fetchone()
        if not row:
            print(f"  ! module {course['num']:02d} is not in the database, skipped")
            continue
        for index, week in enumerate(course["weeks"], start=1):
            current = conn.execute(
                "SELECT * FROM weeks WHERE course_id=? AND week_number=?",
                (row["id"], index)).fetchone()
            if not current:
                print(f"  ! M{course['num']:02d} week {index} missing from the database, skipped")
                continue
            for file_key, column in FIELDS.items():
                new = (week.get(file_key) or "").strip()
                old = (current[column] or "").strip()
                if new and new != old:
                    changes.append((course["num"], index, column, old, new, current["id"]))

    print(("DRY RUN — nothing written\n" if dry else "") + f"{len(changes)} field(s) differ\n")
    for num, wk, column, old, new, _ in changes:
        print(f"M{num:02d} w{wk} {column}")
        print(f"   was: {old[:100]}{'…' if len(old) > 100 else ''}")
        print(f"   now: {new[:100]}{'…' if len(new) > 100 else ''}")
        print()

    if dry:
        print("Re-run with --confirm to apply.")
    elif changes:
        try:
            for _, _, column, _, new, week_id in changes:
                conn.execute(f"UPDATE weeks SET {column}=? WHERE id=?", (new, week_id))
            conn.commit()
            print(f"Applied {len(changes)} change(s).")
        except Exception:
            conn.rollback()
            print("Failed — nothing was written.")
            raise
    conn.close()


if __name__ == "__main__":
    main()
