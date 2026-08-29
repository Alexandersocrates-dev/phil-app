#!/usr/bin/env python3
"""
Module 08 week 2: fill the whole worksheet, and fix the writing around it.

The worksheet has four rows. The activity fills one.

    What happened                              nothing writes this
    What I was thinking                        nothing writes this
    What the adult might have been managing    <- the only row the activity fills
    What I could try differently               nothing writes this

So a pupil takes away a sheet that is three-quarters blank, and the row that
matters most - what they would do next time - is never reached. The activity now
works down the sheet, with the "this doesn't mean they were right" line placed
before the last question rather than after everything, which is where it needs to
sit if the pupil is about to be asked to change something.

Wording, in the rows and around them:

  - The rows sit under a heading that says "Question" and none of them was one.
  - "What the adult might have been managing" - managing is doing a lot of work
    there; a pupil reads it as line management.
  - "Explore a recent incident with a specific staff member" is written to an
    adult about a pupil, on a sheet the pupil fills in.
  - "Pupil fills that into the worksheet" - fills in, or writes on.
  - The watch-for note is a comma splice, and the home task has four commas
    holding up one sentence.
  - Input step 4 announces the activity, which the activity then does.

    python3 apply_module08_week2.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week2.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Row count is unchanged, so nothing already written moves.
"""

import argparse
import json
import os
import sys

BODY_OLD = "Explore a recent incident with a specific staff member."
BODY_NEW = "One fall-out with a member of staff, looked at from both sides."

ROWS_OLD = [
    ["What happened", ""],
    ["What I was thinking", ""],
    ["What the adult might have been managing", ""],
    ["What I could try differently", ""],
]
ROWS_NEW = [
    ["What happened?", ""],
    ["What was I thinking at the time?", ""],
    ["What might the adult have been dealing with?", ""],
    ["What could I try differently next time?", ""],
]

EDITS = [
    {
        "field": "input",
        "why": "step 2 ran a question and a caution together; step 4 announced the activity",
        "old": "1. Explain that staff are managing thirty people, a timetable and safety at once.\n"
               "2. Ask: 'how many people is a teacher keeping track of at once?' This doesn't excuse an adult being unfair or rude.\n"
               "3. Say why it's worth knowing anyway: it makes an adult's reaction predictable rather than personal.\n"
               "4. Say that you'll work out together what the adult might have been dealing with.",
        "new": "1. Explain that staff are managing thirty people, a timetable and safety all at once.\n"
               "2. Ask: 'how many people do you think a teacher is keeping track of at once?'\n"
               "3. Be clear that none of this excuses an adult being unfair or rude.\n"
               "4. Say why it's worth knowing anyway: it makes an adult's reaction predictable rather than personal.",
    },
    {
        "field": "activity",
        "why": "three of the worksheet's four rows were never filled",
        "old": "1. Ask: 'can you tell me about a time recently you fell out with a member of staff?'\n"
               "2. Ask: 'what do you think was going on for them right then?' Pupil fills that into the worksheet.\n"
               "3. Ask: 'what were they probably worried about in that moment?' Add it.\n"
               "4. Say plainly this doesn't mean they were right \u2014 you're working out what was going on.",
        "new": "1. Ask: 'can you tell me about a time recently when you fell out with a member of staff?' "
               "Pupil writes what happened on the worksheet.\n"
               "2. Ask: 'what were you thinking at the time?' Pupil adds that.\n"
               "3. Ask: 'what do you think that adult was dealing with right then?' Pupil adds that too.\n"
               "4. Say plainly that this doesn't mean the adult was right. You're working out what was "
               "going on, not who was in the wrong.\n"
               "5. Ask: 'knowing that, what could you try differently next time?' Pupil writes it in the last row.",
    },
    {
        "field": "lookfor",
        "why": "comma splice",
        "old": "Balance this carefully, the goal is perspective, not making the pupil feel at "
               "fault for an adult's poor handling of a situation.",
        "new": "Balance this carefully. The goal is perspective, not making a pupil feel at "
               "fault for how an adult handled something.",
    },
    {
        "field": "home",
        "why": "four commas holding up one sentence",
        "old": "Gently point out a moment where an adult, including you, was under pressure, "
               "to build the same perspective-taking at home.",
        "new": "Point out a moment when an adult was under pressure \u2014 you included. It builds "
               "the same habit at home.",
    },
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

    week = next(m for m in data if m.get("num") == 8)["weeks"][1]
    changes = 0

    for edit in EDITS:
        text = week.get(edit["field"]) or ""
        if text == edit["new"]:
            print("week 2 %s: already applied, skipping" % edit["field"])
            continue
        if text != edit["old"]:
            print("week 2 %s: not the expected text - nothing written." % edit["field"])
            return 1
        print("=" * 72)
        print("module 08 week 2 - %s" % edit["field"])
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week[edit["field"]] = edit["new"]
        changes += 1

    item = next((i for i in packs["08"]["items"]
                 if i.get("name") == "Perspective-taking worksheet (staff)"), None)
    if item is None:
        print("pack 08: worksheet not found - nothing written.")
        return 1

    if item.get("body") == BODY_NEW:
        print("worksheet body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("worksheet body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 08 - worksheet body")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    rows = (item.get("table") or {}).get("rows")
    if rows == ROWS_NEW:
        print("worksheet rows: already applied, skipping")
    elif rows != ROWS_OLD:
        print("worksheet rows: not the expected rows - left alone")
    else:
        print("=" * 72)
        print("pack 08 - worksheet rows (count unchanged, so nothing written moves)")
        for a, b in zip(ROWS_OLD, ROWS_NEW):
            print("   %-42s -> %s" % (a[0], b[0]))
        print()
        item["table"]["rows"] = [list(r) for r in ROWS_NEW]
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
