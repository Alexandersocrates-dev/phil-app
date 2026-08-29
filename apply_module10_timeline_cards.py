#!/usr/bin/env python3
"""
Module 10: replace the incident timeline grid with an example and blank lines.

A four-column, five-row grid asks a pupil to hold the whole shape of an incident
in mind while deciding which of twenty boxes each fragment belongs in. That is
hard on its own, and this sheet is filled in while talking about something the
pupil is probably ashamed of.

It becomes the pattern used elsewhere in the packs: a worked example first, then
blank lines for their own. Five example cards walk one incident through from an
ordinary moment to the aftermath, with the time on each so the gap is visible
without a column for it. Underneath, six lines the pupil writes on.

The last line is the one the reflect asks for - the earliest point they could
have stopped - which the grid handled with a tick column nobody explained.

Replaces both the original three-row table and the expanded five-row one, so it
can be run whether or not the earlier timeline scripts were applied.

    python3 apply_module10_timeline_cards.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module10_timeline_cards.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: answers move from table cells to form fields, stored
under different keys, so anything already written on a timeline will not carry
across.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("Read the example first, then fill in your own. Start with what "
               "you did and work back up. Facts and times, not blame.")

CARDS_TARGET = [
    {"cat": "Example", "title": "What I was doing before", "art": "art-clock",
     "text": "12:35 - walking back from lunch, normal day.",
     "note": "Somewhere ordinary"},
    {"cat": "Example", "title": "The first thing that bothered me", "art": "art-bump",
     "text": "12:50 - someone knocked my bag off the desk.",
     "note": "The first thing, not the worst"},
    {"cat": "Example", "title": "How it built up", "art": "art-too-hard",
     "text": "12:55 - nobody said sorry. I sat there getting angrier.",
     "note": "This bit is usually the longest"},
    {"cat": "Example", "title": "What I did", "art": "art-stop",
     "text": "1:05 - kicked the chair over and slammed the door.",
     "note": "Facts only"},
    {"cat": "Example", "title": "What happened after", "art": "art-door-exit",
     "text": "1:10 - sent out, missed the rest of the lesson.",
     "note": "Including what it cost you"},
]

FIELDS_TARGET = [
    "What I was doing before (and what time)",
    "The first thing that bothered me",
    "How it built up",
    "What I did",
    "What happened after",
    "The earliest point I could have stopped",
]


def load_courses(path):
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    prefix, body = src.split("=", 1)
    body = body.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return prefix + "= ", json.loads(body)


ACT_TARGET = (
    "1. Get out the incident timeline and read the example through together, top to bottom.\n"
    "2. Ask: 'what did you do?' Fill that line in first.\n"
    "3. Work back up the sheet, asking 'and just before that?' for each line.\n"
    "4. Add roughly what time each one was, as in the example.\n"
    "5. Ask: 'how long was it, start to finish?' Usually longer than they expect."
)
ACT_KNOWN = [
    ("1. Get out the incident timeline template.\n"
     "2. Ask: 'can you talk me through what happened, from before it started?'\n"
     "3. Pupil fills the incident timeline: before, during, after.\n"
     "4. Stick to facts \u2014 what happened and when, not whose fault it was.\n"
     "5. Ask: 'how long was it between the first annoyance and the damage?'"),
    ("1. Get out the incident timeline template and read the three cards on it together.\n"
     "2. Ask: 'can you talk me through what happened?' Start at the damage and work backwards.\n"
     "3. Keep asking 'and just before that?' until you reach something ordinary. That is the top row.\n"
     "4. Fill a row for each step, with roughly what time it was.\n"
     "5. Stick to facts \u2014 what happened and when, not whose fault it was.\n"
     "6. Ask: 'how long was it, start to finish?' The answer is usually longer than the pupil expects."),
    ("1. Get out the incident timeline and read the three cards on it together.\n"
     "2. Start at the damage. Fill that row in first.\n"
     "3. Work up the sheet, asking 'and just before that?' for each row.\n"
     "4. Add roughly what time each one was.\n"
     "5. Ask: 'how long was it, start to finish?' Usually longer than they expect."),
    ("1. Get out the incident timeline and read the three cards on it together.\n"
     "2. Start with the 'what I did' row. Fill that one in first.\n"
     "3. Work up the sheet, asking 'and just before that?' for each row.\n"
     "4. Add roughly what time each one was.\n"
     "5. Ask: 'how long was it, start to finish?' Usually longer than they expect."),
]

REF_TARGET = (
    "1. Ask: 'looking at that, where is the earliest point it could have gone differently?'\n"
    "2. Pupil writes it on the last line. It is usually much earlier than they expect."
)
REF_KNOWN = [
    ("1. Ask: 'looking at that timeline, where's the earliest point it could have gone differently?'\n"
     "2. Pupil marks that point \u2014 it's usually much earlier than they expect."),
    ("1. Ask: 'looking at that timeline, where is the earliest point it could have gone differently?'\n"
     "2. Pupil ticks that row in the last column. It is usually much earlier than they expect."),
]


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
    if item is None:
        print("pack 10: timeline not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") != BODY_TARGET:
        item["body"] = BODY_TARGET
        print("body: %s" % BODY_TARGET)
        changes += 1
    else:
        print("body: already applied")

    if item.pop("table", None) is not None:
        print("table removed")
        changes += 1

    if item.get("cards") != CARDS_TARGET:
        item["cards"] = [dict(c) for c in CARDS_TARGET]
        print("example: %d cards walking one incident through" % len(CARDS_TARGET))
        for c in CARDS_TARGET:
            print("   %-34s %s" % (c["title"], c["text"]))
        changes += 1
    else:
        print("example cards: already applied")

    if (item.get("form") or {}).get("fields") != FIELDS_TARGET:
        item["form"] = {"fields": list(FIELDS_TARGET)}
        print("\nblank lines for their own:")
        for f in FIELDS_TARGET:
            print("   %s" % f)
        changes += 1
    else:
        print("blank lines: already applied")

    week = next(m for m in data if m.get("num") == 10)["weeks"][0]
    for field, target, known in (("activity", ACT_TARGET, ACT_KNOWN),
                                 ("reflect", REF_TARGET, REF_KNOWN)):
        text = week.get(field) or ""
        if text == target:
            print("week 1 %s: already applied" % field)
        elif text not in known:
            print("week 1 %s: not a version this knows - left alone" % field)
        else:
            week[field] = target
            print("week 1 %s updated" % field)
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
