#!/usr/bin/env python3
"""
Module 07 week 2: let the input teach and the activity sort.

Every line of the input was the activity in advance.

  input 2  "which of these do you reckon are yours?"
  activity 1  "which of these happen to you?"     - the same question

  input 3  "say they'll pick out the ones that are theirs and put them in order"
  activity 1-2  they pick them out and put them in order  - announced, then done

  input 4  "the top one is where a strategy is worth aiming"
  activity 3  asks about the top one

A pupil answers the sorting question in the input, then gets asked it again five
minutes later with the cards in front of them. The second time is the real one,
so the first is wasted and slightly deflating.

The input now does what the input phase is for: what a disengagement trigger is,
that everyone has some, and why the order will matter. No card handling.

Laying the cards out moves to the activity, which is where they are used. That
also moves the pill: the app places a card set at the step that produces it, so
it now renders beside the sorting instructions rather than a phase above them.
Verified.

Also fixes the watch-for comma splice, and the home task, where "which trigger,
tired, bored, distracted, shows up most" reads as a list of four things.

    python3 apply_module07_week2.py --dry-run --courses data/courses_data.js
    python3 apply_module07_week2.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "field": "input",
        "why": "was a preview of the activity, including its main question",
        "old": "1. Lay out the disengagement trigger cards face up.\n"
               "2. Ask: 'which of these do you reckon are yours?' Everyone has some \u2014 the point is which.\n"
               "3. Say they'll pick out the ones that are theirs and put them in order.\n"
               "4. Explain why the order matters: the top one is where a strategy is worth aiming.",
        "new": "1. Explain what a disengagement trigger is: the thing that makes you stop trying, not the thing that gets you in trouble.\n"
               "2. Say that everyone has some. The question is which ones are theirs.\n"
               "3. Explain why the order will matter: a strategy is worth aiming at the one that happens most.",
    },
    {
        "field": "activity",
        "why": "the cards were produced a phase before they were used",
        "old": "1. Ask: 'which of these happen to you?' Pupil picks out the ones that apply.\n"
               "2. Pupil puts their picks in order, the most common at the top.\n"
               "3. Ask: 'what makes the top one worse, and what makes it easier?'\n"
               "4. If they say none apply, ask about the last lesson that dragged.",
        "new": "1. Lay out the disengagement trigger cards face up.\n"
               "2. Ask: 'which of these happen to you?' Pupil picks out the ones that apply.\n"
               "3. Pupil puts their picks in order, the most common at the top.\n"
               "4. Ask: 'what makes the top one worse, and what makes it easier?'\n"
               "5. If they say none apply, ask about the last lesson that dragged.",
    },
    {
        "field": "lookfor",
        "why": "comma splice",
        "old": "If task difficulty is the main trigger, flag this to the class teacher, "
               "it may need an academic support response alongside this module.",
        "new": "If task difficulty is the main trigger, tell the class teacher. That "
               "one needs an academic response alongside this module, not a "
               "mentoring one on its own.",
    },
    {
        "field": "home",
        "why": "the three examples read as part of the list of things to notice",
        "old": "Notice which trigger, tired, bored, distracted, shows up most during "
               "homework time at home.",
        "new": "Notice which trigger \u2014 tired, bored, distracted \u2014 shows up most "
               "during homework at home.",
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
    week = next(m for m in data if m.get("num") == 7)["weeks"][1]

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
        print("module 07 week 2 - %s" % edit["field"])
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
        print("timing: not the expected 10/20 - left alone")

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
