#!/usr/bin/env python3
"""
Module 07 week 3: ask the check-in questions in words a pupil uses.

    1. Ask: 'of the triggers you picked out last week, which one came up most?'
    2. Ask: 'what did you do when it happened?'
    3. Whatever they did is the current strategy, even if it's leaving the room.

Three things.

"Triggers" is the mentor's word for it. Week 2 is titled "What switches me off"
and that is the phrase the pupil met and used, so the check-in should reach for
the same one rather than the technical term for it.

"Came up most" does not say where or when. A pupil hears it as a question about
the whole of their life; the mentor means this week, in lessons.

And nothing covers the pupil who cannot remember. Week 2 has a fallback for
exactly this - "if they say none apply, ask about the last lesson that dragged" -
and without one here the session stalls on its first question. That fallback is
now step 2.

Step 3 was a note to the mentor sitting in a list of instructions, so it reads
like something to say to the pupil. It is now written as what to do.

    python3 apply_module07_week3_checkin.py --dry-run --courses data/courses_data.js
    python3 apply_module07_week3_checkin.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

OLD = (
    "1. Ask: 'of the triggers you picked out last week, which one came up most?'\n"
    "2. Ask: 'what did you do when it happened?'\n"
    "3. Whatever they did is the current strategy, even if it's leaving the room."
)

NEW = (
    "1. Ask: 'which of the things that switch you off happened most this week?'\n"
    "2. If they can't think of one, ask about the last lesson that dragged.\n"
    "3. Ask: 'and what did you do when it happened?'\n"
    "4. Don't correct the answer. Whatever they did is their strategy at the "
    "moment, even if it was walking out."
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
    text = week.get("checkin") or ""

    if text == NEW:
        print("already applied, nothing to do.")
        return 0
    if text != OLD:
        print("check-in is not the expected text - nothing written.")
        return 1

    print("module 07 week 3 - checkin")
    print("--- before ---\n%s\n--- after ---\n%s\n" % (text, NEW))
    week["checkin"] = NEW

    if args.dry_run:
        print("DRY RUN - nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("1 change written to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
