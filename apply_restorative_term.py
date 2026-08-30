#!/usr/bin/env python3
"""
Call it a restorative conversation everywhere.

Three places said "repair conversation" for the thing the resource itself calls
the restorative conversation prompt card. Two names for one practice, and the
one in the objective is the version a school reads.

  10 w4  objective  "takes part in a repair conversation or action"
  08 w4  home       "model a short repair conversation yourself"
  04 w4  objective  handled by apply_restorative_fix.py, which rewrites that
                    line entirely - skipped here if already applied

Module 10's objective also had "or action" doing a lot of quiet work: a pupil
who does something to put it right without a conversation has met it, which is
correct, but "a repair conversation or action" reads as two vague halves. It now
says both plainly.

The watch-for note is a comma splice, and "punitive labour" is not language a
mentor would use.

    python3 apply_restorative_term.py --dry-run --courses data/courses_data.js
    python3 apply_restorative_term.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "module": 10, "week": 4, "field": "objective",
        "old": "Pupil understands the impact of a past incident and takes part in a "
               "repair conversation or action.",
        "new": "Pupil understands the impact of a past incident and either takes part "
               "in a restorative conversation or agrees an action that puts it right.",
    },
    {
        "module": 10, "week": 4, "field": "lookfor",
        "old": "Repair should be proportionate and pupil-led where possible, not "
               "punitive labour, check school policy on this before agreeing "
               "specific actions.",
        "new": "Whatever is agreed should be proportionate and chosen by the pupil "
               "where possible. It is not a punishment by another name. Check the "
               "school's policy before agreeing anything specific.",
    },
    {
        "module": 8, "week": 4, "field": "home",
        "old": "If there's been a difficult moment at home, model a short repair "
               "conversation yourself",
        "new": "If there's been a difficult moment at home, model a short restorative "
               "conversation yourself",
        "substring": True,
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
    changes = 0

    for edit in EDITS:
        week = next(m for m in data if m.get("num") == edit["module"])["weeks"][edit["week"] - 1]
        text = week.get(edit["field"]) or ""
        if edit["new"] in text:
            print("%02d w%d %s: already applied"
                  % (edit["module"], edit["week"], edit["field"]))
            continue
        if edit.get("substring"):
            if text.count(edit["old"]) != 1:
                print("%02d w%d %s: expected text not found - left alone"
                      % (edit["module"], edit["week"], edit["field"]))
                continue
            week[edit["field"]] = text.replace(edit["old"], edit["new"])
        else:
            if text != edit["old"]:
                print("%02d w%d %s: not the expected text - left alone"
                      % (edit["module"], edit["week"], edit["field"]))
                continue
            week[edit["field"]] = edit["new"]
        print("%02d w%d %s:" % (edit["module"], edit["week"], edit["field"]))
        print("   before: %s" % edit["old"])
        print("   after:  %s\n" % edit["new"])
        changes += 1

    # Module 04's objective is rewritten wholesale by apply_restorative_fix.py.
    m4 = next(m for m in data if m.get("num") == 4)["weeks"][3]
    if "repair conversation" in (m4.get("objective") or ""):
        print("04 w4 objective still says 'repair conversation' - "
              "apply_restorative_fix.py replaces that line; run it too.")

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
