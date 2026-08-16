"""
Phil - seed script.

Imports the 20 real courses (courses_data.js, the same file used to generate
the Word course documents and resource packs) into the courses/weeks tables,
so the app ships with real content rather than placeholder text. Safe to run
more than once: it clears and reloads the course catalog each time, but never
touches establishments, users, pupils or session records.
"""

import json
import re
import os
import secrets
import db
import auth as authlib

COURSES_JS_PATH = os.path.join(os.path.dirname(__file__), "data", "courses_data.js")

PHIL_STAFF_EMAIL = os.environ.get("PHIL_STAFF_EMAIL", "staff@phileducation.co.uk")


def load_courses_json():
    text = open(COURSES_JS_PATH, encoding="utf-8").read().strip()
    text = re.sub(r"^module\.exports\s*=\s*", "", text)
    text = re.sub(r";\s*$", "", text)
    return json.loads(text)


def seed_courses(conn):
    courses = load_courses_json()
    conn.execute("DELETE FROM weeks")
    conn.execute("DELETE FROM courses")

    for c in courses:
        description = c.get("approachNote", "")
        cur = conn.execute(
            """INSERT INTO courses (module_number, title, focus_area, description,
               status, created_by, published_at) VALUES (?,?,?,?,?,?,?)""",
            (c["num"], c["title"], c.get("shortName", c["title"]), description,
             "published", None, db.now()),
        )
        course_id = cur.lastrowid

        for i, w in enumerate(c.get("weeks", []), start=1):
            resources = json.dumps(w.get("resources", []))
            conn.execute(
                """INSERT INTO weeks (course_id, week_number, title, objective,
                   checkin, input_content, activity, reflect, lookfor, resources,
                   home_activity)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (course_id, i, w.get("title", f"Week {i}"), w.get("objective", ""),
                 w.get("checkin", ""), w.get("input", ""), w.get("activity", ""),
                 w.get("reflect", ""), w.get("lookfor", ""), resources,
                 w.get("home", "")),
            )
    conn.commit()
    return len(courses)


def seed_phil_staff(conn):
    """
    Creates the first Phil staff account, a one-off deploy step per
    Phil_Technical_Build_Spec.docx section 7.8: phil_staff accounts are never
    created through the public sign-up form, so the very first one has no
    inviter and is seeded directly. Every subsequent one is invited from
    inside the Phil team management screen.

    No password is hard-coded. PHIL_STAFF_PASSWORD is used when it is set as an
    environment variable; otherwise a random one is generated. Either way the
    password is returned, never stored in the repo, so callers can surface it
    once and there is no default credential to document or leak.
    """
    existing = conn.execute("SELECT id FROM users WHERE role='phil_staff' LIMIT 1").fetchone()
    if existing:
        return None
    password = os.environ.get("PHIL_STAFF_PASSWORD") or secrets.token_urlsafe(12)
    authlib.create_user(conn, None, "phil_staff", "Phil Staff", PHIL_STAFF_EMAIL, password)
    conn.commit()
    return password


if __name__ == "__main__":
    db.init_db()
    conn = db.get_conn()
    n = seed_courses(conn)
    staff_password = seed_phil_staff(conn)
    conn.close()
    print(f"Seeded {n} courses.")
    if staff_password:
        print(f"Seeded Phil staff account: {PHIL_STAFF_EMAIL}")
        print(f"Sign-in password (shown once, change it after first sign-in): {staff_password}")
