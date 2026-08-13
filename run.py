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
import app as phil_app

if __name__ == "__main__":
    db.init_db()
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
