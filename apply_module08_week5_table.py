#!/usr/bin/env python3
"""
Module 08 week 5: turn the working relationship plan into a two-sided table.

The plan was a stack of six fields. Two problems with that shape.

It only holds one situation. A pupil who has trouble in two lessons for two
different reasons has to pick one, or write both into the same box.

And it does not show the two sides against each other. The whole point of the
plan is that both people do something, and a list of fields separates "what I
need from them" from "what they can expect from me" by two rows, so neither side
reads as an exchange. In a table they sit next to each other on one line, with a
fourth column for what the two of them settle on together.

    What goes wrong | What I'll do | What they'll do | What we've agreed

The first row is worked through as an example. That also fixes the overlapping
artwork on the download: the examples were in cards, and card text across the
packs runs to about 36 characters, while these ran to 255. The motif is drawn at
a fixed place in the card, so text that long ran underneath it. An example
belongs in the shape it is an example of, not in a card beside it.

Staff member and review date stay as fields above the table, since they apply to
the whole plan rather than to a row.

    python3 apply_module08_week5_table.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week5_table.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_module08_week5_plan.py, or instead of it.

NOTE ON EXISTING ENTRIES: this moves answers from form fields to table cells,
which are stored under different keys. Anything already written into this plan
will not carry across. Fine on test enrolments; check first if a real pupil has
completed module 08.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("One or two key staff. Fill in a row for each thing that tends "
               "to go wrong. Both sides fill in their column, and the last one "
               "is what you settle on together.")

BODY_KNOWN = [
    "Agreed with one or two key staff.",
    ("Agreed with one or two key staff \u2014 the ones where it matters most. Both "
     "halves get filled in. A plan that only lists what staff should change is "
     "not an agreement."),
]

FIELDS_TARGET = ["Staff member and subject", "Review date"]
FIELDS_KNOWN = [
    ["Staff member", "What I need from them", "What they can expect from me", "Review date"],
    ["Staff member and subject", "What tends to go wrong between us",
     "What I need them to do instead", "What they can expect from me",
     "What we both do if it happens again", "Review date"],
]

TABLE_TARGET = {
    "headers": ["What goes wrong", "What I'll do", "What they'll do", "What we've agreed"],
    "rows": [
        ["Example: I get told off in front of the class",
         "Leave it and see him at the end",
         "Say 'see me at the end' instead",
         "Sort it after the lesson, not during"],
        ["", "", "", ""],
        ["", "", "", ""],
        ["", "", "", ""],
    ],
}

ACT_TARGET = (
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

ACT_KNOWN = [
    ("1. Ask: 'which one or two staff does this matter most with?'\n"
     "2. Ask: 'what should they do instead of telling you off in front of everyone?'\n"
     "3. Ask: 'and what will you do differently?' Both halves matter \u2014 it's not a list of staff duties.\n"
     "4. Now write all of that into the working relationship plan, and set a review date.\n"
     "5. Share the finished plan with those staff."),
    ("1. Ask: 'which one or two staff does this matter most with?'\n"
     "2. Ask: 'what tends to go wrong between you?' Their words, on the plan.\n"
     "3. Read the two examples on the plan together before going further.\n"
     "4. Ask: 'what could they do instead?' Something they could actually do, not 'stop telling me off'.\n"
     "5. Ask: 'and what will you do differently?' Both halves matter \u2014 it's not a list of staff duties.\n"
     "6. Ask: 'what do you both do if it happens again anyway?' It will, and the plan needs to survive it.\n"
     "7. Set a review date, then share the finished plan with those staff."),
]


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
    if item is None:
        print("pack 08: plan template not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") == BODY_TARGET:
        print("body: already applied, skipping")
    elif item.get("body") not in BODY_KNOWN:
        print("body: not a version this knows - nothing written.")
        return 1
    else:
        print("body updated")
        item["body"] = BODY_TARGET
        changes += 1

    fields = (item.get("form") or {}).get("fields")
    if fields == FIELDS_TARGET:
        print("fields: already applied, skipping")
    elif fields not in FIELDS_KNOWN:
        print("fields: not a version this knows - nothing written.")
        return 1
    else:
        print("fields: %s  ->  %s" % (fields, FIELDS_TARGET))
        item["form"]["fields"] = list(FIELDS_TARGET)
        changes += 1

    if item.get("table") == TABLE_TARGET:
        print("table: already applied, skipping")
    else:
        item["table"] = json.loads(json.dumps(TABLE_TARGET))
        print("table added: %s" % " | ".join(TABLE_TARGET["headers"]))
        print("   row 1 is a worked example; three blank rows follow")
        changes += 1

    if item.pop("cards", None) is not None:
        print("example cards removed - the example is now the table's first row")
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][4]
    text = week.get("activity") or ""
    if text == ACT_TARGET:
        print("week 5 activity: already applied, skipping")
    elif text not in ACT_KNOWN:
        print("week 5 activity: not a version this knows - left alone")
    else:
        print("=" * 72)
        print("module 08 week 5 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACT_TARGET))
        week["activity"] = ACT_TARGET
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
