#!/usr/bin/env python3
"""
Module 04 week 2: say plainly what the next phase is.

"Explain that you'll walk the same fall-out round from the other side, one
question at a time."

Two faults. "Walk round from the other side" is a figure of speech that has to
be decoded before it means anything, and a mentor reading this out loud has to
paraphrase it on the spot. And "one question at a time" describes the wrong
activity — that phrasing belongs to week 1, which works through four restorative
questions in order. Week 2 asks two: what were they thinking, and how were they
feeling.

    python3 apply_week2_reword.py --dry-run --courses data/courses_data.js
    python3 apply_week2_reword.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = ("4. Explain that you'll walk the same fall-out round from the other "
       "side, one question at a time.")

NEW = ("4. Say what's coming next: the same fall-out as last week, but "
       "answering as the other person.")


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
    week = next(m for m in data if m.get("num") == 4)["weeks"][1]
    text = week.get("input") or ""

    if NEW in text:
        print("already applied, nothing to do.")
        return 0
    if text.count(OLD) != 1:
        print("expected text not found exactly once — nothing written.")
        return 1

    updated = text.replace(OLD, NEW)
    print("module 04 week 2 — input")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
    week["input"] = updated

    if args.dry_run:
        print("DRY RUN — nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
