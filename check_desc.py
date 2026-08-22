#!/usr/bin/env python3
"""Shows what the database holds as each course's description, so we can see
whether the file's approachNote is what reached it."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

conn = db.get_conn()
rows = conn.execute("SELECT module_number, title, description FROM courses ORDER BY module_number").fetchall()
for r in rows[:3]:
    d = r["description"] or ""
    print(f"--- M{r['module_number']:02d} {r['title']} ---")
    print(f"    {d[:220]}")
    print()
hits = [r["module_number"] for r in rows
        if r["description"] and ("judgement" in r["description"] or "Education Inspection Framework" in r["description"])]
print(f"courses whose stored description still uses retired Ofsted wording: {hits}")
conn.close()
