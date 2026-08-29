#!/usr/bin/env python3
"""
Module 07 week 3: teach the idea in the input, use the sheet in the activity.

All four input steps were doing something other than teaching.

  1. "Explain the idea: one task, broken into parts you can finish" describes
     the sheet, which does not appear until the activity. It is also almost
     word for word what is printed on the sheet itself - "One task, broken into
     parts you can actually finish" - so the mentor reads it out, and then the
     pupil reads it again five minutes later.

  2. "Say you'll do it with a real piece of their work in a moment" announces
     the activity. Activity step 2 then does it.

  4. "Which lesson would you try that in first?" is the reflect's question,
     asked a phase early. Reflect step 2 asks it again for real.

  3 stays, because offering a second strategy is what the week's objective
     needs - "at least one practical focus strategy" - but it now says "what
     switches them off" rather than "their top trigger", matching the check-in.

The input now explains why starting is the hard part and what makes it easier,
which is the thing the sheet is an answer to. The sheet then arrives in the
activity carrying its own description.

    python3 apply_module07_week3_input.py --dry-run --courses data/courses_data.js
    python3 apply_module07_week3_input.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = (
    "1. Explain the idea: one task, broken into parts you can finish.\n"
    "2. Say you'll do it with a real piece of their work in a moment, not a made-up task.\n"
    "3. Add one other strategy that fits their top trigger \u2014 a movement break, or a focus object.\n"
    "4. Ask: 'which lesson would you try that in first?'"
)

NEW = (
    "1. Explain why starting is the hard part: a task you can't see the end of "
    "feels bigger than it is.\n"
    "2. Say the fix is making the first bit small enough that starting is easy.\n"
    "3. Offer one other thing to try alongside it, chosen to fit what switches "
    "them off \u2014 a movement break, or something to hold."
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
    week = next(m for m in data if m.get("num") == 7)["weeks"][2]
    text = week.get("input") or ""

    if text == NEW:
        print("already applied, nothing to do.")
        return 0
    if text != OLD:
        print("input is not the expected text - nothing written.")
        return 1

    print("module 07 week 3 - input")
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
