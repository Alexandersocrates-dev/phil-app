#!/usr/bin/env python3
"""
Parent disclosure test.

The isolation test asks *who can reach a route*. This asks a different question:
*what comes back*. A parent is legitimately entitled to their child's page — the
risk is not that they reach it, but that it contains something written for staff.

Every mentor-written field is seeded with a recognisable marker. Anything that
appears in a parent's response is a disclosure.

    /opt/venv/bin/python test_parent_disclosure.py
"""
import io
import os
import re
import sys
import tempfile

WORK = tempfile.mkdtemp()
os.environ["PHIL_DB_PATH"] = os.path.join(WORK, "phil.db")
os.environ["PHIL_PDF_DIR"] = os.path.join(WORK, "pdfs")
os.makedirs(os.environ["PHIL_PDF_DIR"], exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db          # noqa: E402
import auth as authlib  # noqa: E402
import app as phil      # noqa: E402


# Markers seeded into staff-only fields. Any of these in a parent's response is
# a leak, and the label says which field it came from.
MARKERS = {
    "ZZSAFEGUARDZZ": "safeguarding note",
    "ZZWHATHAPPENEDZZ": "session record: what happened",
    "ZZMENTORNOTESZZ": "session record: mentor's summary",
    "ZZREFLECTIONGOALZZ": "session record: reflection goal",
    "ZZLOOKFORZZ": "week: 'Watch for' mentor guidance",
    "ZZCHECKINZZ": "week: check-in script",
    "ZZINPUTZZ": "week: input script",
    "ZZACTIVITYZZ": "week: activity script",
    "ZZREFLECTZZ": "week: reflect script",
    "ZZSUPPORTPLANZZ": "support plan (staff session 6)",
    "ZZCOMPLETIONZZ": "completion reflection",
}
# What a parent is entitled to see.
ALLOWED = {
    "Little": "child's forename",
    "Billy": "child's surname",
    "Verbal disruption": "course title",
    "ZZHOMETASKZZ": "home task",
}


def build():
    db.init_db()
    conn = db.get_conn()
    now = db.now()
    conn.execute("INSERT INTO establishments (type,name,status,created_at) "
                 "VALUES ('school','School A','active',?)", (now,))
    conn.execute("""INSERT INTO subscriptions (establishment_id, plan_type, included_seats,
                    status, payment_method, created_at) VALUES (1,'school',15,'active','invoice',?)""",
                 (now,))
    authlib.create_user(conn, 1, "mentor", "Sarah", "sarah@a.test", "password123")
    authlib.create_user(conn, None, "parent_carer", "Parent", "parent@x.test", "password123")
    mentor = conn.execute("SELECT * FROM users WHERE email='sarah@a.test'").fetchone()
    parent = conn.execute("SELECT * FROM users WHERE email='parent@x.test'").fetchone()

    conn.execute("""INSERT INTO pupils (establishment_id,forename,surname,date_of_birth,
                    year_group,status,created_by,created_at)
                    VALUES (1,'Little','Billy','2010-01-01','9','active',?,?)""", (mentor["id"], now))
    conn.execute("INSERT INTO courses (module_number,title,status) "
                 "VALUES (5,'Verbal disruption','published')")
    for wk in range(1, 7):
        staff = 1 if wk == 6 else 0
        conn.execute("""INSERT INTO weeks (course_id,week_number,title,objective,checkin,
                        input_content,activity,reflect,lookfor,resources,home_activity,staff_only)
                        VALUES (1,?,?,?,?,?,?,?,?,'[]',?,?)""",
                     (wk, f"Session {wk} title", "Pupil can describe the trigger.",
                      "ZZCHECKINZZ", "ZZINPUTZZ", "ZZACTIVITYZZ", "ZZREFLECTZZ",
                      "ZZLOOKFORZZ", "ZZHOMETASKZZ", staff))

    conn.execute("""INSERT INTO enrolments (pupil_id,course_id,mentor_id,start_date,status,
                    current_week,parent_access_enabled,created_at)
                    VALUES (1,1,?,'2026-08-01','active',2,1,?)""", (mentor["id"], now))

    for wk in (1, 2):
        conn.execute("""INSERT INTO session_records (enrolment_id,week_id,date,what_happened,
                        reflection_goal,mentor_notes,resources_used,mood_rating,engagement_rating,
                        safeguarding_flag,safeguarding_note,recorded_by,created_at)
                        VALUES (1,?,?,?,?,?,'',3,3,1,?,?,?)""",
                     (wk, "2026-08-0%d" % wk, "ZZWHATHAPPENEDZZ", "ZZREFLECTIONGOALZZ",
                      "ZZMENTORNOTESZZ", "ZZSAFEGUARDZZ", mentor["id"], now))
    # The staff-only session 6 record: this is the support plan.
    conn.execute("""INSERT INTO session_records (enrolment_id,week_id,date,what_happened,
                    reflection_goal,mentor_notes,resources_used,safeguarding_flag,
                    safeguarding_note,recorded_by,created_at)
                    VALUES (1,6,'2026-09-01',?,'','','',0,'',?,?)""",
                 ("Where they started: ZZSUPPORTPLANZZ", mentor["id"], now))
    conn.execute("""INSERT INTO completion_reflections (enrolment_id,pupil_engagement,
                    course_effectiveness,recommended_next_steps,completed_by,completed_at,updated_at)
                    VALUES (1,?,'','',?,?,?)""", ("ZZCOMPLETIONZZ", mentor["id"], now, now))
    conn.execute("INSERT INTO pupil_parent_links (pupil_id,parent_user_id,created_at) "
                 "VALUES (1,?,?)", (parent["id"], now))
    conn.execute("INSERT INTO certificates (enrolment_id,issued_date,pdf_path) "
                 "VALUES (1,'2026-09-01','')")
    conn.commit()
    conn.close()
    return parent["email"]


def request(method, path, cookie=None, body=""):
    raw = body.encode()
    environ = {"REQUEST_METHOD": method,
               "PATH_INFO": path.split("?")[0],
               "QUERY_STRING": path.split("?")[1] if "?" in path else "",
               "wsgi.input": io.BytesIO(raw), "CONTENT_LENGTH": str(len(raw)),
               "CONTENT_TYPE": "application/x-www-form-urlencoded",
               "HTTP_HOST": "test", "wsgi.url_scheme": "http"}
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    cap = {}

    def start_response(status, headers, exc_info=None):
        cap["status"] = status
        cap["headers"] = headers

    payload = b"".join(phil.wsgi_app(environ, start_response))
    return cap["status"], payload


def main():
    email = build()
    _, _ = None, None
    status, payload = request("POST", "/login",
                              body=f"email={email.replace('@','%40')}&password=password123")
    cookie = None
    # sign in again capturing headers
    raw = f"email={email.replace('@','%40')}&password=password123".encode()
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/login", "QUERY_STRING": "",
               "wsgi.input": io.BytesIO(raw), "CONTENT_LENGTH": str(len(raw)),
               "CONTENT_TYPE": "application/x-www-form-urlencoded",
               "HTTP_HOST": "test", "wsgi.url_scheme": "http"}
    cap = {}

    def sr(status, headers, exc_info=None):
        cap["headers"] = headers

    b"".join(phil.wsgi_app(environ, sr))
    for k, v in cap.get("headers", []):
        if k.lower() == "set-cookie":
            cookie = v.split(";")[0]
    if not cookie:
        print("could not sign in as the parent")
        return 1

    routes = [("GET", "/parent", "parent home"),
              ("GET", "/report/mentee/1", "course report (view)"),
              ("GET", "/report/mentee/1/pdf", "course report PDF"),
              ("GET", "/certificate/1/pdf", "certificate PDF"),
              ("GET", "/notifications", "notifications"),
              ("GET", "/session/1/pdf", "session record PDF"),
              ("GET", "/report/pupil/1/pdf", "pupil report PDF"),
              ("GET", "/mentor/enrolment/1/summaries/pdf", "summaries PDF"),
              ("GET", "/mentor/pupils/1", "pupil record")]

    print("=" * 76)
    print("What a linked parent actually receives")
    print("Any ZZ marker below is staff-written content reaching a family")
    print("=" * 76)

    leaks = []
    for method, path, name in routes:
        status, payload = request(method, path, cookie=cookie)
        code = int(status.split()[0])
        text = payload.decode("utf-8", "ignore")
        found = [MARKERS[m] for m in MARKERS if m in text]
        allowed_seen = [ALLOWED[a] for a in ALLOWED if a in text]
        if found:
            leaks.append((name, found))
        verdict = "LEAK: " + "; ".join(found) if found else "clean"
        print(f"\n  {name} ({code})")
        print(f"      {verdict}")
        if allowed_seen and not found:
            print(f"      shows: {', '.join(allowed_seen)}")

    print("\n" + "=" * 76)
    print(f"LEAKS: {len(leaks)}")
    for name, found in leaks:
        print(f"    {name}: {', '.join(found)}")
    print("=" * 76)
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
