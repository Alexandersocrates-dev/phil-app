#!/usr/bin/env python3
"""
Module 07: drop "drift", and ask week 5's opening question the useful way.

"Drift" is the writer's word for it. It appears eight times across the module
and nowhere else in the course, and a pupil asked "when did you drift?" has to
work out what is being asked before they can answer.

Week 2 is titled "What switches me off", so the module already has a phrase the
pupil has met. This uses "lose focus" for the moment it happens and "switch off"
where the sentence is about the state, which is how the rest of the module reads.

Week 5's input asked: "if you could only keep one thing from this course, which
would it be?" That is a question about ranking, and a pupil who found two things
useful has to discard one to answer it. It also invites "none of it". Asking
what has been most helpful gets at the same thing without the trap, and it is
the answer that goes at the top of the plan.

The line about earlier sheets is kept. It is not part of the question - it tells
the mentor the pupil's own writing is on the page if they need reminding.

    python3 apply_module07_drift.py --dry-run --courses data/courses_data.js
    python3 apply_module07_drift.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {"week": 1, "field": "checkin",
     "old": "3. Don't frame this as being in trouble for drifting off.",
     "new": "3. Don't frame this as being in trouble for switching off."},
    {"week": 1, "field": "input",
     "old": "3. The skill is noticing the drift sooner, so less of the lesson is lost.",
     "new": "3. The skill is noticing sooner that you've switched off, so less of the lesson is lost."},
    {"week": 1, "field": "input",
     "old": "4. Say you'll map a real lesson out in a moment, drift and all.",
     "new": "4. Say you'll map a real lesson out in a moment, the switched-off bits included."},
    {"week": 1, "field": "activity",
     "old": "2. Ask: 'think of a lesson this week \u2014 when were you actually working, and when did you drift?'",
     "new": "2. Ask: 'think of a lesson this week \u2014 when were you actually working, and when did you lose focus?'"},
    {"week": 1, "field": "activity",
     "old": "4. Ask: 'how long did you last before the first drift?'",
     "new": "4. Ask: 'how long did you last before you first lost focus?'"},
    {"week": 1, "field": "activity",
     "old": "5. Be clear that everyone drifts \u2014 you're finding the pattern, not the failure.",
     "new": "5. Be clear that everyone loses focus \u2014 you're finding the pattern, not the failure."},
    {"week": 1, "field": "reflect",
     "old": "1. Ask: 'what was happening right before you drifted?'",
     "new": "1. Ask: 'what was happening right before you lost focus?'"},
    {"week": 5, "field": "activity",
     "old": "1. Ask: 'what are the two things most likely to make you drift?' Their week two sheets are in this step if they need reminding.",
     "new": "1. Ask: 'what are the two things most likely to make you lose focus?' Their week two sheets are in this step if they need reminding."},
    {"week": 5, "field": "input",
     "old": "1. Ask: 'if you could only keep one thing from this course, which would it be?' Their earlier sheets are in this step if they need reminding.",
     "new": "1. Ask: 'what's been the most helpful thing you've learnt from this course?' Their earlier sheets are in this step if they need reminding."},
]


def load_courses(path):
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    prefix, body = src.split("=", 1)
    body = body.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return prefix + "= ", json.loads(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--courses", default=os.path.join("data", "courses_data.js"))
    args = ap.parse_args()

    if not os.path.exists(args.courses):
        print("cannot find %s" % args.courses)
        return 1

    prefix, data = load_courses(args.courses)
    module = next(m for m in data if m.get("num") == 7)
    changes = 0

    for edit in EDITS:
        week = module["weeks"][edit["week"] - 1]
        text = week.get(edit["field"]) or ""
        if edit["new"] in text:
            print("w%d %-8s already applied, skipping" % (edit["week"], edit["field"]))
            continue
        if text.count(edit["old"]) != 1:
            print("w%d %s: expected line not found exactly once - nothing written."
                  % (edit["week"], edit["field"]))
            return 1
        print("w%d %-8s %s" % (edit["week"], edit["field"], edit["old"][:66]))
        print("            -> %s" % edit["new"][:66])
        week[edit["field"]] = text.replace(edit["old"], edit["new"])
        changes += 1

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("\n%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
