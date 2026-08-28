#!/usr/bin/env python3
"""
Module 04 week 1: one idea per line, and stop saying it twice.

Three faults in the input phase as it stands.

Layered lines. Step 1 asks a question and then tells the mentor how to receive
the answer. Step 2 gives a fallback, then a second fallback, then the reason for
both. Step 5 carries pacing and a reassurance in one sentence. The house style
elsewhere in these courses is one point per line.

An abstract question aimed at a pupil. "Does it seem fair that everyone involved
gets asked these same four questions?" asks a young person to evaluate the
fairness of a process they have not been through, and no answer to it changes
what happens next. The neutrality it was carrying is already said plainly in the
check-in and again when the mentor says they won't be correcting anything.

Saying the same thing in both phases. The input read the four questions aloud
and promised to take them one at a time; the activity then worked through the
four questions on the card, one at a time. The input's job is to put the card on
the table. The activity's job is to use it.

    python3 apply_week1_simplify.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_week1_simplify.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_week1_scenario.py.
"""

import argparse
import json
import os
import sys

INPUT_OLD = (
    "1. Ask: 'is there a fall-out with someone that's still on your mind?' "
    "Take whatever comes back, including 'not really'.\n"
    "2. If nothing comes, use something smaller — a group chat, someone who "
    "went quiet on them — or a made-up one. Either works today; it's the "
    "structure they're learning.\n"
    "3. Show the restorative question prompt card and read the four questions aloud.\n"
    "4. Ask: 'does it seem fair that everyone involved gets asked these same "
    "four questions?' Today you're doing their part of it.\n"
    "5. Say you'll take them one at a time with room to think, and you won't be "
    "correcting their version — you're collecting it, not testing it."
)

INPUT_NEW = (
    "1. Ask: 'is there a fall-out with someone that's still on your mind?'\n"
    "2. If nothing comes, use a smaller one, or make one up. It works the same.\n"
    "3. Show the restorative question prompt card.\n"
    "4. Read the four questions aloud.\n"
    "5. Say you won't be correcting their answers."
)

ACTIVITY_OLD = (
    "1. Take the situation from the input and work through the four questions "
    "on the card, one at a time."
)

ACTIVITY_NEW = (
    "1. Work through the four questions, one at a time, on the situation from the input."
)

# The card carried the same fault: three ideas in two sentences.
CARD_OLDS = [
    "Asked of everyone involved, not just one pupil. One at a time.",
    "The four questions a restorative conversation uses, asked here of one "
    "pupil about their own part. One at a time. You're collecting their "
    "account, not testing it.",
]
CARD_NEW = "The four questions a restorative conversation asks. Here, one pupil, about their own part."


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

    week = next(m for m in data if m.get("num") == 4)["weeks"][0]
    changes = 0

    for field, old, new in (("input", INPUT_OLD, INPUT_NEW),
                            ("activity", ACTIVITY_OLD, ACTIVITY_NEW)):
        text = week.get(field) or ""
        if new in text:
            print("week 1 %s: already applied, skipping" % field)
            continue
        if text.count(old) != 1:
            print("week 1 %s: expected text not found exactly once (found %d). "
                  "Run apply_week1_scenario.py first. Nothing written."
                  % (field, text.count(old)))
            return 1
        updated = text.replace(old, new)
        print("=" * 72)
        print("module 04 week 1 — %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
        week[field] = updated
        changes += 1

    item = next((i for i in packs["04"]["items"]
                 if i.get("name") == "Restorative question prompt card"), None)
    if item is None:
        print("pack 04: restorative card not found — nothing written")
        return 1
    if item.get("body") == CARD_NEW:
        print("pack 04 card body: already applied, skipping")
    elif item.get("body") in CARD_OLDS:
        print("=" * 72)
        print("pack 04 — Restorative question prompt card (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (item["body"], CARD_NEW))
        item["body"] = CARD_NEW
        changes += 1
    else:
        print("pack 04 card body: not a version this knows — left alone")

    if args.dry_run:
        print("DRY RUN — %d change(s) would be made, nothing written." % changes)
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
