#!/usr/bin/env python3
"""
Module 10 week 2: four concrete steps instead of five abstract ones.

The input had grown into a sequence of statements about warning signs without
ever naming one. "The body is the first thing they can notice in themselves" is
a true sentence a pupil cannot picture; "hot face, tight fists, fast breathing"
is the same point in words they can check against their own last incident.

Steps 4 and 5 were also one idea split in two - what the body signal is good
for, and how it compares with last week's timeline. They read better as one
line, and the comparison is what makes the difference stick: the timeline finds
a warning outside you, this one travels with you.

    python3 apply_module10_week2_simpler.py --dry-run --courses data/courses_data.js
    python3 apply_module10_week2_simpler.py --courses data/courses_data.js

Standard library only. Run after apply_module10_week2_signal.py.
"""

import argparse
import json
import os
import sys

OLD = (
    "1. Explain that something is always there just before the urge \u2014 frustration, humiliation, being overwhelmed.\n"
    "2. Say there will be words to pick from, so it doesn't have to be just 'angry'.\n"
    "3. Explain that the feeling shows up physically before they act.\n"
    "4. Say why that matters: once it has started, the body is the first thing they can notice in themselves.\n"
    "5. Be clear the situation is an earlier warning still. That is what last week's timeline was for."
)
NEW = (
    "1. Explain that a feeling always comes first \u2014 frustration, humiliation, "
    "feeling overwhelmed.\n"
    "2. Say there are words to pick from, so it doesn't have to be just 'angry'.\n"
    "3. Explain that the body shows it before they act: hot face, tight fists, "
    "fast breathing.\n"
    "4. Say that is their warning sign, and unlike last week's timeline it goes "
    "everywhere with them."
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
    week = next(m for m in data if m.get("num") == 10)["weeks"][1]
    text = week.get("input") or ""

    if text == NEW:
        print("already applied, nothing to do.")
        return 0
    if text != OLD:
        print("input is not the expected text. Run apply_module10_week2_signal.py "
              "first. Nothing written.")
        return 1

    print("module 10 week 2 - input")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, NEW))
    week["input"] = NEW

    if args.dry_run:
        print("DRY RUN - nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
