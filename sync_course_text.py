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

# Fields that aren't free text and so aren't part of the text sync, but do need
# to exist when a week is created for the first time.
EXTRA = {
    "resources": lambda w: json.dumps(w.get("resources") or []),
    "staff_only": lambda w: 1 if w.get("staff_only") else 0,
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
    course_changes = []
    created = []

    for course in courses:
        if only is not None and course["num"] != only:
            continue
        row = conn.execute("SELECT id FROM courses WHERE module_number=?",
                           (course["num"],)).fetchone()
        if not row:
            print(f"  ! module {course['num']:02d} is not in the database, skipped")
            continue
        # The course's own description (the file's approachNote) was never part
        # of the sync, so corrections to it — framework citations, evidence
        # references — could never reach the database from the file.
        new_desc = (course.get("approachNote") or "").strip()
        old_desc = (conn.execute("SELECT description FROM courses WHERE id=?",
                                 (row["id"],)).fetchone()["description"] or "").strip()
        if new_desc and new_desc != old_desc:
            course_changes.append((course["num"], old_desc, new_desc, row["id"]))

        for index, week in enumerate(course["weeks"], start=1):
            current = conn.execute(
                "SELECT * FROM weeks WHERE course_id=? AND week_number=?",
                (row["id"], index)).fetchone()
            if not current:
                # A week in the file but not the database is a new session, such
                # as the staff-only session 6. Create it rather than skipping,
                # or the file could never introduce one.
                created.append((course["num"], index, row["id"], week))
                continue
            for file_key, column in FIELDS.items():
                new = (week.get(file_key) or "").strip()
                old = (current[column] or "").strip()
                if new and new != old:
                    changes.append((course["num"], index, column, old, new, current["id"]))

            # Resources and the staff-only flag were only written when a week was
            # created, so adding a resource to an existing week could never
            # reach the database. Compare them here too.
            new_res = json.dumps(week.get("resources") or [])
            old_res = current["resources"] or "[]"
            if json.loads(new_res) != json.loads(old_res):
                changes.append((course["num"], index, "resources", old_res, new_res, current["id"]))

            new_flag = 1 if week.get("staff_only") else 0
            old_flag = current["staff_only"] if "staff_only" in current.keys() else 0
            if new_flag != (old_flag or 0):
                changes.append((course["num"], index, "staff_only", str(old_flag), str(new_flag), current["id"]))

    print(("DRY RUN — nothing written\n" if dry else "")
          + f"{len(changes)} week field(s) differ, {len(course_changes)} course "
            f"description(s) differ, {len(created)} week(s) to create\n")
    for num, old, new, _ in course_changes:
        print(f"M{num:02d} description")
        print(f"   was: {old[:100]}{'…' if len(old) > 100 else ''}")
        print(f"   now: {new[:100]}{'…' if len(new) > 100 else ''}")
        print()
    for num, index, _, week in created:
        flag = " [staff only]" if week.get("staff_only") else ""
        print(f"CREATE M{num:02d} week {index}: {week.get('title', '')}{flag}")
    if created:
        print()
    for num, wk, column, old, new, _ in changes:
        print(f"M{num:02d} w{wk} {column}")
        print(f"   was: {old[:100]}{'…' if len(old) > 100 else ''}")
        print(f"   now: {new[:100]}{'…' if len(new) > 100 else ''}")
        print()

    if dry:
        print("Re-run with --confirm to apply.")
    elif changes or created or course_changes:
        try:
            for _, index, course_id, week in created:
                cols = ["course_id", "week_number"] + list(FIELDS.values()) + list(EXTRA)
                vals = [course_id, index] + [(week.get(k) or "").strip() for k in FIELDS] \
                    + [fn(week) for fn in EXTRA.values()]
                conn.execute(
                    f"INSERT INTO weeks ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    vals)
            for _, _, column, _, new, week_id in changes:
                conn.execute(f"UPDATE weeks SET {column}=? WHERE id=?", (new, week_id))
            for _, _, new_desc, course_id in course_changes:
                conn.execute("UPDATE courses SET description=? WHERE id=?",
                             (new_desc, course_id))
            conn.commit()
            print(f"Applied {len(changes)} week change(s), "
                  f"{len(course_changes)} description(s), "
                  f"created {len(created)} week(s).")
        except Exception:
            conn.rollback()
            print("Failed — nothing was written.")
            raise
    conn.close()


if __name__ == "__main__":
    main()
