#!/usr/bin/env python3
"""
Module 06: make the avoidance ladder readable, and stop it contradicting the session.

The sheet said "List situations from least to most anxiety-provoking, and rate
each 1-10." Four problems.

"Anxiety-provoking" is clinical register on a sheet a pupil fills in and keeps.

Two different 1s. The rows count 1 to 6, where 1 is easiest. The second column
asks for a rating 1 to 10, where 1 is least worrying. A pupil writing "1" in
row 1 has no way to know which scale that answers.

One column asking for two things. "Situation and worry rating (1-10)" put the
description and the number in the same cell, so neither is reliably there.

And the sheet never says to be specific, though the session does: "not
'lessons', but 'walking into maths late'". The session text is the mentor's; the
sheet is what the pupil looks at while writing, and that is where the rule
needs to be.

The contradiction: week 2 says to put them in order "easiest at the bottom,
hardest at the top", while the sheet runs easiest at the TOP (step 1) down to
hardest at the bottom (step 6). A mentor following the instruction fills the
ladder upside down, and week 3's "start with the smallest step" then points at
the wrong end. The week now refers to step numbers instead of a direction, which
cannot be read backwards.

Splitting the second column into two is safe: resource_entries keys cells by
position, so t<row>_0 and t<row>_1 are unchanged and anything already written
stays in the situation column, which is where it belongs. Three columns is
already proven in print - module 05's tally card has three.

    python3 apply_ladder_clarity.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_ladder_clarity.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.
"""

import argparse
import json
import os
import sys

BODY_OLD = "List situations from least to most anxiety-provoking, and rate each 1-10."
BODY_NEW = ("Six things you'd get out of if you could, in order: the one you'd "
            "find easiest at step 1, the hardest at step 6. Be specific - not "
            "'lessons', but 'walking into maths late'. Then rate how worried "
            "each one makes you, 1 to 10. You start at step 1, not step 6.")

HEADERS_OLD = ["Step", "Situation and worry rating (1-10)"]
HEADERS_NEW = ["Step", "What the situation is", "Worry 1-10"]

ACTIVITY_OLD = (
    "1. Get out the avoidance ladder template.\n"
    "2. Ask: 'what are the bits of school you'd get out of if you could?'\n"
    "3. Pupil writes each one onto the avoidance ladder.\n"
    "4. Put them in order together, easiest at the bottom, hardest at the top.\n"
    "5. Be specific: not 'lessons', but 'walking into maths late'."
)
ACTIVITY_NEW = (
    "1. Get out the avoidance ladder template.\n"
    "2. Ask: 'what are the bits of school you'd get out of if you could?'\n"
    "3. Be specific together: not 'lessons', but 'walking into maths late'.\n"
    "4. Pupil writes each one onto the ladder, easiest at step 1 and hardest at step 6.\n"
    "5. Pupil rates how worried each one makes them, 1 to 10."
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
    ap.add_argument("--packs", default=os.path.join("data", "resource_packs.json"))
    args = ap.parse_args()

    for path in (args.courses, args.packs):
        if not os.path.exists(path):
            print("cannot find %s" % path)
            return 1

    prefix, data = load_courses(args.courses)
    with open(args.packs, "r", encoding="utf-8") as fh:
        packs = json.load(fh)

    item = next((i for i in packs["06"]["items"]
                 if i.get("name") == "Avoidance ladder template"), None)
    if item is None:
        print("pack 06: ladder not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") == BODY_NEW:
        print("body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 06 - Avoidance ladder template (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    table = item.get("table") or {}
    if table.get("headers") == HEADERS_NEW:
        print("table: already applied, skipping")
    elif table.get("headers") != HEADERS_OLD:
        print("table: headers are not the expected ones - left alone")
    else:
        print("=" * 72)
        print("pack 06 - Avoidance ladder template (columns)")
        print("--- before --- %s" % HEADERS_OLD)
        print("--- after  --- %s" % HEADERS_NEW)
        table["headers"] = HEADERS_NEW
        for row in table.get("rows") or []:
            while len(row) < len(HEADERS_NEW):
                row.append("")
        print("rows padded to %d cells; step labels unchanged: %s\n"
              % (len(HEADERS_NEW), [r[0] for r in table["rows"]]))
        changes += 1

    week = next(m for m in data if m.get("num") == 6)["weeks"][1]
    text = week.get("activity") or ""
    if text == ACTIVITY_NEW:
        print("week 2 activity: already applied, skipping")
    elif text != ACTIVITY_OLD:
        print("week 2 activity: not the expected text - left alone")
    else:
        print("=" * 72)
        print("module 06 week 2 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACTIVITY_NEW))
        week["activity"] = ACTIVITY_NEW
        changes += 1

    if args.dry_run:
        print("DRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("Nothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("%d change(s) written." % changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
