#!/usr/bin/env python3
"""Shows exactly what would change in each course description.

The sync's own preview truncates at 100 characters, which hides the change when
it falls later in the paragraph. This prints the differing sentences only, so
every edit can be read before anything is written."""
import difflib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "courses_data.js")
with open(DATA, encoding="utf-8") as fh:
    src = fh.read()
courses = json.loads(re.search(r"=\s*(\[.*\]);?\s*$", src, re.S).group(1))

conn = db.get_conn()
for c in courses:
    row = conn.execute("SELECT description FROM courses WHERE module_number=?", (c["num"],)).fetchone()
    if not row:
        continue
    old = (row["description"] or "").strip()
    new = (c.get("approachNote") or "").strip()
    if not new or old == new:
        continue
    print(f"=== M{c['num']:02d} {c['title']} ===")
    o = re.split(r"(?<=\.)\s+", old)
    n = re.split(r"(?<=\.)\s+", new)
    for line in difflib.unified_diff(o, n, lineterm="", n=0):
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        mark = "REMOVED:" if line.startswith("-") else "ADDED:  "
        print(f"  {mark} {line[1:].strip()}")
    print()
conn.close()
