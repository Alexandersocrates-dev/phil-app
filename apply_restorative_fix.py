#!/usr/bin/env python3
"""
Module 04: makes the joint conversation the school's process, not the mentor's.

Three problems this addresses.

The restorative question prompt card is subtitled "Asked of everyone involved,
not just one pupil". There is no everyone — the session is 1:1. The card reads
as a conference script when what week 1 actually does is take one pupil's own
account.

Week 4's activity ends "If both pupils agree, arrange a joint conversation with
a second mentor present." That is one line, formatted like the rehearsal steps
above it, in a module covering bullying. It tells a mentor to convene a meeting
between a target and an instigator, implies they have already asked the other
pupil, and gives no criteria for when that would be wrong. The caution that
exists sits in `lookfor`, which is the adaptation note, not the instruction.

The module also had no mentor-facing guidance on any of this, so a new pack item
carries it.

    python3 apply_restorative_fix.py --dry-run
    python3 apply_restorative_fix.py

Standard library only. Writes courses_data.js and data/resource_packs.json.
"""

import argparse
import json
import os
import sys

COURSES = "courses_data.js"
PACKS = os.path.join("data", "resource_packs.json")

# Mentor-facing. Follows the existing "briefing note" pattern in packs 18 and 19
# — body, cards, tone — so it renders the same way as the rest.
NEW_ITEM = {
    "name": "Joint conversation briefing note",
    "body": "For you, not the pupil. A joint conversation is the school's "
            "process, not part of the mentoring session. Read this before you "
            "say anything to the pupil about one.",
    "tone": "teal",
    "cards": [
        {
            "cat": "Who runs it",
            "title": "Not you",
            "art": "art-person-pin",
            "text": "Your pastoral lead or DSL arranges and chairs it. You "
                    "prepare your pupil, and you may sit with them.",
            "note": "Ask, don't arrange",
        },
        {
            "cat": "When not to",
            "title": "Where one has power over the other",
            "art": "art-shield",
            "text": "Repeated targeting, or an imbalance between them, makes a "
                    "joint meeting a place where the harm can happen again.",
            "note": "Take it to the DSL instead",
        },
        {
            "cat": "Consent",
            "title": "A yes under pressure is not a yes",
            "art": "art-stop",
            "text": "Ask privately, more than once, on different days. Saying "
                    "no has to cost them nothing.",
            "note": "Never pass on a request from the other pupil",
        },
        {
            "cat": "If it goes ahead",
            "title": "Both prepared separately",
            "art": "art-repair",
            "text": "Each pupil is prepared by a different adult before anyone "
                    "sits down together.",
            "note": "Rehearsal on its own is a complete session",
        },
    ],
}

PACK_EDITS = [
    {
        "pack": "04",
        "item": "Restorative question prompt card",
        "field": "body",
        "old": "Asked of everyone involved, not just one pupil. One at a time.",
        "new": "The four questions a restorative conversation uses, asked here "
               "of one pupil about their own part. One at a time. You're "
               "collecting their account, not testing it.",
    },
]

COURSE_EDITS = [
    {
        "module": 4,
        "week": 4,
        "field": "objective",
        "old": "Pupil can use an 'I statement' and take part in a structured repair conversation.",
        "new": "Pupil can build an 'I statement' about a real fall-out and "
               "rehearse it until they would say it.",
        "why": "the old objective promised a repair conversation the session doesn't run",
    },
    {
        "module": 4,
        "week": 4,
        "field": "activity",
        "old": "4. If both pupils agree, arrange a joint conversation with a second mentor present.",
        "new": "4. Don't arrange a joint conversation yourself, and don't ask "
               "the other pupil anything.\n"
               "5. If your pupil wants one, ask what they'd want out of it, "
               "then take it to your pastoral lead or DSL — read the joint "
               "conversation briefing note first.",
        "why": "told the mentor to convene a meeting between the two pupils themselves",
    },
    {
        "module": 4,
        "week": 4,
        "field": "lookfor",
        "old": "A joint conversation should only happen if genuinely appropriate "
               "and consensual, this session can be adapted to rehearsal only.",
        "new": "Rehearsal is the whole session — it is not a lesser version of "
               "it. Any joint conversation is arranged by the pastoral lead or "
               "DSL, never by the mentor, and never where there has been "
               "repeated targeting or an imbalance between the two pupils.",
        "why": "the existing caution didn't say who decides or what would rule it out",
    },
]

