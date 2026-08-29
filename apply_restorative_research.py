#!/usr/bin/env python3
"""
Module 08 week 4: bring the restorative prompt card in line with the practice.

The card carries four questions. The standard restorative script - the one used
in UK schools and set out by the Restorative Justice Council - has five, and the
one missing is the one that does the work: "what have you thought about since?"
It is the question that separates a restorative conversation from an account of
an incident, because it is where a pupil says the thing they have been carrying
around, unprompted, before anyone asks them to put it right.

Question 4 also softened the script. "What would help this relationship going
forward?" invites a wish; "what needs to happen to put this right?" asks for an
undertaking. The RJC's position is that restorative practice is not the soft
alternative to a sanction - it emphasises responsibility over conformity - and
the wording should not undercut that.

Three mentor-facing steps are added for the part the card never covered: what
has to be true before the conversation, and what happens after it. Both parties
willing, separately prepared, and someone checking a week later whether it held.
An unprepared conversation is the common failure mode, and the card previously
sent a mentor straight in.

A source line is added, following the pattern used on other cards in the packs:

  - DfE, Behaviour in Schools (February 2024) - the statutory-adjacent advice
    schools work to.
  - EEF, Improving Behaviour in Schools (2019), recommendation 5: universal
    systems will not meet every pupil's needs, and pupils needing more intensive
    support do better with a personalised approach. That is the ground a 1:1
    restorative conversation stands on.
  - Restorative Justice Council on what restorative practice is and is not.

Deliberately NOT claimed: that whole-school restorative practice has a strong
evidence base. It does not. EEF's recommendation covers targeted work with
individuals, which is what this session does; whole-school restorative
programmes are contested, and the DfE's own behaviour adviser has publicly
called them ineffective at that scale. The card should not imply more than the
evidence carries.

    python3 apply_restorative_research.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_restorative_research.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.
"""

import argparse
import json
import os
import sys

BODY_OLD = "For repairing one working relationship the pupil still needs."
BODY_NEW = ("For repairing one working relationship the pupil still needs. "
            "Both people answer the same questions, in the same order, and "
            "neither is asked to apologise on cue.")

CARDS_OLD = [
    {"cat": "Question 1", "title": "What happened?", "art": "art-question",
     "text": "Both sides get asked this.", "note": ""},
    {"cat": "Question 2", "title": "What were you thinking at the time?",
     "art": "art-body-signals", "text": "Not an excuse \u2014 context.", "note": ""},
    {"cat": "Question 3", "title": "Who has been affected, and how?",
     "art": "art-apart", "text": "Including the wider class.", "note": ""},
    {"cat": "Question 4", "title": "What would help this relationship going forward?",
     "art": "art-hand-heart", "text": "Something specific and small.", "note": ""},
]

CARDS_NEW = [
    {"cat": "Question 1", "title": "What happened?", "art": "art-question",
     "text": "Both people answer this, not just the pupil. Facts before feelings.",
     "note": "No interrupting the other's account"},
    {"cat": "Question 2", "title": "What were you thinking at the time?",
     "art": "art-body-signals",
     "text": "Context, not an excuse. What someone was thinking explains a "
             "reaction without approving of it.",
     "note": "Don't argue with the answer"},
    {"cat": "Question 3", "title": "What have you thought about since?",
     "art": "art-thoughts",
     "text": "The question most often skipped, and the one that changes the "
             "conversation. Leave a long silence after it.",
     "note": "Wait. Don't fill the gap"},
    {"cat": "Question 4", "title": "Who has been affected, and how?",
     "art": "art-apart",
     "text": "Widen it past the two of them: the rest of the class, other staff, "
             "people at home.",
     "note": "Name people, not 'everyone'"},
    {"cat": "Question 5", "title": "What needs to happen to put this right?",
     "art": "art-repair",
     "text": "Both people answer, and both agree to something. One specific, "
             "small thing each is better than a long list.",
     "note": "An undertaking, not a wish"},
]

