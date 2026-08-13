"""
Phil - dev server entry point.

Run with: python3 run.py [port]
Then open http://localhost:8000 (or whatever port you passed).

First run: also run `python3 seed.py` once to load the course library.
"""

import os
import sys
from wsgiref.simple_server import make_server

import db
import seed
import app as phil_app

if __name__ == "__main__":
    db.init_db()
    # First boot against a fresh database (e.g. a brand new Railway volume)
    # seeds itself: the 20-course library and the first Phil staff account,
    # no manual `python3 seed.py` step needed. This deliberately only runs
    # once, checked by "are there any courses yet", not on every boot:
    # seed_courses() deletes and reloads the courses/weeks tables, and
    # SQLite's AUTOINCREMENT never reuses an id, so calling it again after
    # establishments exist would hand every course a new id and silently
    # orphan every enrolment, session record and course request that
    # pointed at the old ones. To intentionally refresh course content
    # later (e.g. after editing courses_data.js), run `python3 seed.py`
    # by hand, that's a deliberate action, not something that should ever
    # happen implicitly on a restart.
    conn = db.get_conn()
    has_courses = conn.execute("SELECT 1 FROM courses LIMIT 1").fetchone() is not None
    if not has_courses:
        seed.seed_courses(conn)
    seed.seed_phil_staff(conn)
    conn.close()
    # Railway (and most hosts) inject PORT as an env var rather than a CLI
    # arg; an explicit CLI arg still wins for local dev, e.g. `python3
    # run.py 8001`, and 8000 is the last-resort default.
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = int(os.environ.get("PORT", 8000))
    httpd = make_server("0.0.0.0", port, phil_app.wsgi_app)
    print(f"Phil running at http://localhost:{port}")
    httpd.serve_forever()
