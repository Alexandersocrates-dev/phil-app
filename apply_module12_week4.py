#!/usr/bin/env python3
"""
Module 12 week 4: ask the question the action plan's last field needs.

The plan template has five fields:

    My specific barrier          <- activity step 1
    What would help              <- activity step 2
    Who needs to be involved     <- activity step 4
    What I'll try first          <- nothing asks this
    Review date                  <- nothing asks this either

Four of the five get filled. The pupil leaves with a plan naming the barrier,
what would help and who is involved, and no first move - which is the only part
of it they can do on their own on Monday.

The review date is the same omission: the session agrees a plan and never says
when anyone looks at it again. Every other week-5 plan in the course sets one.

Two steps added, and step 3 folded into step 2 where it belongs - it is a note
about how to answer step 2's question, not a separate instruction.

    python3 apply_module12_week4.py --dry-run --courses data/courses_data.js
    python3 apply_module12_week4.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = (
    "1. Go back to the barrier they named, and use the card sort to pin down which kind it is.\n"
    "2. Ask: 'what would actually fix that?' Pupil writes it into the action plan.\n"
    "3. Be specific to their barrier \u2014 transport, one lesson, a person, a caring role \u2014 not a general routine.\n"
    "4. Ask: 'who needs to do something for this to work?' Add the name and the date."
)

NEW = (
    "1. Go back to the barrier they named, and use the card sort to pin down which kind it is.\n"
    "2. Ask: 'what would actually fix that?' Pupil writes it into the action plan. Keep it "
    "specific to their barrier \u2014 transport, one lesson, a person, a caring role \u2014 not a "
    "general routine.\n"
    "3. Ask: 'who needs to do something for this to work?' Add the name.\n"
    "4. Ask: 'and what's the first thing you'll try yourself?' Pupil writes that in too. It "
    "should be something they can do without waiting for anyone.\n"
    "5. Agree when you'll look at the plan again, and write the date on it."
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
    week = next(m for m in data if m.get("num") == 12)["weeks"][3]
    text = week.get("activity") or ""

    if text == NEW:
        print("already applied, nothing to do.")
        return 0
    if text != OLD:
        print("activity is not the expected text - nothing written.")
        return 1

    print("module 12 week 4 - activity")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, NEW))
    week["activity"] = NEW

    if args.dry_run:
        print("DRY RUN - nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
