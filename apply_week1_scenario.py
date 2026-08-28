#!/usr/bin/env python3
"""
Module 04 week 1: get a situation on the table before handing over the structure.

The input phase showed the four restorative questions and asked whether it was
fair that everyone involved gets asked the same ones — before anything had been
established about what happened or who was involved. The pupil only got asked
for a fall-out in the activity, one phase later.

It also presumed there was one. The check-in opened "something unrelated to the
conflict", and the activity asked for "a fall-out you've had recently". A pupil
can be on this module for a running pattern, because staff noticed something, or
as a bystander — week 3 covers that role explicitly. If nothing recent comes to
mind, the session as written had no content.

Week 2 already solves this, twice: it models with a neutral example first, and
allows "a made-up one if that's still too raw". This brings week 1 into line.

    python3 apply_week1_scenario.py --dry-run
    python3 apply_week1_scenario.py

Standard library only. Writes courses_data.js. Independent of
apply_restorative_fix.py — they touch different fields, so order doesn't matter.
"""

import argparse
import json
import os
import sys

COURSES = "courses_data.js"

EDITS = [
    {
        "field": "objective",
        "why": "required a real recent conflict to exist",
        "old": "Pupil can describe a recent conflict from a personal perspective "
               "without assigning blame to start.",
        "new": "Pupil can describe a conflict from their own perspective, real "
               "or made up, without starting from blame.",
    },
    {
        "field": "checkin",
        "why": "'unrelated to the conflict' presumes a known conflict",
        "old": "1. Start with something unrelated to the conflict — what they're into, how the week went.",
        "new": "1. Start with something unrelated — what they're into, how the week went.",
    },
    {
        "field": "input",
        "why": "handed over the four questions before any situation existed to apply them to",
        "old": "1. Show the restorative question prompt card and read the four questions aloud.\n"
               "2. Ask: 'is it fair that everyone involved gets asked the same four questions?'\n"
               "3. Explain that you'll work through them one at a time, with room to think between each.\n"
               "4. Say you won't be correcting their version — you're collecting it, not testing it.",
        "new": "1. Ask: 'is there a fall-out with someone that's still on your "
               "mind?' Take whatever comes back, including 'not really'.\n"
               "2. If nothing comes, use something smaller — a group chat, "
               "someone who went quiet on them — or a made-up one. Either works "
               "today; it's the structure they're learning.\n"
               "3. Show the restorative question prompt card and read the four "
               "questions aloud.\n"
               "4. Ask: 'does it seem fair that everyone involved gets asked "
               "these same four questions?' Today you're doing their part of it.\n"
               "5. Say you'll take them one at a time with room to think, and "
               "you won't be correcting their version — you're collecting it, "
               "not testing it.",
    },
    {
        "field": "activity",
        "why": "asked for the fall-out here, one phase after the questions were introduced",
        "old": "1. Ask: 'can you tell me about a fall-out you've had recently?'\n"
               "2. Work through the four restorative questions on the card, one at a time.",
        "new": "1. Take the situation from the input and work through the four "
               "questions on the card, one at a time.",
    },
    {
        "field": "lookfor",
        "why": "didn't say a made-up situation is a full session, not a fallback",
        "old": "Keep this session focused on the pupil's own experience, "
               "perspective-taking on the other party comes later, so don't rush it.",
        "new": "Keep this session focused on the pupil's own experience — "
               "perspective-taking on the other party comes later, so don't rush "
               "it. A made-up fall-out does the job as well as a real one; the "
               "structure is what's being learnt, and a pupil with nothing recent "
               "is not a session without content.",
    },
]

# The elicitation moves out of the activity and into the input, so the minutes
# follow it. Total is unchanged at 45.
TIMING = {"input": 12, "activity": 18}
TIMING_OLD = {"input": 10, "activity": 20}


def load_courses(path):
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    prefix, body = src.split("=", 1)
    body = body.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return prefix + "= ", json.loads(body)


def renumber(text):
    out, n = [], 0
    for line in text.split("\n"):
        head = line.lstrip().split(". ", 1)
        if len(head) == 2 and head[0].isdigit():
            n += 1
            out.append("%d. %s" % (n, head[1]))
        else:
            out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--courses", default=COURSES)
    args = ap.parse_args()

    if not os.path.exists(args.courses):
        print("cannot find %s — run this from the clone root" % args.courses)
        return 1

    prefix, data = load_courses(args.courses)
    module = next((m for m in data if m.get("num") == 4), None)
    if module is None:
        print("module 04 not found — stopping, nothing written")
        return 1
    week = module["weeks"][0]

    changes = 0
    for edit in EDITS:
        text = week.get(edit["field"]) or ""
        if edit["new"] in text:
            print("week 1 %s: already applied, skipping" % edit["field"])
            continue
        if text.count(edit["old"]) != 1:
            print("week 1 %s: expected text not found exactly once (found %d) "
                  "— stopping, nothing written"
                  % (edit["field"], text.count(edit["old"])))
            return 1
        updated = renumber(text.replace(edit["old"], edit["new"]))
        print("=" * 72)
        print("module 04 week 1 — %s" % edit["field"])
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
        week[edit["field"]] = updated
        changes += 1

    timing = week.get("timing") or {}
    if all(timing.get(k) == v for k, v in TIMING.items()):
        print("timing: already applied, skipping")
    elif all(timing.get(k) == v for k, v in TIMING_OLD.items()):
        timing.update(TIMING)
        print("timing: input 10 -> 12, activity 20 -> 18 (total unchanged at %d)"
              % sum(timing.values()))
        changes += 1
    else:
        print("timing: not the expected 10/20 — left alone, check it by hand")

    if args.dry_run:
        print("\nDRY RUN — %d change(s) would be made, nothing written." % changes)
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
