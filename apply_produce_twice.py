#!/usr/bin/env python3
"""
Three sessions that produce the same resource twice.

Found by running the app's own assign_resources_to_steps over all 120 sessions
and looking for a step that tells the mentor to produce something when no
resource renders at that step.

In each of these the input already shows the sheet and does teaching work with
it - reads the levels, reads the four questions, reads the order of the steps.
The activity then opens with "Get out the X", which is already out and sitting
in the phase above. A mentor following it literally looks for something they are
holding.

The activity's line is the redundant one, so it goes. The input keeps its
instruction, because it is doing more than producing the sheet.

This does not move any pill: all three already render in the input, which is
where the app places reference material a mentor shows. Verified before and
after.

    python3 apply_produce_twice.py --dry-run --courses data/courses_data.js
    python3 apply_produce_twice.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "module": 8, "week": 4,
        "why": "input step 3 already shows the card and reads its four questions",
        "old": "1. Get out the restorative conversation prompt card.\n"
               "2. Ask: 'which member of staff would be most worth sorting things out with?'\n"
               "3. Work through the restorative prompts together so they know what they'll say.\n"
               "4. Rehearse it with you playing the adult, twice.\n"
               "5. If the staff member agrees and the pupil is willing, hold the real conversation with you there.",
        "new": "1. Ask: 'which member of staff would be most worth sorting things out with?'\n"
               "2. Work through the restorative prompts together so they know what they'll say.\n"
               "3. Rehearse it with you playing the adult, twice.\n"
               "4. If the staff member agrees and the pupil is willing, hold the real conversation with you there.",
    },
    {
        "module": 11, "week": 1,
        "why": "input steps 1 and 4 already show the thermometer and the word cards",
        "old": "1. Get out the feeling word cards and the anger thermometer together.\n"
               "2. Ask: 'which of these words have you actually felt?' Pupil picks the ones that apply and places each on the thermometer, coolest at the bottom.\n"
               "3. Go through two or three and ask: 'when was the last time you felt that one?'\n"
               "4. Point out the gap between the words they normally use and the words they've just placed.",
        "new": "1. Ask: 'which of these words have you actually felt?' Pupil picks the ones that apply and places each on the thermometer, coolest at the bottom.\n"
               "2. Go through two or three and ask: 'when was the last time you felt that one?'\n"
               "3. Point out the gap between the words they normally use and the words they've just placed.",
    },
    {
        "module": 15, "week": 3,
        "why": "input step 1 already shows the step card and reads its order",
        "old": "1. Get out the block, report, save evidence step card.\n"
               "2. Ask: 'which app would you actually need this on?'\n"
               "3. Walk the block, report and save steps on that one, using a practice account or the printed screenshots.\n"
               "4. Pupil does it themselves, not just watches.\n"
               "5. Ask: 'where would the screenshot end up, so it isn't lost?'",
        "new": "1. Ask: 'which app would you actually need this on?'\n"
               "2. Walk the block, report and save steps on that one, using a practice account or the printed screenshots.\n"
               "3. Pupil does it themselves, not just watches.\n"
               "4. Ask: 'where would the screenshot end up, so it isn't lost?'",
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
    args = ap.parse_args()

    if not os.path.exists(args.courses):
        print("cannot find %s" % args.courses)
        return 1

    prefix, data = load_courses(args.courses)
    changes = 0

    for edit in EDITS:
        module = next((m for m in data if m.get("num") == edit["module"]), None)
        if module is None:
            print("module %02d not found - nothing written." % edit["module"])
            return 1
        week = module["weeks"][edit["week"] - 1]
        text = week.get("activity") or ""
        if text == edit["new"]:
            print("module %02d week %d: already applied, skipping"
                  % (edit["module"], edit["week"]))
            continue
        if text != edit["old"]:
            print("module %02d week %d: not the expected text - nothing written."
                  % (edit["module"], edit["week"]))
            return 1
        print("=" * 72)
        print("module %02d week %d - activity" % (edit["module"], edit["week"]))
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week["activity"] = edit["new"]
        changes += 1

    if args.dry_run:
        print("DRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("Nothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
