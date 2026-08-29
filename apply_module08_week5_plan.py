#!/usr/bin/env python3
"""
Module 08 week 5: make the working relationship plan a plan two people can keep.

Four fields - staff member, what I need from them, what they can expect from me,
review date - and a one-line body. Three things missing.

Nowhere to name the problem. The plan jumps straight to what each side should do
without recording what actually goes wrong between them, so a staff member
reading it has to remember the incident it came out of. "What tends to go wrong"
now sits second, in the pupil's words.

Nothing for when it happens again. It will. A plan with no repair clause fails
the first time either side slips, because neither knows what happens next. "What
we do if it happens again" is the field that keeps the plan alive past the first
bad Tuesday.

No examples. "What I need from them" invites "stop telling me off", which is a
complaint rather than something a teacher can do. Two worked examples now sit
above the form, showing the shape: a specific, small, doable action on each side.

    python3 apply_module08_week5_plan.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week5_plan.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.

NOTE ON EXISTING ENTRIES: form answers are keyed by position (f0, f1, ...), so
inserting a field shifts everything after it. Anything already written into
fields 2, 3 and 4 of this plan will appear one row lower. No way round it when
adding a field mid-form. Fine on test enrolments; check first if a real pupil
has completed module 08.
"""

import argparse
import json
import os
import sys

BODY_OLD = "Agreed with one or two key staff."
BODY_NEW = ("Agreed with one or two key staff \u2014 the ones where it matters most. "
            "Both halves get filled in. A plan that only lists what staff should "
            "change is not an agreement.")

FIELDS_OLD = ["Staff member", "What I need from them",
              "What they can expect from me", "Review date"]
FIELDS_NEW = ["Staff member and subject",
              "What tends to go wrong between us",
              "What I need them to do instead",
              "What they can expect from me",
              "What we both do if it happens again",
              "Review date"]

CARDS = [
    {
        "cat": "Example",
        "title": "Being told off in front of everyone",
        "art": "art-talked-over",
        "text": "Goes wrong: I get told off in front of the class and I answer "
                "back. They do: say my name and 'see me at the end' instead. "
                "I do: leave it and go to him at the end, not argue in the room. "
                "If it happens again: I write it down and we sort it after the lesson.",
        "note": "Something they could actually do",
    },
    {
        "cat": "Example",
        "title": "Work I don't understand",
        "art": "art-too-hard",
        "text": "Goes wrong: I don't get the work so I put my head down and do "
                "nothing. They do: check on me in the first five minutes without "
                "making it obvious. I do: put my hand up once before giving up. "
                "If it happens again: I finish what I can and show her at the end.",
        "note": "Small enough to do every lesson",
    },
]

ACT_OLD = (
    "1. Ask: 'which one or two staff does this matter most with?'\n"
    "2. Ask: 'what should they do instead of telling you off in front of everyone?'\n"
    "3. Ask: 'and what will you do differently?' Both halves matter \u2014 it's not a list of staff duties.\n"
    "4. Now write all of that into the working relationship plan, and set a review date.\n"
    "5. Share the finished plan with those staff."
)
ACT_NEW = (
    "1. Ask: 'which one or two staff does this matter most with?'\n"
    "2. Ask: 'what tends to go wrong between you?' Their words, on the plan.\n"
    "3. Read the two examples on the plan together before going further.\n"
    "4. Ask: 'what could they do instead?' Something they could actually do, not "
    "'stop telling me off'.\n"
    "5. Ask: 'and what will you do differently?' Both halves matter \u2014 it's not a "
    "list of staff duties.\n"
    "6. Ask: 'what do you both do if it happens again anyway?' It will, and the "
    "plan needs to survive it.\n"
    "7. Set a review date, then share the finished plan with those staff."
)

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
    ap.add_argument("--packs", default=os.path.join("data", "resource_packs.json"))
    args = ap.parse_args()

    for path in (args.courses, args.packs):
        if not os.path.exists(path):
            print("cannot find %s" % path)
            return 1

    prefix, data = load_courses(args.courses)
    with open(args.packs, "r", encoding="utf-8") as fh:
        packs = json.load(fh)

    item = next((i for i in packs["08"]["items"]
                 if i.get("name") == "Working relationship plan template"), None)
    if item is None:
        print("pack 08: plan template not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") == BODY_NEW:
        print("body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("body\n--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    fields = (item.get("form") or {}).get("fields")
    if fields == FIELDS_NEW:
        print("fields: already applied, skipping")
    elif fields != FIELDS_OLD:
        print("fields: not the expected four - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("fields")
        for f in FIELDS_OLD:
            print("   before: %s" % f)
        for f in FIELDS_NEW:
            print("   after:  %s" % f)
        print()
        item["form"]["fields"] = list(FIELDS_NEW)
        changes += 1

    if item.get("cards") == CARDS:
        print("examples: already applied, skipping")
    elif item.get("cards"):
        print("examples: item already has cards - left alone")
    else:
        item["cards"] = [dict(c) for c in CARDS]
        print("added %d worked examples: %s"
              % (len(CARDS), "; ".join(c["title"] for c in CARDS)))
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][4]
    text = week.get("activity") or ""
    if text == ACT_NEW:
        print("week 5 activity: already applied, skipping")
    elif text != ACT_OLD:
        print("week 5 activity: not the expected text - left alone")
    else:
        print("=" * 72)
        print("module 08 week 5 - activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACT_NEW))
        week["activity"] = ACT_NEW
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
    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\n%d change(s) written." % changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
