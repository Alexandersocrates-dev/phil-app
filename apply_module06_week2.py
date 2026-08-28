#!/usr/bin/env python3
"""
Module 06 week 2: fix the garbled first line, and three things around it.

"Explain the trade avoidance makes: instant relief now, more fear next time."
is missing a word - the trade THAT avoidance makes - and even repaired it asks
a mentor to read a compressed clause aloud. It carries the central idea of the
whole module, so it is the worst line in the session to have to decode.

Step 2 ended "And what happened to it while you waited", which starts with And
and is not an instruction, so a mentor has to work out it is a second question.

Steps 3 and 4 are one thought cut in half: what the goal is not, then what it
is. They now read as one.

The watch-for note joins two clauses with a comma, and names the SENCO. Schools
are not structured alike, and the point is that the people around the pupil are
involved, not which post they hold.

    python3 apply_module06_week2.py --dry-run --courses data/courses_data.js
    python3 apply_module06_week2.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "field": "input",
        "why": "missing word in step 1, dangling clause in step 2, one idea split across 3 and 4",
        "old": "1. Explain the trade avoidance makes: instant relief now, more fear next time.\n"
               "2. Ask: 'have you ever put off a phone call?' And what happened to it while you waited.\n"
               "3. Say plainly that the goal is not to feel no worry. That would be a strange goal.\n"
               "4. The goal is doing the thing while the worry is there, starting small.",
        "new": "1. Explain what avoiding something buys you: relief right now, and more fear next time.\n"
               "2. Ask: 'have you ever put off a phone call?' Then ask what happened to it while they waited.\n"
               "3. Say plainly that the goal isn't to stop feeling worried \u2014 it's to do the thing while the worry is still there, starting small.",
    },
    {
        "field": "lookfor",
        "why": "comma splice, and names a post rather than describing who to involve",
        "old": "Involve parents or carers and the SENCO in building this ladder where "
               "possible, plans work best with a joined-up home-school approach.",
        "new": "Build the ladder with the people around the pupil where you can \u2014 "
               "family, and whoever supports them in school. A ladder that home "
               "and school both know about is the one that gets climbed.",
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
    week = next(m for m in data if m.get("num") == 6)["weeks"][1]

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
        print("module 06 week 2 - %s" % edit["field"])
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
