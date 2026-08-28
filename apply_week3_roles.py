#!/usr/bin/env python3
"""
Module 04 week 3: stop the input pointing at a sheet that isn't on screen yet.

Input step 1 said "Show the roles handout". The handout is a fill-in table, and
the app deliberately places those at the step where the pupil writes on them —
here the activity, where they mark their role. So a mentor read "show the roles
handout" and had nothing to show; the pill was one step further down.

That placement is correct and shouldn't change: putting a fill-in sheet above
the instruction that fills it makes the mentor scroll back mid-session. The
input is what needs to change. It now names the four roles as a spoken
explanation, which is what that phase is for, and the sheet comes out in the
activity where it is used.

Input step 3 also went — "ask which role they've been in this term" is the
activity's first question, asked one step early.

    python3 apply_week3_roles.py --dry-run --courses data/courses_data.js
    python3 apply_week3_roles.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = (
    "1. Show the roles handout: target, instigator, bystander, defender.\n"
    "2. Explain that most people move between these rather than being one of them.\n"
    "3. Ask which role they've been in this term — you may get more than one answer.\n"
    "4. Avoid labelling the pupil; the point is that roles change, which means they can be chosen."
)

NEW = (
    "1. Name the four roles out loud: target, instigator, bystander, defender.\n"
    "2. Explain that most people move between these rather than being one of them.\n"
    "3. Avoid labelling the pupil. The point is that roles change, which means they can be chosen."
)


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
    week = next(m for m in data if m.get("num") == 4)["weeks"][2]
    text = week.get("input") or ""

    if text == NEW:
        print("already applied, nothing to do.")
        return 0
    if text != OLD:
        print("input is not the expected text — nothing written.")
        return 1

    print("module 04 week 3 — input")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, NEW))
    week["input"] = NEW

    if args.dry_run:
        print("DRY RUN — nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
