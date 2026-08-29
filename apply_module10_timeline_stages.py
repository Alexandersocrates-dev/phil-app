#!/usr/bin/env python3
"""
Module 10: name the timeline's stages in the pupil's own terms.

"First annoyance", "It built up" and "The damage" are the writer's summary of
each stage rather than a prompt a pupil can answer. "First annoyance" in
particular is a noun a pupil has to translate before they can fill the row in.

Every stage is now a first-person phrase that answers itself:

    What I was doing before
    The first thing that bothered me
    How it built up
    What I did
    What happened after

"What I did" for the damage row is deliberate. It is the plainest possible
description and it puts the pupil in the sentence without any of the blame
language the sheet exists to avoid - the body already says facts, not blame,
and "The damage" was the one label that read like a charge sheet.

    python3 apply_module10_timeline_stages.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module10_timeline_stages.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_module10_timeline_simpler.py.
"""

import argparse
import json
import os
import sys

STAGES_OLD = ["Before it started", "First annoyance", "It built up",
              "The damage", "Afterwards"]
STAGES_NEW = ["What I was doing before", "The first thing that bothered me",
              "How it built up", "What I did", "What happened after"]

CARD_OLD = {"title": "Start at the bottom",
            "text": "Fill in the damage first, then work up."}
CARD_NEW = {"title": "Start at the bottom",
            "text": "Fill in what you did first, then work up."}

ACT_OLD = (
    "1. Get out the incident timeline and read the three cards on it together.\n"
    "2. Start at the damage. Fill that row in first.\n"
    "3. Work up the sheet, asking 'and just before that?' for each row.\n"
    "4. Add roughly what time each one was.\n"
    "5. Ask: 'how long was it, start to finish?' Usually longer than they expect."
)
ACT_NEW = (
    "1. Get out the incident timeline and read the three cards on it together.\n"
    "2. Start with the 'what I did' row. Fill that one in first.\n"
    "3. Work up the sheet, asking 'and just before that?' for each row.\n"
    "4. Add roughly what time each one was.\n"
    "5. Ask: 'how long was it, start to finish?' Usually longer than they expect."
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

    item = next((i for i in packs["10"]["items"]
                 if i.get("name") == "Incident timeline template"), None)
    if item is None or not item.get("table"):
        print("pack 10: timeline not found. Run the earlier timeline scripts first.")
        return 1

    changes = 0
    rows = item["table"]["rows"]
    current = [r[0] for r in rows]

    if current == STAGES_NEW:
        print("stages: already applied")
    elif current != STAGES_OLD:
        print("stages: not the expected set. Run apply_module10_timeline_simpler.py "
              "first. Nothing written.")
        return 1
    else:
        for a, b in zip(STAGES_OLD, STAGES_NEW):
            print("   %-20s -> %s" % (a, b))
        for r, name in zip(rows, STAGES_NEW):
            r[0] = name
        changes += 1

    card = next((c for c in item.get("cards") or []
                 if c.get("title") == CARD_OLD["title"]), None)
    if card is None:
        print("card: not found - left alone")
    elif card.get("text") == CARD_NEW["text"]:
        print("card: already applied")
    elif card.get("text") != CARD_OLD["text"]:
        print("card: not the expected text - left alone")
    else:
        print("\n   card: %s -> %s" % (CARD_OLD["text"], CARD_NEW["text"]))
        card["text"] = CARD_NEW["text"]
        changes += 1

    week = next(m for m in data if m.get("num") == 10)["weeks"][0]
    text = week.get("activity") or ""
    if text == ACT_NEW:
        print("week 1 activity: already applied")
    elif text != ACT_OLD:
        print("week 1 activity: not the expected text - left alone")
    else:
        print("\n   activity step 2 now names the row rather than the incident")
        week["activity"] = ACT_NEW
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
