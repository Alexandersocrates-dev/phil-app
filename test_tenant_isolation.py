#!/usr/bin/env python3
"""
Tenant isolation test.

Builds two establishments in a scratch database, signs in as each role for real,
and requests every id-bearing route belonging to School A. Anything other than a
block for an outsider is a breach.

This drives the actual WSGI app through real requests with real session cookies —
not the access helper in isolation, which would only prove the helper works.
"""
import io
import os
import re
import sys
import tempfile
import datetime

# A scratch database in a temp directory: this must never touch the live volume.
WORK = tempfile.mkdtemp()
os.environ["PHIL_DB_PATH"] = os.path.join(WORK, "phil.db")
os.environ["PHIL_PDF_DIR"] = os.path.join(WORK, "pdfs")
os.makedirs(os.environ["PHIL_PDF_DIR"], exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db          # noqa: E402
import auth as authlib  # noqa: E402
import app as phil      # noqa: E402


# ---------------------------------------------------------------- fixtures
def build():
    # The scratch database starts empty, so create the schema before using it.
    db.init_db()
    conn = db.get_conn()
    now = db.now()
    ids = {}
    for name in ("School A", "School B"):
        conn.execute(
            "INSERT INTO establishments (type,name,status,created_at) VALUES ('school',?,'active',?)",
            (name, now))
        ids[name] = conn.execute("SELECT id FROM establishments WHERE name=?", (name,)).fetchone()["id"]
        conn.execute(
            """INSERT INTO subscriptions (establishment_id, plan_type, included_seats,
               status, payment_method, created_at) VALUES (?,?,?,?,?,?)""",
            (ids[name], "school", 15, "active", "invoice", now))

    people = {}
    for label, estab, role, email in [
        ("mentorA", "School A", "mentor", "ma@a.test"),
        ("mentorA2", "School A", "mentor", "ma2@a.test"),
        ("adminA", "School A", "admin", "ad@a.test"),
        ("mentorB", "School B", "mentor", "mb@b.test"),
        ("adminB", "School B", "admin", "ad@b.test"),
    ]:
        authlib.create_user(conn, ids[estab], role, label, email, "password123")
        people[label] = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    conn.execute(
        """INSERT INTO pupils (establishment_id,forename,surname,date_of_birth,year_group,
           status,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (ids["School A"], "Little", "Billy", "2010-01-01", "9", "active",
         people["mentorA"]["id"], now))
    pupil_a = conn.execute("SELECT id FROM pupils WHERE surname='Billy'").fetchone()["id"]

    conn.execute("INSERT INTO courses (module_number,title,status) VALUES (1,'Verbal disruption','published')")
    course = conn.execute("SELECT id FROM courses").fetchone()["id"]
    for wk in range(1, 7):
        conn.execute(
            """INSERT INTO weeks (course_id,week_number,title,objective,checkin,input_content,
               activity,reflect,lookfor,resources,home_activity,staff_only)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (course, wk, f"Week {wk}", "o", "c", "i", "a", "r", "l", "[]", "h",
             1 if wk == 6 else 0))

    conn.execute(
        """INSERT INTO enrolments (pupil_id,course_id,mentor_id,start_date,status,current_week,created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (pupil_a, course, people["mentorA"]["id"], "2026-08-01", "active", 1, now))
    enrolment = conn.execute("SELECT id FROM enrolments").fetchone()["id"]

    week1 = conn.execute("SELECT id FROM weeks WHERE week_number=1").fetchone()["id"]
    conn.execute(
        """INSERT INTO session_records (enrolment_id,week_id,date,what_happened,reflection_goal,
           mentor_notes,resources_used,mood_rating,engagement_rating,safeguarding_flag,
           safeguarding_note,recorded_by,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (enrolment, week1, "2026-08-01", "Check-in: private", "goal", "notes", "",
         4, 4, 1, "CONFIDENTIAL SAFEGUARDING NOTE", people["mentorA"]["id"], now))
    record = conn.execute("SELECT id FROM session_records").fetchone()["id"]

    conn.execute(
        "INSERT INTO certificates (enrolment_id, issued_date, pdf_path) VALUES (?,?,?)",
        (enrolment, "2026-08-20", ""))
    conn.commit()
    conn.close()
    return dict(people=people, pupil=pupil_a, enrolment=enrolment,
                record=record, course=course)


# ---------------------------------------------------------------- driving the app
def request(method, path, cookie=None, body=""):
    """Make a real request against the WSGI app and return (status, headers, body)."""
    raw = body.encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path.split("?")[0],
        "QUERY_STRING": path.split("?")[1] if "?" in path else "",
        "wsgi.input": io.BytesIO(raw),
        "CONTENT_LENGTH": str(len(raw)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "HTTP_HOST": "test",
        "wsgi.url_scheme": "http",
    }
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    chunks = phil.application(environ, start_response)
    payload = b"".join(chunks)
    return captured["status"], captured.get("headers", []), payload


def sign_in(email):
    status, headers, _ = request(
        "POST", "/login", body=f"email={email.replace('@','%40')}&password=password123")
    for k, v in headers:
        if k.lower() == "set-cookie":
            return v.split(";")[0]
    raise SystemExit(f"could not sign in as {email} (status {status})")


# ---------------------------------------------------------------- the test
def main():
    f = build()
    sessions = {label: sign_in(u["email"]) for label, u in f["people"].items()}

    e, p, r = f["enrolment"], f["pupil"], f["record"]
    routes = [
        ("GET",  f"/mentor/pupils/{p}",                      "pupil record"),
        ("GET",  f"/mentor/session/{e}",                     "session form"),
        ("POST", f"/mentor/session/{e}/autosave",            "session autosave"),
        ("POST", f"/mentor/session/{e}",                     "session SUBMIT"),
        ("GET",  f"/mentor/schedule/{e}",                    "schedule"),
        ("GET",  f"/mentor/reflection/{e}",                  "reflection"),
        ("GET",  f"/report/mentee/{e}",                      "course report (view)"),
        ("GET",  f"/report/mentee/{e}/pdf",                  "course report PDF"),
        ("GET",  f"/report/pupil/{p}/pdf",                   "pupil report PDF"),
        ("GET",  f"/mentor/enrolment/{e}/summaries/pdf",     "summaries PDF"),
        ("GET",  f"/session/{r}/pdf",                        "session record PDF"),
        ("GET",  f"/certificate/{e}/pdf",                    "certificate PDF"),
        ("POST", f"/mentor/enrolment/{e}/review",            "set review point"),
        ("POST", f"/mentor/pupils/{p}/archive",              "archive pupil"),
    ]

    # An outsider must never get a 200 with content. Redirect to login/flash is a
    # block; 403/404 is a block; 200 carrying the pupil's data is a breach.
    def outcome(status, payload):
        code = int(status.split()[0])
        if code in (301, 302, 303, 307):
            return "blocked (redirect)"
        if code in (401, 403, 404):
            return f"blocked ({code})"
        if code == 200:
            leaked = (b"Little" in payload or b"Billy" in payload
                      or b"CONFIDENTIAL" in payload or b"%PDF" in payload[:8])
            return "BREACH (200 with data)" if leaked else "blocked (200, no data)"
        return f"blocked ({code})"

    print("=" * 78)
    print("School A owns: pupil Little Billy, enrolment, session record, certificate")
    print("Outsiders tested: School B's mentor and admin, plus School A's OTHER mentor")
    print("=" * 78)

    breaches = []
    for label, who in [("mentorB", "School B mentor"), ("adminB", "School B admin"),
                       ("mentorA2", "School A, different mentor")]:
        print(f"\n--- as {who} ---")
        for method, path, name in routes:
            status, _, payload = request(method, path, cookie=sessions[label])
            res = outcome(status, payload)
            flag = "  <== BREACH" if res.startswith("BREACH") else ""
            if flag:
                breaches.append((who, method, path, name))
            print(f"  {method:5} {name:24} {status.split()[0]:4} {res}{flag}")

    print(f"\n--- as School A's own mentor (must still work) ---")
    broken = []
    for method, path, name in routes:
        if method == "POST":
            continue  # side-effectful; the GETs prove access
        status, _, payload = request(method, path, cookie=sessions["mentorA"])
        code = int(status.split()[0])
        ok = code == 200 or code in (301, 302, 303)
        if not ok:
            broken.append((method, path, name))
        print(f"  {method:5} {name:24} {status.split()[0]:4} {'ok' if ok else 'BROKEN <=='}")

    print("\n" + "=" * 78)
    print(f"BREACHES: {len(breaches)}")
    for b in breaches:
        print("   ", b)
    print(f"LEGITIMATE ACCESS BROKEN: {len(broken)}")
    for b in broken:
        print("   ", b)
    print("=" * 78)
    return 1 if (breaches or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
