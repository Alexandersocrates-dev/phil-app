#!/usr/bin/env python3
"""
Module 10 week 3: raise the register, and stop the input running the activity.

"Is that rubbish?", "take the edge off" and "without anyone making a thing of it"
are the writer speaking as a teenager. A mentor reading them aloud is doing an
impression, and the wording does not survive being read by a parent or quoted in
a report. Plain is the aim, not matey.

Input step 3 also had the mentor try an outlet in the room. The activity's first
step then does exactly that, properly, two or three times. The input now
explains the idea and the activity tests it, which is the split the rest of the
course uses.

The watch-for note is one sentence held together by two commas, and names the
practical arrangements as an afterthought when they are the whole point of it.

    python3 apply_module10_week3_register.py --dry-run --courses data/courses_data.js
    python3 apply_module10_week3_register.py --courses data/courses_data.js

Standard library only.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "field": "input",
        "why": "'is that rubbish?' is doing an impression; step 3 also ran the activity early",
        "old": "1. Explain that the urge is physical, so it needs a physical outlet, not just calm words.\n"
               "2. Show the safe outlet ideas: squeezing something, tearing scrap paper, pushing against a wall.\n"
               "3. Ask: 'does squeezing something actually help, or is that rubbish?' Try one now, in the room, so it isn't theoretical.\n"
               "4. Agree where each one is actually available \u2014 an outlet they can't reach is no use.",
        "new": "1. Explain that the urge is physical, so it needs something physical to do with it, not just calm words.\n"
               "2. Show the safe outlet ideas: squeezing something, tearing scrap paper, pushing against a wall.\n"
               "3. Say plainly that they will try these out in a moment, and that it is fine to decide one of them does nothing for them.",
    },
    {
        "field": "activity",
        "why": "'take the edge off' and 'making a thing of it'; nothing recorded which one they chose",
        "old": "1. Try two or three of the safe outlet ideas here and now, properly.\n"
               "2. Ask after each: 'did that take any of the edge off?'\n"
               "3. Ask: 'which of those could you actually do at school without anyone making a thing of it?'\n"
               "4. Agree where it would be kept and who would need to know.",
        "new": "1. Try two or three of the safe outlet ideas here and now, properly.\n"
               "2. Ask after each: 'did that help at all, or not really?'\n"
               "3. Ask: 'which of those could you do at school without drawing attention?'\n"
               "4. Agree where it would be kept, and who needs to know it is there.",
    },
    {
        "field": "lookfor",
        "why": "one sentence, two commas, and the arrangements treated as an afterthought",
        "old": "The replacement needs to be immediately accessible during a real trigger, "
               "agree the practical logistics, such as where it's kept and how it's "
               "requested, with the class teacher.",
        "new": "An outlet the pupil cannot reach in the moment is not an outlet. Agree "
               "with the class teacher where it is kept and how the pupil asks for "
               "it, before the session ends.",
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
    week = next(m for m in data if m.get("num") == 10)["weeks"][2]

    changes = 0
    for edit in EDITS:
        text = week.get(edit["field"]) or ""
        if text == edit["new"]:
            print("week 3 %s: already applied" % edit["field"])
            continue
        if text != edit["old"]:
            print("week 3 %s: not the expected text - nothing written." % edit["field"])
            return 1
        print("=" * 72)
        print("module 10 week 3 - %s" % edit["field"])
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
