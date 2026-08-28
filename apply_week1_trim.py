#!/usr/bin/env python3
"""
Module 04 week 1: keep the input to setting up, and the activity to doing.

"Read the four questions aloud" was the activity starting early — the activity's
first step then works through those same four questions. Reading them out twice
in a row is the overlap that was left after the last pass.

"Say you won't be correcting their answers" belongs immediately before the pupil
starts answering, not two steps earlier with the card still being introduced.

Leaves the input as three steps: get a situation, have a fallback, put the card
on the table.

    python3 apply_week1_trim.py --dry-run --courses data/courses_data.js
    python3 apply_week1_trim.py --courses data/courses_data.js

Standard library only. Run after apply_week1_simplify.py.
"""

import argparse
import json
import os
import sys

INPUT_OLD = (
    "1. Ask: 'is there a fall-out with someone that's still on your mind?'\n"
    "2. If nothing comes, use a smaller one, or make one up. It works the same.\n"
    "3. Show the restorative question prompt card.\n"
    "4. Read the four questions aloud.\n"
    "5. Say you won't be correcting their answers."
)

INPUT_NEW = (
    "1. Ask: 'is there a fall-out with someone that's still on your mind?'\n"
    "2. If nothing comes, use a smaller one, or make one up. It works the same.\n"
    "3. Show the restorative question prompt card."
)

ACTIVITY_OLD = (
    "1. Work through the four questions, one at a time, on the situation from the input.\n"
    "2. Leave a silence after each — the first answer is rarely the full one.\n"
    "3. Note what they say in the box below, in their words, without taking sides."
)

ACTIVITY_NEW = (
    "1. Say you won't be correcting their answers.\n"
    "2. Read the four questions aloud, then work through them one at a time on "
    "the situation from the input.\n"
    "3. Leave a silence after each — the first answer is rarely the full one.\n"
    "4. Note what they say in the box below, in their words, without taking sides."
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
    week = next(m for m in data if m.get("num") == 4)["weeks"][0]

    changes = 0
    for field, old, new in (("input", INPUT_OLD, INPUT_NEW),
                            ("activity", ACTIVITY_OLD, ACTIVITY_NEW)):
        text = week.get(field) or ""
        if text == new:
            print("week 1 %s: already applied, skipping" % field)
            continue
        if text != old:
            print("week 1 %s: not the expected text. Run apply_week1_simplify.py "
                  "first. Nothing written." % field)
            return 1
        print("=" * 72)
        print("module 04 week 1 — %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, new))
        week[field] = new
        changes += 1

    if args.dry_run:
        print("DRY RUN — %d change(s) would be made, nothing written." % changes)
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
