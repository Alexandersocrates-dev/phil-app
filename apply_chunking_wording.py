#!/usr/bin/env python3
"""
Module 07: two places that still say "chunking" after the sheet was renamed.

apply_chunking_rename.py renamed the resource and rewrote the activity that
produces it, but missed the two lines where a mentor says the word out loud:

  w3 reflect  "could you do that chunking on your own in a lesson?"
  w4 checkin  "did you use the chunking, and in which lesson?"

Those are the worst two to leave. The rest of the module now avoids the term
entirely, so a pupil meets it for the first time in a question about something
they supposedly just learned - and week 4's check-in asks whether they used a
thing under a name that appears nowhere on the sheet they were given.

Both now describe the action instead of naming a technique, which is what the
sheet does too.

    python3 apply_chunking_wording.py --dry-run --courses data/courses_data.js
    python3 apply_chunking_wording.py --courses data/courses_data.js

Standard library only. Run after apply_chunking_rename.py, though it does not
depend on it - these two lines are untouched by that script.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "week": 3, "field": "reflect",
        "old": "1. Ask: 'could you do that chunking on your own in a lesson?'\n"
               "2. Pupil picks one lesson this week to try it in.",
        "new": "1. Ask: 'could you break work up like that on your own, in a lesson?'\n"
               "2. Pupil picks one lesson this week to try it in.",
    },
    {
        "week": 4, "field": "checkin",
        "old": "1. Ask: 'did you use the chunking, and in which lesson?'\n"
               "2. Ask: 'what was different about that lesson, if anything?'\n"
               "3. If they didn't use it, ask: 'what would have needed to be true for you to?'",
        "new": "1. Ask: 'did you break anything into steps last week, and in which lesson?'\n"
               "2. Ask: 'what was different about that lesson, if anything?'\n"
               "3. If they didn't, ask: 'what would have needed to be true for you to?'",
    },
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
        if text == edit["new"]:
            print("week %d %s: already applied, skipping" % (edit["week"], edit["field"]))
            continue
        if text != edit["old"]:
            print("week %d %s: not the expected text - nothing written."
                  % (edit["week"], edit["field"]))
            return 1
        print("=" * 72)
        print("module 07 week %d - %s" % (edit["week"], edit["field"]))
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week[edit["field"]] = edit["new"]
        changes += 1

    if args.dry_run:
        print("DRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("Nothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