ADD_RESOURCE = {"module": 4, "week": 4, "name": "Joint conversation briefing note"}


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
    ap.add_argument("--packs", default=PACKS)
    args = ap.parse_args()

    for path in (args.courses, args.packs):
        if not os.path.exists(path):
            print("cannot find %s — run this from the clone root" % path)
            return 1

    prefix, data = load_courses(args.courses)
    with open(args.packs, "r", encoding="utf-8") as fh:
        packs = json.load(fh)

    changes = 0

    # 1. The new mentor-facing item.
    items = packs["04"]["items"]
    if any(i.get("name") == NEW_ITEM["name"] for i in items):
        print("pack 04: '%s' already present, skipping" % NEW_ITEM["name"])
    else:
        # Sits after the I statement card, which is the week it belongs to.
        at = next((n for n, i in enumerate(items)
                   if i.get("name") == "I statement card"), len(items) - 1)
        items.insert(at + 1, NEW_ITEM)
        print("pack 04: added '%s' after 'I statement card'" % NEW_ITEM["name"])
        changes += 1

    # 2. The restorative card's framing.
    for edit in PACK_EDITS:
        item = next((i for i in packs[edit["pack"]]["items"]
                     if i.get("name") == edit["item"]), None)
        if item is None:
            print("pack %s: item '%s' not found — stopping, nothing written"
                  % (edit["pack"], edit["item"]))
            return 1
        if item.get(edit["field"]) == edit["new"]:
            print("pack %s '%s': already applied, skipping" % (edit["pack"], edit["item"]))
            continue
        if item.get(edit["field"]) != edit["old"]:
            print("pack %s '%s': %s is not what was expected — stopping, nothing written"
                  % (edit["pack"], edit["item"], edit["field"]))
            return 1
        print("=" * 72)
        print("pack %s — %s (%s)" % (edit["pack"], edit["item"], edit["field"]))
        print("--- before ---\n%s\n--- after ---\n%s\n" % (edit["old"], edit["new"]))
        item[edit["field"]] = edit["new"]
        changes += 1

    # 3. Week 4.
    for edit in COURSE_EDITS:
        module = next((m for m in data if m.get("num") == edit["module"]), None)
        week = (module.get("weeks") or [])[edit["week"] - 1]
        text = week.get(edit["field"]) or ""
        if edit["new"] in text:
            print("module %02d week %d %s: already applied, skipping"
                  % (edit["module"], edit["week"], edit["field"]))
            continue
        if text.count(edit["old"]) != 1:
            print("module %02d week %d %s: expected text not found exactly once "
                  "— stopping, nothing written"
                  % (edit["module"], edit["week"], edit["field"]))
            return 1
        updated = renumber(text.replace(edit["old"], edit["new"]))
        print("=" * 72)
        print("module %02d week %d — %s" % (edit["module"], edit["week"], edit["field"]))
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
        week[edit["field"]] = updated
        changes += 1

    # 4. The week's resource list, so the note prints in the pack.
    module = next(m for m in data if m.get("num") == ADD_RESOURCE["module"])
    week = module["weeks"][ADD_RESOURCE["week"] - 1]
    if ADD_RESOURCE["name"] in week.get("resources", []):
        print("module 04 week 4 resources: already lists the briefing note")
    else:
        week.setdefault("resources", []).append(ADD_RESOURCE["name"])
        print("module 04 week 4 resources: now %s" % week["resources"])
        changes += 1

    if args.dry_run:
        print("\nDRY RUN — %d change(s) would be made, nothing written." % changes)
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
