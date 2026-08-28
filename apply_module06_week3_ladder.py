#!/usr/bin/env python3
"""
Module 06 week 3: put the avoidance ladder back on the page.

The check-in opens "Look at the ladder together and read the steps out", but the
ladder is not in week 3's resources, so nothing renders. The mentor is told to
read from a sheet that isn't there, and the pupil's own ranking - the whole
output of week 2 - is invisible in the session that acts on it.

No code change is needed. attach_earlier_entries already carries what a pupil
wrote on a resource in an earlier week, and falls back to the blank sheet when
they wrote nothing. Listing the ladder in week 3 is enough to get both
behaviours: last week's rungs if they filled it in, an empty ladder if they
didn't.

Also names the ladder in the check-in line rather than calling it "the ladder",
so the app can match the wording to the pack item, and adds a comparison
question so the earlier answers render at the line that asks about them rather
than beside the blank sheet - _COMPARE_LINE looks for "has it changed" and
similar.

    python3 apply_module06_week3_ladder.py --dry-run --courses data/courses_data.js
    python3 apply_module06_week3_ladder.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

LADDER = "Avoidance ladder template"

CHECKIN_OLD = (
    "1. Look at the ladder together and read the steps out.\n"
    "2. Ask: 'did you try any step on the ladder, even partly?'\n"
    "3. A partial attempt counts. Say so before they tell you it doesn't."
)

CHECKIN_NEW = (
    "1. Get out the avoidance ladder template and read their steps back to them.\n"
    "2. Ask: 'did you try any step on the ladder, even partly?'\n"
    "3. A partial attempt counts. Say so before they tell you it doesn't.\n"
    "4. Ask what has changed about the order, if anything, since last week."
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
    module = next(m for m in data if m.get("num") == 6)
    week2, week3 = module["weeks"][1], module["weeks"][2]

    if LADDER not in (week2.get("resources") or []):
        print("module 06 week 2 does not list '%s' - nothing written." % LADDER)
        return 1

    changes = 0

    text = week3.get("checkin") or ""
    if text == CHECKIN_NEW:
        print("week 3 checkin: already applied, skipping")
    elif text != CHECKIN_OLD:
        print("week 3 checkin: not the expected text - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 06 week 3 - checkin")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, CHECKIN_NEW))
        week3["checkin"] = CHECKIN_NEW
        changes += 1

    resources = week3.setdefault("resources", [])
    if LADDER in resources:
        print("week 3 resources: already lists the ladder")
    else:
        # Ahead of the step-planning worksheet: the check-in reads the ladder
        # before the activity fills the worksheet in.
        resources.insert(0, LADDER)
        print("week 3 resources: now %s" % resources)
        changes += 1

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("\n%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
