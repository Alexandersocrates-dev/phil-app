#!/usr/bin/env python3
"""
Module 05 week 4: anchor the scale once, with the chart in front of you.

Five problems, found by reading the whole session rather than the one line that
prompted it.

1. The input explained a one-to-five rating on a chart that doesn't appear until
   the activity. The mentor describes how to use a sheet they can't show.

2. The scale gets anchored twice. Input step 4 asked "what would a 3 look like
   for you?" and activity step 2 asked "what would a five look like for you, and
   what would a one look like?" - the same exercise, done in two phases, and a
   pupil who answered it once is asked again ten minutes later.

3. The activity anchored the scale AFTER using it. Step 1 filled a row in for a
   real lesson; step 2 then worked out what the numbers mean. So the first
   rating a pupil ever gives is on a scale nobody has defined yet, which is
   exactly the inconsistency the anchoring exists to prevent.

4. The objective claimed the pupil "can use the agreed signal across at least
   one real lesson". Using the signal was last week's home task, checked in this
   week's check-in. Nothing in this session practises it. The session sets up
   the chart, so the objective should say so.

5. The watch-for note is a comma splice, and "loop in the class teacher" is the
   kind of phrase the copyedit took out elsewhere.

    python3 apply_module05_week4.py --dry-run --courses data/courses_data.js
    python3 apply_module05_week4.py --courses data/courses_data.js

Standard library only. Touches courses_data.js only - the chart itself is fine.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "field": "objective",
        "why": "claimed the pupil practises the signal; this session sets up the chart",
        "old": "Pupil can use the agreed signal across at least one real lesson, "
               "tracked with a self-monitoring chart.",
        "new": "Pupil can rate their own self-control on an agreed one-to-five "
               "scale, and has a chart set up for the week ahead.",
    },
    {
        "field": "input",
        "why": "described how to use a chart that isn't on screen until the activity, "
               "and anchored the scale a phase early",
        "old": "1. Explain the one-to-five rating they'll be using to score their own lessons.\n"
               "2. Make clear the pupil rates themselves \u2014 nobody else marks it.\n"
               "3. Say why it gets filled in straight after a lesson: by home time the detail has gone.\n"
               "4. Ask: 'what would a 3 look like for you?' So the numbers mean something consistent.",
        "new": "1. Say what this week adds: keeping a short record of how each lesson went.\n"
               "2. Make clear the pupil rates themselves \u2014 nobody else marks it.\n"
               "3. Say why it gets filled in straight after a lesson: by home time the detail has gone.",
    },
    {
        "field": "activity",
        "why": "rated a real lesson before working out what the numbers meant",
        "old": "1. Take a lesson from this week and fill the self-monitoring chart in together, so they've done one with you.\n"
               "2. Ask: 'what would a five look like for you, and what would a one look like?'\n"
               "3. Pupil picks which lessons to track this week and writes them on the chart.\n"
               "4. Agree when they'll fill it in \u2014 end of the lesson, not the end of the day.",
        "new": "1. Get out the self-monitoring chart and read the one-to-five scale on it.\n"
               "2. Ask: 'what would a five look like for you, and what would a one look like?'\n"
               "3. Note their words. The numbers only mean anything if they mean the same thing each time.\n"
               "4. Take a lesson from this week and fill a row in together, so they've done one with you.\n"
               "5. Pupil picks which lessons to track this week and writes them on the chart.\n"
               "6. Agree when they'll fill it in \u2014 end of the lesson, not the end of the day.",
    },
    {
        "field": "lookfor",
        "why": "comma splice, and 'loop in' is the register the copyedit removed elsewhere",
        "old": "Self-monitoring is most effective when paired with brief, positive "
               "teacher feedback, loop in the class teacher where possible.",
        "new": "Self-monitoring works best alongside brief, positive feedback from "
               "the class teacher. Where you can, tell the teacher what the pupil "
               "is tracking and what to look for.",
    },
]

TIMING_OLD = {"input": 10, "activity": 20}
TIMING_NEW = {"input": 8, "activity": 22}


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
    week = next(m for m in data if m.get("num") == 5)["weeks"][3]

    changes = 0
    for edit in EDITS:
        text = week.get(edit["field"]) or ""
        if text == edit["new"]:
            print("week 4 %s: already applied, skipping" % edit["field"])
            continue
        if text != edit["old"]:
            print("week 4 %s: not the expected text - nothing written." % edit["field"])
            return 1
        print("=" * 72)
        print("module 05 week 4 - %s" % edit["field"])
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week[edit["field"]] = edit["new"]
        changes += 1

    timing = week.get("timing") or {}
    if all(timing.get(k) == v for k, v in TIMING_NEW.items()):
        print("timing: already applied, skipping")
    elif all(timing.get(k) == v for k, v in TIMING_OLD.items()):
        timing.update(TIMING_NEW)
        print("timing: input 10 -> 8, activity 20 -> 22 (total unchanged at %d)"
              % sum(timing.values()))
        changes += 1
    else:
        print("timing: not the expected 10/20 - left alone, check it by hand")

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("\n%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
