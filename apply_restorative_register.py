#!/usr/bin/env python3
"""
Module 08 week 4: define a restorative conversation in plain, precise language.

"A way of sorting out a fall-out so both people can get on afterwards" was too
colloquial for a definition. Plain and colloquial are not the same thing: the
sentence a mentor reads out to define a term should be simple enough for a
fourteen-year-old and precise enough that it does not sound like slang.

    a structured conversation that repairs a relationship after something has
    gone wrong between two people

Every word is one a pupil knows, and it says what the thing is rather than what
it feels like. It also matches the session's own title, Repair and restore.

    python3 apply_restorative_register.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_restorative_register.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_restorative_define.py.
"""

import argparse
import json
import os
import sys

BODY_OLD = ("A way of sorting out a fall-out so both people can get on "
            "afterwards. Both answer the same five questions, in the same "
            "order. Nobody apologises on cue.")
BODY_NEW = ("A structured conversation that repairs a relationship after "
            "something has gone wrong. Both people answer the same five "
            "questions, in the same order. Nobody apologises on cue.")

INPUT_OLD = (
    "1. Explain what a restorative conversation is: a way of sorting out a "
    "fall-out so both people can get on afterwards.\n"
    "2. Say it's used between friends, at home and at work. Here it's with a "
    "member of staff.\n"
    "3. Say it isn't an apology for its own sake. Ask: 'what would an apology be "
    "for \u2014 you, or them?'\n"
    "4. Say the point is making a room easier to be in, not deciding who was "
    "right. They'll be in that lesson twice a week either way.\n"
    "5. Say plainly this is not the soft option: both people answer the same five "
    "questions, and both agree to something.\n"
    "6. Show the restorative conversation prompt card and read the five questions.\n"
    "7. Say they choose who it's with, and whether they want you there. They can "
    "also choose not to."
)

INPUT_NEW = (
    "1. Explain what a restorative conversation is: a structured conversation "
    "that repairs a relationship after something has gone wrong between two "
    "people.\n"
    "2. Say it is used in schools, workplaces and families. Here it is with a "
    "member of staff.\n"
    "3. Say it is not an apology for its own sake. Ask: 'what would an apology be "
    "for \u2014 you, or them?'\n"
    "4. Say the aim is to make a room easier to work in, not to decide who was "
    "right. They will be in that lesson twice a week either way.\n"
    "5. Say plainly this is not the soft option: both people answer the same five "
    "questions, and both agree to something.\n"
    "6. Show the restorative conversation prompt card and read the five questions.\n"
    "7. Say they choose who it is with, and whether they want you there. They can "
    "also choose not to."
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

    item = next((i for i in packs["08"]["items"]
                 if i.get("name") == "Restorative conversation prompt card"), None)
    if item is None:
        print("pack 08: prompt card not found - nothing written.")
        return 1

    if item.get("body") == BODY_NEW:
        print("card body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("card body: not the expected text. Run apply_restorative_define.py first.")
        return 1
    else:
        print("=" * 72)
        print("pack 08 - card body")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][3]
    text = week.get("input") or ""
    if text == INPUT_NEW:
        print("week 4 input: already applied, skipping")
    elif text != INPUT_OLD:
        print("week 4 input: not the expected text - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 08 week 4 - input")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, INPUT_NEW))
        week["input"] = INPUT_NEW
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
