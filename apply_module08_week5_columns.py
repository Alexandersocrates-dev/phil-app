#!/usr/bin/env python3
"""
Module 08 week 5: say who completes each column of the plan.

The headers were "What I'll do" and "What they'll do", which do not say who
writes in them. The sheet is filled in during a session with the pupil and later
shared with the staff member, so "I" and "they" mean different people depending
on who is holding it. A staff member reading the plan sees "What they'll do" and
has no way to know that column is theirs.

Columns are now named by role, so the sheet says who completes what without the
mentor having to explain it:

    The situation | The pupil will | The staff member will | Agreed by both

The colloquial wording goes with it. "What goes wrong" becomes "The situation",
"told off" becomes "corrected", and the contraction comes out of "What we've
agreed". This is a document a school keeps and a member of staff signs up to,
so it should read like one.

    python3 apply_module08_week5_columns.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week5_columns.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_module08_week5_table.py.
"""

import argparse
import json
import os
import sys

BODY_OLD = ("One or two key staff. Fill in a row for each thing that tends to go "
            "wrong. Both sides fill in their column, and the last one is what you "
            "settle on together.")
BODY_NEW = ("One row for each situation. The pupil completes their column, the "
            "staff member completes theirs, and the last column is agreed by both.")

HEADERS_OLD = ["What goes wrong", "What I'll do", "What they'll do", "What we've agreed"]
HEADERS_NEW = ["The situation", "The pupil will", "The staff member will", "Agreed by both"]

ROW0_OLD = ["Example: I get told off in front of the class",
            "Leave it and see him at the end",
            "Say 'see me at the end' instead",
            "Sort it after the lesson, not during"]
# Two lines per cell is all that prints at this column width, so each of these
# is kept under about fifty characters.
ROW0_NEW = ["Example: corrected in front of the class",
            "Leave it and speak to him at the end",
            "Say 'see me at the end' instead",
            "Disagreements are raised after the lesson"]

ACT_OLD = (
    "1. Ask: 'which one or two staff does this matter most with?' Write the name "
    "and subject at the top.\n"
    "2. Read the example row together before filling anything in.\n"
    "3. Ask: 'what tends to go wrong between you?' One row per thing, in their words.\n"
    "4. Ask: 'what will you do?' and 'what could they do instead?' Fill both "
    "columns before moving to the next row.\n"
    "5. Ask: 'so what do you both agree, then?' That last column is the one the "
    "staff member signs up to.\n"
    "6. Set a review date, then share the finished plan with those staff."
)
ACT_NEW = (
    "1. Ask: 'which one or two staff does this matter most with?' Write the name "
    "and subject at the top.\n"
    "2. Read the example row together before filling anything in.\n"
    "3. Ask: 'what situations keep going wrong?' One row each, in their words.\n"
    "4. Pupil completes their own column first, for every row.\n"
    "5. Fill the staff column with what the pupil would ask of them. The staff "
    "member confirms or changes it when the plan is shared.\n"
    "6. Agree the last column together. That is the line the staff member is "
    "signing up to, so it has to work for both.\n"
    "7. Set a review date, then share the finished plan with those staff."
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

    item = next((i for i in packs["08"]["items"]
                 if i.get("name") == "Working relationship plan template"), None)
    if item is None or not item.get("table"):
        print("pack 08: plan table not found. Run apply_module08_week5_table.py "
              "first. Nothing written.")
        return 1

    changes = 0
    tbl = item["table"]

    if item.get("body") == BODY_NEW:
        print("body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("body:\n  before: %s\n  after:  %s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    if tbl.get("headers") == HEADERS_NEW:
        print("headers: already applied, skipping")
    elif tbl.get("headers") != HEADERS_OLD:
        print("headers: not the expected set - nothing written.")
        return 1
    else:
        for a, b in zip(HEADERS_OLD, HEADERS_NEW):
            print("  %-22s -> %s" % (a, b))
        tbl["headers"] = list(HEADERS_NEW)
        changes += 1

    rows = tbl.get("rows") or []
    if rows and rows[0] == ROW0_NEW:
        print("example row: already applied, skipping")
    elif not rows or rows[0] != ROW0_OLD:
        print("example row: not the expected text - left alone")
    else:
        print("\nexample row rewritten to match the new column roles")
        rows[0] = list(ROW0_NEW)
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][4]
    text = week.get("activity") or ""
    if text == ACT_NEW:
        print("week 5 activity: already applied, skipping")
    elif text != ACT_OLD:
        print("week 5 activity: not the expected text - left alone")
    else:
        print("\n" + "=" * 72)
        print("module 08 week 5 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACT_NEW))
        week["activity"] = ACT_NEW
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
