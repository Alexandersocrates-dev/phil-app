#!/usr/bin/env python3
"""
Module 05 week 2: give the mentor the game, instead of asking them to invent it.

The activity opened "Explain the game" without saying anywhere what the game
is - no rules, no name, nothing in the resources list. Step 2 then said "fire
six or seven questions quickly" without a single question. A mentor reading this
in the room has to make up the rules and a question bank on the spot, while the
pupil watches. Two mentors would run two different sessions.

Adds a quick-fire question card with two rounds of six, and rewrites the
activity to state the rules and use it.

Two rounds rather than one list, because step 4 runs the game a second time and
repeating the same six questions turns an impulse exercise into a memory one.

The questions are deliberately trivial. The point is the gap between the urge to
speak and speaking, which is what the input phase teaches. A question a pupil
might not know turns the game into a test of knowledge and gives them a reason
to stay quiet that has nothing to do with impulse.

    python3 apply_module05_game.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module05_game.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.
"""

import argparse
import json
import os
import sys

NEW_ITEM = {
    "name": "Quick-fire question card",
    "body": "Rules: you ask, they put a hand up and wait to be asked. Calling "
            "out ends the round. Read them straight down, barely pausing - the "
            "speed is what makes the urge show up.",
    "table": {
        "headers": ["Round one", "Round two"],
        "rows": [
            ["What is 2 add 2?", "What is 5 add 5?"],
            ["What colour is a banana?", "What colour is grass?"],
            ["Name a day of the week.", "Name a month of the year."],
            ["How many legs has a spider?", "How many wheels on a bike?"],
            ["What is the capital of France?", "What is the capital of Spain?"],
            ["Name a football team.", "Name a subject you do at school."],
        ],
    },
}

ACTIVITY_OLD = (
    "1. Explain the game: you'll ask easy questions, and they answer by putting a hand up, not calling out.\n"
    "2. Fire six or seven questions quickly \u2014 the speed is the point.\n"
    "3. When they slip, stop and ask: 'what did you notice just before you spoke?'\n"
    "4. Run it once more so they finish having managed it."
)

ACTIVITY_NEW = (
    "1. Explain the rules: you ask, they put a hand up and wait to be asked. "
    "Calling out ends the round.\n"
    "2. Get out the quick-fire question card and read round one straight down, "
    "barely pausing. The speed is the point.\n"
    "3. When they call out, stop and ask: 'what did you notice just before you spoke?'\n"
    "4. Run round two so they finish having managed it."
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

    changes = 0

    items = packs["05"]["items"]
    if any(i.get("name") == NEW_ITEM["name"] for i in items):
        print("pack 05: '%s' already present, skipping" % NEW_ITEM["name"])
    else:
        at = next((n for n, i in enumerate(items)
                   if i.get("name") == "Stop-think-choose technique card"), len(items) - 1)
        items.insert(at + 1, NEW_ITEM)
        print("pack 05: added '%s' after 'Stop-think-choose technique card'" % NEW_ITEM["name"])
        changes += 1

    week = next(m for m in data if m.get("num") == 5)["weeks"][1]

    text = week.get("activity") or ""
    if text == ACTIVITY_NEW:
        print("week 2 activity: already applied, skipping")
    elif text != ACTIVITY_OLD:
        print("week 2 activity: not the expected text - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 05 week 2 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACTIVITY_NEW))
        week["activity"] = ACTIVITY_NEW
        changes += 1

    if NEW_ITEM["name"] in week.get("resources", []):
        print("week 2 resources: already lists the question card")
    else:
        week.setdefault("resources", []).append(NEW_ITEM["name"])
        print("week 2 resources: now %s" % week["resources"])
        changes += 1

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\n%d change(s) written." % changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