STEPS_NEW = [
    {"title": "Before: check it's wanted",
     "art": "art-fork",
     "text": "Both people have to be willing, and either can say no without it "
             "counting against them. A conversation someone was made to attend "
             "is not a restorative one."},
    {"title": "Before: prepare separately",
     "art": "art-person-pin",
     "text": "Each person hears the five questions and thinks about their answers "
             "beforehand. Walking in cold is the most common reason these go wrong."},
    {"title": "After: check it held",
     "art": "art-calendar",
     "text": "Agree a day to check back, and do it. Whatever was agreed is either "
             "happening a week later or it isn't, and only asking finds out."},
]

SOURCE = ("The five restorative questions as set out by the Restorative Justice "
          "Council. Sits within EEF, Improving Behaviour in Schools (2019), "
          "recommendation 5, on tailoring targeted approaches to individual "
          "pupils, and DfE, Behaviour in Schools (February 2024).")

INPUT_OLD = (
    "1. Explain that a restorative conversation isn't an apology for its own sake.\n"
    "2. Ask: 'what would an apology be for \u2014 you, or them?' Its purpose is repairing one working relationship they still need.\n"
    "3. Show the restorative conversation prompt card and read the four questions.\n"
    "4. Say they'll choose which relationship is worth repairing, and whether they want you there."
)
INPUT_NEW = (
    "1. Explain that a restorative conversation isn't an apology for its own sake.\n"
    "2. Ask: 'what would an apology be for \u2014 you, or them?' Its purpose is repairing one working relationship they still need.\n"
    "3. Say plainly that this is not the soft option. Both people answer the same five questions, and both have to agree to something.\n"
    "4. Show the restorative conversation prompt card and read the five questions.\n"
    "5. Say they choose which relationship is worth repairing, and whether they want you there. They can also choose not to."
)

LOOK_OLD = ("Only proceed with a real conversation if the staff member is willing "
            "and the pupil is ready, rehearsal alone is a valid outcome for this session.")
LOOK_NEW = ("Rehearsal alone is a full outcome for this session. Only hold a real "
            "conversation if both the staff member and the pupil are willing, and "
            "both have seen the questions first. A pupil who feels made to do it "
            "will perform an apology, which is worse than not having the "
            "conversation at all.")


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
        print("pack 08: prompt card not found - nothing written.")
        return 1

    changes = 0

    if item.get("cards") == CARDS_NEW:
        print("questions: already applied, skipping")
    elif item.get("cards") != CARDS_OLD:
        print("questions: not the expected four - nothing written.")
        return 1
    else:
        print("=" * 72)
        print("pack 08 - the questions")
        for c in CARDS_OLD:
            print("   before: %s" % c["title"])
        for c in CARDS_NEW:
            print("   after:  %s" % c["title"])
        print()
        item["cards"] = [dict(c) for c in CARDS_NEW]
        changes += 1

    if item.get("steps") == STEPS_NEW:
        print("before/after steps: already applied, skipping")
    elif item.get("steps"):
        print("before/after steps: item already has steps - left alone")
    else:
        item["steps"] = [dict(s) for s in STEPS_NEW]
        print("added %d mentor-facing steps: %s"
              % (len(STEPS_NEW), ", ".join(s["title"] for s in STEPS_NEW)))
        changes += 1

    if item.get("body") != BODY_NEW:
        if item.get("body") == BODY_OLD:
            item["body"] = BODY_NEW
            print("body updated")
            changes += 1
        else:
            print("body: not the expected text - left alone")
    else:
        print("body: already applied, skipping")

    if item.get("source") == SOURCE:
        print("source: already applied, skipping")
    elif item.get("source"):
        print("source: already set to something else - left alone")
    else:
        item["source"] = SOURCE
        print("source line added")
        changes += 1

    week = next(m for m in data if m.get("num") == 8)["weeks"][3]
    for field, old, new in (("input", INPUT_OLD, INPUT_NEW),
                            ("lookfor", LOOK_OLD, LOOK_NEW)):
        text = week.get(field) or ""
        if text == new:
            print("week 4 %s: already applied, skipping" % field)
            continue
        if text != old:
            print("week 4 %s: not the expected text - left alone" % field)
            continue
        print("=" * 72)
        print("module 08 week 4 - %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, new))
        week[field] = new
        changes += 1

    if args.dry_run:
        print("DRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("Nothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("%d change(s) written." % changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
