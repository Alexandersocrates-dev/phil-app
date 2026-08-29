#!/usr/bin/env python3
"""
Five sessions that ask the pupil the same question twice.

Found by comparing every input line against every activity and reflect line
across all 120 sessions. Twenty pairs came back; most were a concept explained
in the input and applied in the activity, which is the right shape. These five
are the ones where the pupil genuinely answers something, then gets asked it
again in the same session.

  18 w3  "is there a date coming up that you already know will be hard?"
         asked in the input, then verbatim in the reflect.
  19 w2  "why do you think these are hard to spot?" - input and reflect.
  05 w5  "which of the things we've tried would you keep doing?" - input, then
         "which one will you actually keep doing?" in the reflect.
  10 w2  "what was the feeling just before the urge?" - input, then the same
         question in the activity where the pupil answers it properly with the
         feelings scale in front of them.
  19 w5  a fourth produce-twice: the input shows the reporting routes card and
         the activity opens by getting it out.

In each case the later ask is the real one - it happens with the resource on the
table, or after the session's work. So the input's copy goes, and the input is
left doing what it is for.

    python3 apply_asked_twice.py --dry-run --courses data/courses_data.js
    python3 apply_asked_twice.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "module": 18, "week": 3, "field": "input",
        "why": "step 2 is the reflect's question, and the reflect is where it gets acted on",
        "old": "1. Explain that particular days bring grief back strongly, even long after things settle.\n"
               "2. Ask: 'is there a date coming up that you already know will be hard?' Birthdays, anniversaries, Christmas, results day.\n"
               "3. Say why a plan helps \u2014 the day arrives whether or not you've thought about it.\n"
               "4. Show the anniversary planning card, and say the toolkit gets built around a specific date if there's one coming up.",
        "new": "1. Explain that particular days bring grief back strongly, even long after things settle.\n"
               "2. Name the kinds of day that do it: birthdays, anniversaries, Christmas, results day.\n"
               "3. Say why a plan helps \u2014 the day arrives whether or not you've thought about it.\n"
               "4. Show the anniversary planning card, and say the toolkit gets built around a specific date if there's one coming up.",
    },
    {
        "module": 19, "week": 2, "field": "input",
        "why": "step 3 is the reflect's question; the reflect asks it after the tactics have been worked through",
        "old": "1. Go through the tactics card set in plain language, one at a time.\n"
               "2. Cover being singled out for attention, gifts that create obligation, isolation from others, and secrets.\n"
               "3. Ask: 'why do you think these are hard to spot?' At the start, they feel like being valued.\n"
               "4. Say that anyone can be drawn in, including confident people. That matters \u2014 shame stops disclosure.",
        "new": "1. Go through the tactics card set in plain language, one at a time.\n"
               "2. Cover being singled out for attention, gifts that create obligation, isolation from others, and secrets.\n"
               "3. Say why they are hard to spot: at the start, all of it feels like being valued.\n"
               "4. Say that anyone can be drawn in, including confident people. That matters \u2014 shame stops disclosure.",
    },
    {
        "module": 5, "week": 5, "field": "input",
        "why": "the reflect asks the same question, and asks it after the session's work rather than before",
        "old": "1. Ask: 'which of the things we've tried would you keep doing without being asked?' Their earlier sheets are in this step if they need reminding.\n"
               "2. Keep that answer \u2014 it goes to the next teacher later in this session.",
        "new": "1. Look back over the things you've tried across the five weeks. Their earlier sheets are in this step if they need reminding.\n"
               "2. Say that what they keep doing is going to the next teacher later in this session, so it is worth thinking about now.",
    },
    {
        "module": 10, "week": 2, "field": "input",
        "why": "the activity asks this with the feelings scale in front of them, which is where it belongs",
        "old": "1. Ask: 'what was the feeling just before the urge?' Frustration, humiliation, overwhelm.\n"
               "2. Say they'll have words to pick from, so it isn't just 'angry'.\n"
               "3. Explain that the feeling shows up physically before they act.\n"
               "4. Say why that matters \u2014 the physical signal is the earliest warning they get.",
        "new": "1. Explain that something is always there just before the urge \u2014 frustration, humiliation, being overwhelmed.\n"
               "2. Say there will be words to pick from, so it doesn't have to be just 'angry'.\n"
               "3. Explain that the feeling shows up physically before they act.\n"
               "4. Say why that matters \u2014 the physical signal is the earliest warning they get.",
    },
    {
        "module": 19, "week": 5, "field": "activity",
        "why": "the input already shows the card and reads it through; the activity opened by getting it out again",
        "old": "1. Get out the reporting routes information card.\n"
               "2. Ask: 'who are two adults you'd go to?'\n"
               "3. Ask: 'do you know the school's safeguarding lead by name?' If not, tell them now.\n"
               "4. Now write both onto the safety card, with Childline's number from the reporting routes card.\n"
               "5. Ask: 'where will you keep this so it's there but private?'",
        "new": "1. Ask: 'who are two adults you'd go to?'\n"
               "2. Ask: 'do you know who leads on safeguarding here, by name?' If not, tell them now.\n"
               "3. Now write both onto the safety card, with Childline's number from the reporting routes card.\n"
               "4. Ask: 'where will you keep this so it's there but private?'",
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
        text = week.get(edit["field"]) or ""
        if text == edit["new"]:
            print("module %02d week %d %s: already applied, skipping"
                  % (edit["module"], edit["week"], edit["field"]))
            continue
        if text != edit["old"]:
            print("module %02d week %d %s: not the expected text - nothing written."
                  % (edit["module"], edit["week"], edit["field"]))
            return 1
        print("=" * 72)
        print("module %02d week %d - %s" % (edit["module"], edit["week"], edit["field"]))
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week[edit["field"]] = edit["new"]
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
