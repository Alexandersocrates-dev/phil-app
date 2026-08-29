#!/usr/bin/env python3
"""
Module 08 week 4: one script, current live state to final wording.

This replaces apply_restorative_simpler.py, apply_restorative_define.py and
apply_restorative_register.py, which were three passes over the same session and
had to be run in order. Run this instead of all three. Running it after any of
them is harmless: it accepts every intermediate state and leaves the file at the
same place.

What it does.

Defines the term before correcting it. The input opened "a restorative
conversation isn't an apology for its own sake" - a correction to a definition
the pupil had never been given. It now says what one is first:

    a structured conversation that repairs a relationship after something has
    gone wrong between two people

Drops "a working relationship the pupil still needs". That phrasing hands the
pupil the obvious reply - I don't need anything from her - and once said out
loud they have to defend it for the rest of the session. The reason to have the
conversation is that they will be in that lesson twice a week either way, which
is a fact rather than a claim about what they need.

Shortens the question cards. They grew wordy when the research went in. A prompt
card is read at a glance, mid-conversation, by someone also running the
conversation, so each now carries one short line with the guidance moved to the
note underneath.

    python3 apply_module08_week4_final.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module08_week4_final.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_restorative_research.py.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("A structured conversation that repairs a relationship after "
               "something has gone wrong. Both people answer the same five "
               "questions, in the same order. Nobody apologises on cue.")

BODY_KNOWN = [
    ("For repairing one working relationship the pupil still needs. Both people "
     "answer the same questions, in the same order, and neither is asked to "
     "apologise on cue."),
    ("Both people answer the same five questions, in the same order. Nobody is "
     "asked to apologise on cue."),
    ("A way of sorting out a fall-out so both people can get on afterwards. Both "
     "answer the same five questions, in the same order. Nobody apologises on cue."),
]

CARDS_TARGET = [
    {"cat": "Question 1", "title": "What happened?", "art": "art-question",
     "text": "Both of you answer.", "note": "Let each finish"},
    {"cat": "Question 2", "title": "What were you thinking at the time?",
     "art": "art-body-signals",
     "text": "Explains it. Doesn't excuse it.", "note": "Don't argue with the answer"},
    {"cat": "Question 3", "title": "What have you thought about since?",
     "art": "art-thoughts",
     "text": "The one that changes things.", "note": "Wait. Don't fill the silence"},
    {"cat": "Question 4", "title": "Who else has this affected?",
     "art": "art-apart",
     "text": "Not just the two of you.", "note": "Name people, not 'everyone'"},
    {"cat": "Question 5", "title": "What would put this right?",
     "art": "art-repair",
     "text": "One thing each.", "note": "Something you'd actually do"},
]

INPUT_TARGET = (
    "1. Explain what a restorative conversation is: a structured conversation "
    "that repairs a relationship after something has gone wrong between two "
    "people.\n"
    "2. Say it is used in schools, workplaces and families. Here it is with a "
    "member of staff.\n"
    "3. Say it is not an apology for its own sake. Ask: 'what would an apology be "
    "for \u2014 you, or them?'\n"
    "4. Say the aim is to make a room easier to work in, not to decide who was "
    "right. They will be in that lesson twice a week either way.\n"
    "5. Say plainly this is not the soft option: both people answer the same five "
    "questions, and both agree to something.\n"
    "6. Show the restorative conversation prompt card and read the five questions.\n"
    "7. Say they choose who it is with, and whether they want you there. They can "
    "also choose not to."
)

INPUT_KNOWN = [
    ("1. Explain that a restorative conversation isn't an apology for its own sake.\n"
     "2. Ask: 'what would an apology be for \u2014 you, or them?' Its purpose is repairing one working relationship they still need.\n"
     "3. Say plainly that this is not the soft option. Both people answer the same five questions, and both have to agree to something.\n"
     "4. Show the restorative conversation prompt card and read the five questions.\n"
     "5. Say they choose which relationship is worth repairing, and whether they want you there. They can also choose not to."),
    ("1. Explain that a restorative conversation isn't an apology for its own sake.\n"
     "2. Ask: 'what would an apology be for \u2014 you, or them?'\n"
     "3. Say the point is making a room easier to be in, not deciding who was right. They'll be in that lesson twice a week either way.\n"
     "4. Say plainly that this is not the soft option. Both people answer the same five questions, and both agree to something.\n"
     "5. Show the restorative conversation prompt card and read the five questions.\n"
     "6. Say they choose who it's with, and whether they want you there. They can also choose not to."),
    ("1. Explain what a restorative conversation is: a way of sorting out a fall-out so both people can get on afterwards.\n"
     "2. Say it's used between friends, at home and at work. Here it's with a member of staff.\n"
     "3. Say it isn't an apology for its own sake. Ask: 'what would an apology be for \u2014 you, or them?'\n"
     "4. Say the point is making a room easier to be in, not deciding who was right. They'll be in that lesson twice a week either way.\n"
     "5. Say plainly this is not the soft option: both people answer the same five questions, and both agree to something.\n"
     "6. Show the restorative conversation prompt card and read the five questions.\n"
     "7. Say they choose who it's with, and whether they want you there. They can also choose not to."),
]

TIMING_TARGET = {"input": 12, "activity": 18}
TIMING_KNOWN = [{"input": 10, "activity": 20}]


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
                 if i.get("name") == "Restorative conversation prompt card"), None)
    if item is None:
        print("pack 08: prompt card not found. Run apply_restorative_research.py "
              "first. Nothing written.")
        return 1

    changes = 0

    body = item.get("body")
    if body == BODY_TARGET:
        print("card body: already final, skipping")
    elif body not in BODY_KNOWN:
        print("card body: not a version this knows - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("pack 08 - card body")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (body, BODY_TARGET))
        item["body"] = BODY_TARGET
        changes += 1

    cards = item.get("cards") or []
    if cards == CARDS_TARGET:
        print("question cards: already final, skipping")
    elif len(cards) != 5:
        print("question cards: expected five - left alone")
    else:
        print("=" * 72)
        print("pack 08 - question cards")
        for a, b in zip(cards, CARDS_TARGET):
            print("   %-38s %s" % (b["title"], b["text"]))
            if a["text"] != b["text"]:
                print("      was: %s" % a["text"][:74])
        print()
        item["cards"] = [dict(c) for c in CARDS_TARGET]
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][3]
    text = week.get("input") or ""
    if text == INPUT_TARGET:
        print("week 4 input: already final, skipping")
    elif text not in INPUT_KNOWN:
        print("week 4 input: not a version this knows - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 08 week 4 - input")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, INPUT_TARGET))
        week["input"] = INPUT_TARGET
        changes += 1

    timing = week.get("timing") or {}
    if all(timing.get(k) == v for k, v in TIMING_TARGET.items()):
        print("timing: already final, skipping")
    elif any(all(timing.get(k) == v for k, v in known.items()) for known in TIMING_KNOWN):
        timing.update(TIMING_TARGET)
        print("timing: input -> 12, activity -> 18 (total unchanged at %d)"
              % sum(timing.values()))
        changes += 1
    else:
        print("timing: not a version this knows - left alone")

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
