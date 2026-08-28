#!/usr/bin/env python3
"""
Module 05 week 2: say what the game is for, and cover the runs that go well.

Three things were missing from the activity.

The pupil is never told what the game is for. From their side it looks like a
pointless quiz about bananas and capital cities, and a pupil who thinks they are
being tested on knowledge has a reason to stay quiet that has nothing to do with
impulse. The input phase has already taught the gap between the urge and the
speaking; the game is practice at catching it, and saying so out loud is what
connects the two.

Calling out reads as failure. "Calling out ends the round" told the pupil what
not to do without telling them that the slip is the useful part - it is the only
moment where the gap becomes visible. It also left the mentor unsure whether to
stop entirely or carry on.

Nothing covered a clean run. If the pupil got through six questions without
calling out, the mentor had no instruction at all, so the one pupil who managed
it got the least out of it.

The card body repeated the rules the mentor had just read aloud in step 1. It
now carries what the steps don't: what the sheet is for, and that it is the
mentor's to read from rather than the pupil's to look at.

    python3 apply_module05_game_clarity.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module05_game_clarity.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_module05_game.py.
"""

import argparse
import json
import os
import sys

ACTIVITY_OLD = (
    "1. Explain the rules: you ask, they put a hand up and wait to be asked. "
    "Calling out ends the round.\n"
    "2. Get out the quick-fire question card and read round one straight down, "
    "barely pausing. The speed is the point.\n"
    "3. When they call out, stop and ask: 'what did you notice just before you spoke?'\n"
    "4. Run round two so they finish having managed it."
)

ACTIVITY_NEW = (
    "1. Say what it's for: 'this isn't about the answers. It's practice at "
    "catching the moment before you speak - the gap we just talked about.'\n"
    "2. Give the rules: you ask, they put a hand up and wait to be asked.\n"
    "3. Say plainly that calling out isn't losing. It's the moment you both "
    "want to catch, so it's worth something when it happens.\n"
    "4. Read round one off the quick-fire question card, straight down, barely "
    "pausing. Don't wait for a right answer - the speed is what brings the urge "
    "up.\n"
    "5. Each time they call out, stop and ask: 'what did you notice just before "
    "you spoke?' Then pick up where you left off.\n"
    "6. If they get all the way through, ask which one was hardest to hold in.\n"
    "7. Run round two, then tell them one thing you saw them do differently, "
    "however small."
)

BODY_OLD = ("Rules: you ask, they put a hand up and wait to be asked. Calling "
            "out ends the round. Read them straight down, barely pausing - the "
            "speed is what makes the urge show up.")

BODY_NEW = ("Your sheet to read from, not one to hand over - the game needs the "
            "questions to be a surprise. Practice at catching the gap between "
            "wanting to speak and speaking, not a test of what they know.")


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

    week = next(m for m in data if m.get("num") == 5)["weeks"][1]
    text = week.get("activity") or ""
    if text == ACTIVITY_NEW:
        print("week 2 activity: already applied, skipping")
    elif text != ACTIVITY_OLD:
        print("week 2 activity: not the expected text. Run apply_module05_game.py "
              "first. Nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 05 week 2 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACTIVITY_NEW))
        week["activity"] = ACTIVITY_NEW
        changes += 1

    item = next((i for i in packs["05"]["items"]
                 if i.get("name") == "Quick-fire question card"), None)
    if item is None:
        print("pack 05: question card not found. Run apply_module05_game.py "
              "first. Nothing written.")
        return 1
    if item.get("body") == BODY_NEW:
        print("pack 05 card body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("pack 05 card body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 05 - Quick-fire question card (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    # The elicitation and the debrief both grew; the minutes come from the
    # check-in, which is reading a tally that is already filled in.
    timing = week.get("timing") or {}
    if timing.get("activity") == 22:
        print("timing: already applied, skipping")
    elif timing.get("activity") == 20 and timing.get("checkin") == 5:
        timing["activity"] = 22
        timing["checkin"] = 3
        print("timing: checkin 5 -> 3, activity 20 -> 22 (total unchanged at %d)"
              % sum(timing.values()))
        changes += 1
    else:
        print("timing: not the expected 5/20 - left alone, check it by hand")

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
