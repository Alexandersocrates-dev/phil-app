#!/usr/bin/env python3
"""
Module 10: make the incident timeline hold what the session asks for.

Three rows - before, during, after - and two columns. The session needs more
than that.

The input says to work backwards, "keep asking 'and just before that?' until you
reach something ordinary". One row marked "Before" cannot hold a chain of steps,
so the whole build-up gets compressed into a single box, which is the opposite
of what the exercise is for. Five stages now run from the ordinary moment before
it to straight afterwards.

The activity asks "how long was it between the first annoyance and the damage?"
and there is nowhere to write the answer. A "roughly when" column makes the gap
visible, which is the point being taught: the build-up is longer than it feels.

The reflect asks the pupil to mark the earliest point it could have gone
differently, and there is nothing to mark. A tick column carries it, so the
pupil leaves with the interruption point on the sheet rather than in the
conversation.

Three guidance cards are added, kept to about forty characters each so the
artwork does not print over them.

    python3 apply_module10_timeline.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module10_timeline.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: table cells are keyed by position, so the row and
column changes mean anything already written on a timeline will not line up.
Fine on test enrolments.
"""

import argparse
import json
import os
import sys

BODY_OLD = "Facts only - what happened before, during and after."
BODY_NEW = ("Work backwards from the damage. Facts only \u2014 what happened and "
            "roughly when, not whose fault it was.")

TABLE_OLD = {
    "headers": ["Stage", "What happened"],
    "rows": [["Before", ""], ["During", ""], ["After", ""]],
}
TABLE_NEW = {
    "headers": ["Stage", "What happened", "Roughly when", "Could I have stopped here?"],
    "rows": [
        ["Something ordinary before it", "", "", ""],
        ["The first thing that annoyed me", "", "", ""],
        ["What built up after that", "", "", ""],
        ["The damage", "", "", ""],
        ["Straight afterwards", "", "", ""],
    ],
}

CARDS = [
    {"cat": "How to fill it", "title": "Work backwards", "art": "art-question",
     "text": "Start at the damage, not the start of the day.",
     "note": "Ask 'and just before that?'"},
    {"cat": "How to fill it", "title": "Facts, not blame", "art": "art-clock",
     "text": "What happened and roughly when.",
     "note": "No 'because he...'"},
    {"cat": "How to fill it", "title": "Find the gap", "art": "art-fork",
     "text": "Tick the earliest row you could have stopped.",
     "note": "Usually earlier than it feels"},
]

ACT_OLD = (
    "1. Get out the incident timeline template.\n"
    "2. Ask: 'can you talk me through what happened, from before it started?'\n"
    "3. Pupil fills the incident timeline: before, during, after.\n"
    "4. Stick to facts \u2014 what happened and when, not whose fault it was.\n"
    "5. Ask: 'how long was it between the first annoyance and the damage?'"
)
ACT_NEW = (
    "1. Get out the incident timeline template and read the three cards on it together.\n"
    "2. Ask: 'can you talk me through what happened?' Start at the damage and work backwards.\n"
    "3. Keep asking 'and just before that?' until you reach something ordinary. "
    "That is the top row.\n"
    "4. Fill a row for each step, with roughly what time it was.\n"
    "5. Stick to facts \u2014 what happened and when, not whose fault it was.\n"
    "6. Ask: 'how long was it, start to finish?' The answer is usually longer "
    "than the pupil expects."
)

REF_OLD = (
    "1. Ask: 'looking at that timeline, where's the earliest point it could have gone differently?'\n"
    "2. Pupil marks that point \u2014 it's usually much earlier than they expect."
)
REF_NEW = (
    "1. Ask: 'looking at that timeline, where is the earliest point it could have "
    "gone differently?'\n"
    "2. Pupil ticks that row in the last column. It is usually much earlier than "
    "they expect."
)

LOOK_OLD = ("Watch for shame or defensiveness, many pupils already feel bad about "
            "these incidents; the tone here should be understanding, not another "
            "telling-off.")
LOOK_NEW = ("Watch for shame or defensiveness. Many pupils already feel bad about "
            "these incidents, and the tone here should be understanding rather "
            "than a second reprimand.")


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
    if item is None:
        print("pack 10: timeline not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") == BODY_NEW:
        print("body: already applied")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - nothing written.")
        return 1
    else:
        print("body:\n  before: %s\n  after:  %s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    if item.get("table") == TABLE_NEW:
        print("table: already applied")
    elif item.get("table") != TABLE_OLD:
        print("table: not the expected 3x2 - nothing written.")
        return 1
    else:
        print("table")
        print("  before: %s / rows %s"
              % (" | ".join(TABLE_OLD["headers"]), [r[0] for r in TABLE_OLD["rows"]]))
        print("  after:  %s" % " | ".join(TABLE_NEW["headers"]))
        for r in TABLE_NEW["rows"]:
            print("          %s" % r[0])
        print()
        item["table"] = json.loads(json.dumps(TABLE_NEW))
        changes += 1

    if item.get("cards") == CARDS:
        print("cards: already applied")
    elif item.get("cards"):
        print("cards: item already has cards - left alone")
    else:
        item["cards"] = [dict(c) for c in CARDS]
        print("added %d guidance cards: %s"
              % (len(CARDS), ", ".join(c["title"] for c in CARDS)))
        changes += 1

    week = next(m for m in data if m.get("num") == 10)["weeks"][0]
    for field, old, new in (("activity", ACT_OLD, ACT_NEW),
                            ("reflect", REF_OLD, REF_NEW),
                            ("lookfor", LOOK_OLD, LOOK_NEW)):
        text = week.get(field) or ""
        if text == new:
            print("week 1 %s: already applied" % field)
            continue
        if text != old:
            print("week 1 %s: not the expected text - left alone" % field)
            continue
        print("=" * 72)
        print("module 10 week 1 - %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, new))
        week[field] = new
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
