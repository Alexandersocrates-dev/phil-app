#!/usr/bin/env python3
"""
Module 08 week 5: one script, any state to the finished session.

Replaces apply_module08_week5_plan.py, apply_module08_week5_table.py and
apply_module08_week5_columns.py. Run this instead of all three, in any order,
whether or not you ran them. It accepts every state those left behind.

The plan becomes a table with a column each. A stack of fields held one
situation and put the two sides two rows apart, so neither read as an exchange.
Columns are named by role, because "What I'll do" does not say who writes in it,
and the sheet is completed with the pupil and then shared with the staff member:

    The situation | The pupil will | The staff member will | Agreed by both

The first row is worked through as an example. That is also where an example
belongs: they were in cards, and card text across the packs runs to about 36
characters while these ran to 255, so the motif was drawn straight over them.

The questions are shortened. The activity was seven steps, three of which were
one instruction split up, and several carried a caution mid-question. Now five.

Colloquial wording out of all three phases: "stop telling me off", "told off",
"see me at the end", "what still feels hard", "made an actual difference".

    python3 apply_module08_week5_final.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week5_final.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: answers move from form fields to table cells, stored
under different keys, so anything already written into this plan will not carry
across. Fine on test enrolments.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("One row for each situation. The pupil completes their column, "
               "the staff member completes theirs, and the last column is "
               "agreed by both.")
BODY_KNOWN = [
    "Agreed with one or two key staff.",
    ("Agreed with one or two key staff \u2014 the ones where it matters most. Both "
     "halves get filled in. A plan that only lists what staff should change is "
     "not an agreement."),
    ("One or two key staff. Fill in a row for each thing that tends to go wrong. "
     "Both sides fill in their column, and the last one is what you settle on "
     "together."),
]

FIELDS_TARGET = ["Staff member and subject", "Review date"]
FIELDS_KNOWN = [
    ["Staff member", "What I need from them", "What they can expect from me", "Review date"],
    ["Staff member and subject", "What tends to go wrong between us",
     "What I need them to do instead", "What they can expect from me",
     "What we both do if it happens again", "Review date"],
]

TABLE_TARGET = {
    "headers": ["The situation", "The pupil will", "The staff member will",
                "Agreed by both"],
    "rows": [
        ["Example: corrected in front of the class",
         "Leave it and speak to him after the lesson",
         "Speak to him privately, not in front of others",
         "Disagreements are raised after the lesson"],
        ["", "", "", ""],
        ["", "", "", ""],
        ["", "", "", ""],
    ],
}

INPUT_TARGET = (
    "1. Ask: 'which part of this course has made a real difference?' Their "
    "earlier sheets are in this step if they need reminding.\n"
    "2. Note the answer. It goes into the plan in their own words later in this "
    "session."
)
INPUT_KNOWN = [
    ("1. Ask: 'which part of what we've done made an actual difference?' Their earlier sheets are in this step if they need reminding.\n"
     "2. Keep that answer \u2014 it goes into the plan in their words later in this session."),
]

ACT_TARGET = (
    "1. Ask: 'which one or two staff does this matter most with?' Write the name "
    "and subject at the top.\n"
    "2. Read the example row together before filling anything in.\n"
    "3. Ask: 'what situations keep going wrong?' One row for each.\n"
    "4. Work across each row: the pupil's column first, then what they would ask "
    "of the staff member, then the last column agreed between them.\n"
    "5. Set a review date, then share the plan with those staff so they can "
    "confirm or change their column."
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
    ("1. Ask: 'which one or two staff does this matter most with?' Write the name and subject at the top.\n"
     "2. Read the example row together before filling anything in.\n"
     "3. Ask: 'what tends to go wrong between you?' One row per thing, in their words.\n"
     "4. Ask: 'what will you do?' and 'what could they do instead?' Fill both columns before moving to the next row.\n"
     "5. Ask: 'so what do you both agree, then?' That last column is the one the staff member signs up to.\n"
     "6. Set a review date, then share the finished plan with those staff."),
    ("1. Ask: 'which one or two staff does this matter most with?' Write the name and subject at the top.\n"
     "2. Read the example row together before filling anything in.\n"
     "3. Ask: 'what situations keep going wrong?' One row each, in their words.\n"
     "4. Pupil completes their own column first, for every row.\n"
     "5. Fill the staff column with what the pupil would ask of them. The staff member confirms or changes it when the plan is shared.\n"
     "6. Agree the last column together. That is the line the staff member is signing up to, so it has to work for both.\n"
     "7. Set a review date, then share the finished plan with those staff."),
]

REFLECT_TARGET = (
    "1. Ask: 'which change is most likely to work?'\n"
    "2. Ask: 'what still feels difficult?' Note the answer for the course summary."
)
REFLECT_KNOWN = [
    ("1. Ask: 'which change do you think has the best chance of working?'\n"
     "2. Ask: 'what still feels hard?' Note the answer \u2014 it goes into the course summary."),
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
        print("body: already final")
    elif item.get("body") not in BODY_KNOWN:
        print("body: not a version this knows - nothing written.")
        return 1
    else:
        print("body updated")
        item["body"] = BODY_TARGET
        changes += 1

    fields = (item.get("form") or {}).get("fields")
    if fields == FIELDS_TARGET:
        print("fields: already final")
    elif fields not in FIELDS_KNOWN:
        print("fields: not a version this knows - nothing written.")
        return 1
    else:
        print("fields: %d -> %d (%s)" % (len(fields), len(FIELDS_TARGET),
                                         ", ".join(FIELDS_TARGET)))
        item["form"]["fields"] = list(FIELDS_TARGET)
        changes += 1

    if item.get("table") == TABLE_TARGET:
        print("table: already final")
    else:
        item["table"] = json.loads(json.dumps(TABLE_TARGET))
        print("table: %s" % " | ".join(TABLE_TARGET["headers"]))
        print("       row 1 worked as an example, three blank rows under it")
        changes += 1

    if item.pop("cards", None) is not None:
        print("example cards removed - the example is the table's first row")
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][4]
    for field, target, known in (("input", INPUT_TARGET, INPUT_KNOWN),
                                 ("activity", ACT_TARGET, ACT_KNOWN),
                                 ("reflect", REFLECT_TARGET, REFLECT_KNOWN)):
        text = week.get(field) or ""
        if text == target:
            print("week 5 %s: already final" % field)
            continue
        if text not in known:
            print("week 5 %s: not a version this knows - left alone" % field)
            continue
        print("=" * 72)
        print("module 08 week 5 - %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, target))
        week[field] = target
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
