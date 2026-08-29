#!/usr/bin/env python3
"""
Module 10 week 2: the body is not the earliest warning, and week 1 says so.

Input step 4 said "the physical signal is the earliest warning they get".

Week 1 teaches the opposite. Its whole reflect step is "where is the earliest
point it could have gone differently?", answered with "usually much earlier than
they expect" - meaning back in the situation, before any of it reached the body.
A pupil who did week 1 is being told the opposite thing a week later.

It is also not what happens. The order is situation, then how it is read, then
the body, then the urge, then the action. The body is the earliest thing a pupil
can notice IN THEMSELVES once it has started, which is worth knowing and is what
this session teaches. It is not the earliest warning available.

The step now says that, and points back at the timeline for the earlier one.
Two sessions that agreed on nothing now build on each other.

    python3 apply_module10_week2_signal.py --dry-run --courses data/courses_data.js
    python3 apply_module10_week2_signal.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = "4. Say why that matters \u2014 the physical signal is the earliest warning they get."
NEW = ("4. Say why that matters: once it has started, the body is the first thing "
       "they can notice in themselves.\n"
       "5. Be clear the situation is an earlier warning still. That is what last "
       "week's timeline was for.")


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
    week = next(m for m in data if m.get("num") == 10)["weeks"][1]
    text = week.get("input") or ""

    if NEW in text:
        print("already applied, nothing to do.")
        return 0
    if text.count(OLD) != 1:
        print("input step 4 is not the expected text - nothing written.")
        return 1

    updated = text.replace(OLD, NEW)
    print("module 10 week 2 - input")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
    week["input"] = updated

    if args.dry_run:
        print("DRY RUN - nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
