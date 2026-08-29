#!/usr/bin/env python3
"""
Module 07 week 4: name the subject on the sheet, and say the objective plainly.

The worksheet asks for a personal goal, then "How this subject connects to it" -
but nothing ever asks which subject. The activity does, out loud, and the answer
goes nowhere. So the pupil leaves with a sheet referring to "this subject" with
no record of which one it was, and week 5 has nothing to build on.

A row for it now sits between the goal and the link. The first row is reworded
to match what the mentor actually asks - "what do you want to be doing in two
years?" is the question; "My personal goal" is the label for it.

The objective read "Pupil can link a personal goal to effort in at least one
subject", which is three abstractions in a row and does not describe anything a
mentor could watch a pupil do.

The watch-for note is also two comma splices in one sentence.

    python3 apply_module07_week4.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module07_week4.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: table cells are keyed by position, so inserting a row
shifts everything below it. Anything already written in rows 2 and 3 of this
worksheet will appear one row lower than it belongs. There is no way to insert a
row in the middle without that. Worth knowing if any real pupil has filled one
in; harmless on test enrolments.
"""

import argparse
import json
import os
import sys

OBJ_OLD = "Pupil can link a personal goal to effort in at least one subject."
OBJ_NEW = ("Pupil can name something they want in the future, and one subject "
           "that helps them get to it.")

BODY_OLD = "Connect your work to something you care about."
BODY_NEW = ("Three things: what you want, the subject that gets you closer to "
            "it, and one thing you'll do differently this week.")

ROWS_OLD = [
    ["My personal goal", ""],
    ["How this subject connects to it", ""],
    ["One thing I'll do differently this week", ""],
]
ROWS_NEW = [
    ["What I want to be doing", ""],
    ["The subject that connects to it", ""],
    ["How it connects", ""],
    ["One thing I'll do differently this week", ""],
]

ACT_OLD = (
    "1. Ask: 'what do you want to be doing in two years?' Pupil writes it on the goal-mapping worksheet.\n"
    "2. Ask: 'which subject has anything at all to do with that?' Even loosely.\n"
    "3. Draw the line between the two on the worksheet, in their words.\n"
    "4. If they can't see a link, say so honestly and find a different subject."
)
ACT_NEW = (
    "1. Ask: 'what do you want to be doing in two years?' Pupil writes it on the goal-mapping worksheet.\n"
    "2. Ask: 'which subject has anything at all to do with that?' Even loosely. Pupil writes the subject down.\n"
    "3. Ask how it connects, and write that on the worksheet in their words.\n"
    "4. If they can't see a link, say so honestly and try a different subject."
)

LOOK_OLD = ("Keep this grounded and realistic, forced enthusiasm rarely works, "
            "a believable connection does.")
LOOK_NEW = ("Keep it believable. A connection the pupil half-invents to please "
            "you will not survive contact with a Tuesday afternoon; a loose but "
            "real one will.")


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

    week = next(m for m in data if m.get("num") == 7)["weeks"][3]
    changes = 0

    for field, old, new, label in (("objective", OBJ_OLD, OBJ_NEW, "objective"),
                                   ("activity", ACT_OLD, ACT_NEW, "activity"),
                                   ("lookfor", LOOK_OLD, LOOK_NEW, "watch-for")):
        text = week.get(field) or ""
        if text == new:
            print("week 4 %s: already applied, skipping" % label)
            continue
        if text != old:
            print("week 4 %s: not the expected text - nothing written." % label)
            return 1
        print("=" * 72)
        print("module 07 week 4 - %s" % label)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, new))
        week[field] = new
        changes += 1

    item = next((i for i in packs["07"]["items"]
                 if i.get("name") == "Goal-mapping worksheet"), None)
    if item is None:
        print("pack 07: goal-mapping worksheet not found - nothing written.")
        return 1

    if item.get("body") == BODY_NEW:
        print("worksheet body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("worksheet body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 07 - Goal-mapping worksheet (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    rows = (item.get("table") or {}).get("rows")
    if rows == ROWS_NEW:
        print("worksheet rows: already applied, skipping")
    elif rows != ROWS_OLD:
        print("worksheet rows: not the expected rows - left alone")
    else:
        print("=" * 72)
        print("pack 07 - Goal-mapping worksheet (rows)")
        for r in ROWS_OLD:
            print("   before: %s" % r[0])
        for r in ROWS_NEW:
            print("   after:  %s" % r[0])
        print()
        item["table"]["rows"] = [list(r) for r in ROWS_NEW]
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
