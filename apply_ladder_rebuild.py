#!/usr/bin/env python3
"""
Module 06: rebuild the avoidance ladder so it says what to do, not just what's hard.

The sheet named six things a pupil avoids and rated them, and stopped there.
Week 3 then asks them to take the smallest step - but nowhere on the ladder is
there a place to write what that step would be, so the thinking happens once,
out loud, and is gone by the time they need it.

It now has three columns a pupil fills in themselves:

    What you'd avoid | A first step towards it | How hard, 1-10

The fixed "1 (easiest)" ... "6 (hardest)" labels are gone. They were the only
cells on the sheet a pupil could not type into, and the ordering they carried
sits in the body instead, where it does not cost a column.

Three worked examples are added as cards above the table, following the pattern
of module 02's assertive disagreement card - examples first, blank rows under
them. Without them "a first step" is an abstraction, and the whole idea of the
module is that the step is smaller than the thing itself.

    python3 apply_ladder_rebuild.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_ladder_rebuild.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: resource_entries keys table cells by position, and
this removes the leftmost column, so anything a pupil has already written on a
ladder will show up one column to the right of where it belongs. There is no way
to add a column on the left without that happening. Worth knowing before running
it against real pupil data rather than test enrolments.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("Six things you'd get out of if you could, the easiest at the "
               "top. Look at the examples, then fill in your own. A first step "
               "is always smaller than the thing itself.")

BODY_KNOWN = [
    "List situations from least to most anxiety-provoking, and rate each 1-10.",
    ("Six things you'd get out of if you could, in order: the one you'd find "
     "easiest at step 1, the hardest at step 6. Be specific - not 'lessons', "
     "but 'walking into maths late'. Then rate how worried each one makes you, "
     "1 to 10. You start at step 1, not step 6."),
    ("Six things you'd get out of if you could, one per row. Step 1 is the "
     "easiest, step 6 the hardest. Be specific: not 'lessons', but 'walking "
     "into maths late'."),
]

CARDS = [
    {
        "cat": "Example",
        "title": "Walking into maths late",
        "art": "art-clock",
        "text": "First step: wait outside the door for the last few minutes of "
                "break, so you walk in with everyone else.",
        "note": "Smaller than the whole thing",
    },
    {
        "cat": "Example",
        "title": "The lunch hall",
        "art": "art-friends-out",
        "text": "First step: go in with one person, stay two minutes, then leave.",
        "note": "Two minutes still counts",
    },
    {
        "cat": "Example",
        "title": "Answering in class",
        "art": "art-talk",
        "text": "First step: answer one question you already know the answer to.",
        "note": "Pick the easy one on purpose",
    },
]

HEADERS_TARGET = ["What you'd avoid", "A first step towards it", "How hard, 1-10"]
ROWS_TARGET = [["", "", ""] for _ in range(6)]

HEADERS_KNOWN = [
    ["Step", "Situation and worry rating (1-10)"],
    ["Step", "What the situation is", "Worry 1-10"],
    ["Step", "What you'd avoid", "How worried, 1-10"],
]

ACTIVITY_TARGET = (
    "1. Get out the avoidance ladder template.\n"
    "2. Ask: 'what are the bits of school you'd get out of if you could?'\n"
    "3. Be specific together: not 'lessons', but 'walking into maths late'.\n"
    "4. Pupil writes each one onto the ladder, easiest at the top.\n"
    "5. Read the examples together, then pupil writes a first step for each one.\n"
    "6. Pupil rates how hard each one would be, 1 to 10."
)

ACTIVITY_KNOWN = [
    ("1. Get out the avoidance ladder template.\n"
     "2. Ask: 'what are the bits of school you'd get out of if you could?'\n"
     "3. Pupil writes each one onto the avoidance ladder.\n"
     "4. Put them in order together, easiest at the bottom, hardest at the top.\n"
     "5. Be specific: not 'lessons', but 'walking into maths late'."),
    ("1. Get out the avoidance ladder template.\n"
     "2. Ask: 'what are the bits of school you'd get out of if you could?'\n"
     "3. Be specific together: not 'lessons', but 'walking into maths late'.\n"
     "4. Pupil writes each one onto the ladder, easiest at step 1 and hardest at step 6.\n"
     "5. Pupil rates how worried each one makes them, 1 to 10."),
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

    item = next((i for i in packs["06"]["items"]
                 if i.get("name") == "Avoidance ladder template"), None)
    if item is None:
        print("pack 06: ladder not found - nothing written.")
        return 1

    changes = 0

    body = item.get("body")
    if body == BODY_TARGET:
        print("body: already applied, skipping")
    elif body not in BODY_KNOWN:
        print("body: not a version this knows - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("body\n--- before ---\n%s\n--- after ---\n%s\n" % (body, BODY_TARGET))
        item["body"] = BODY_TARGET
        changes += 1

    if item.get("cards") == CARDS:
        print("example cards: already applied, skipping")
    elif item.get("cards"):
        print("example cards: this item already has cards - left alone")
    else:
        print("=" * 72)
        print("example cards added (render above the table):")
        for c in CARDS:
            print("   %-26s %s" % (c["title"], c["text"][:66]))
        print()
        item["cards"] = CARDS
        changes += 1

    table = item.get("table") or {}
    if table.get("headers") == HEADERS_TARGET:
        print("table: already applied, skipping")
    elif table.get("headers") not in HEADERS_KNOWN:
        print("table: headers are not a version this knows - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("table\n--- before --- %s" % table.get("headers"))
        print("               rows: %s" % [r[0] for r in table.get("rows") or []])
        print("--- after  --- %s" % HEADERS_TARGET)
        print("               rows: 6, every cell blank and editable\n")
        table["headers"] = list(HEADERS_TARGET)
        table["rows"] = [list(r) for r in ROWS_TARGET]
        changes += 1

    week = next(m for m in data if m.get("num") == 6)["weeks"][1]
    act = week.get("activity") or ""
    if act == ACTIVITY_TARGET:
        print("week 2 activity: already applied, skipping")
    elif act not in ACTIVITY_KNOWN:
        print("week 2 activity: not a version this knows - left alone")
    else:
        print("=" * 72)
        print("module 06 week 2 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (act, ACTIVITY_TARGET))
        week["activity"] = ACTIVITY_TARGET
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
