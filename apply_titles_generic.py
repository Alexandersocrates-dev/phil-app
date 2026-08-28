#!/usr/bin/env python3
"""
Module 04: describe the process, not the job title.

The joint-conversation guidance named "your pastoral lead or DSL" and said the
mentor never arranges one. Schools are not structured alike, and a mentor may be
the person who owns behaviour or restorative practice where they work — in which
case "never by the mentor" is simply wrong, and being told so undermines the
rest of the guidance.

What matters is not who does it but that it goes through the school's own route
rather than being settled inside a mentoring session. That holds everywhere,
including where the mentor turns out to be the person at the other end of it.

The substantive safeguards are untouched, because none of them depend on a job
title: no joint meeting where one pupil has power over the other, consent asked
privately and more than once, both pupils prepared separately, and rehearsal
alone being a complete session.

    python3 apply_titles_generic.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_titles_generic.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_restorative_fix.py.
"""

import argparse
import json
import os
import sys

COURSE_EDITS = [
    {
        "field": "activity",
        # "Don't arrange one yourself" had the same fault as the job titles: it
        # assumes the mentor lacks the standing to. The safeguard that actually
        # matters is that it isn't settled inside the session, and that the
        # other pupil is not approached by their pupil's mentor.
        "old": "4. Don't arrange a joint conversation yourself, and don't ask "
               "the other pupil anything.\n"
               "5. If your pupil wants one, ask what they'd want out of it, then "
               "take it to your pastoral lead or DSL — read the joint "
               "conversation briefing note first.",
        "new": "4. Don't set a joint conversation up from inside this session, "
               "and don't approach the other pupil about it.\n"
               "5. If your pupil wants one, ask what they'd want out of it, then "
               "take it through your school's own route for this — read the "
               "joint conversation briefing note first.",
    },
    {
        "field": "lookfor",
        "old": "Rehearsal is the whole session — it is not a lesser version of "
               "it. Any joint conversation is arranged by the pastoral lead or "
               "DSL, never by the mentor, and never where there has been "
               "repeated targeting or an imbalance between the two pupils.",
        "new": "Rehearsal is the whole session — it is not a lesser version of "
               "it. Any joint conversation goes through the school's own route "
               "for this rather than being settled in a mentoring session, and "
               "never happens where there has been repeated targeting or an "
               "imbalance between the two pupils.",
    },
]

CARD_EDITS = [
    {
        "title": "Not you",
        "new_cat": "Who decides",
        "new_title": "Your school's route",
        "new_text": "It goes through however your school handles this, which "
                    "may or may not be you. Find out before you offer it to a "
                    "pupil.",
        "new_note": "Check the route first",
    },
    {
        "title": "Where one has power over the other",
        "new_note": "Raise it with whoever leads on safeguarding",
    },
]

BODY_OLD = ("For you, not the pupil. A joint conversation is the school's "
            "process, not part of the mentoring session. Read this before you "
            "say anything to the pupil about one.")
BODY_NEW = ("For you, not the pupil. A joint conversation runs through the "
            "school's own route, not inside a mentoring session. Read this "
            "before you say anything to the pupil about one.")


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

    week = next(m for m in data if m.get("num") == 4)["weeks"][3]
    changes = 0

    for edit in COURSE_EDITS:
        text = week.get(edit["field"]) or ""
        if edit["new"] in text:
            print("week 4 %s: already applied, skipping" % edit["field"])
            continue
        if text.count(edit["old"]) != 1:
            print("week 4 %s: expected text not found exactly once. Run "
                  "apply_restorative_fix.py first. Nothing written." % edit["field"])
            return 1
        updated = text.replace(edit["old"], edit["new"])
        print("=" * 72)
        print("module 04 week 4 — %s" % edit["field"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, updated))
        week[edit["field"]] = updated
        changes += 1

    item = next((i for i in packs["04"]["items"]
                 if i.get("name") == "Joint conversation briefing note"), None)
    if item is None:
        print("pack 04: briefing note not found. Run apply_restorative_fix.py "
              "first. Nothing written.")
        return 1

    if item.get("body") == BODY_NEW:
        print("pack 04 body: already applied, skipping")
    elif item.get("body") == BODY_OLD:
        print("=" * 72)
        print("pack 04 — briefing note body")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1
    else:
        print("pack 04 body: not the expected text — left alone")

    for edit in CARD_EDITS:
        card = next((c for c in item["cards"] if c.get("title") == edit["title"]), None)
        if card is None:
            if any(c.get("title") == edit.get("new_title") for c in item["cards"]):
                print("pack 04 card '%s': already applied, skipping" % edit["title"])
                continue
            print("pack 04 card '%s': not found — left alone" % edit["title"])
            continue
        print("=" * 72)
        print("pack 04 — card '%s'" % edit["title"])
        for key, field in (("new_cat", "cat"), ("new_title", "title"),
                           ("new_text", "text"), ("new_note", "note")):
            if key in edit:
                print("  %-6s before: %s" % (field, card.get(field)))
                print("  %-6s after:  %s" % (field, edit[key]))
                card[field] = edit[key]
        print()
        changes += 1

    if args.dry_run:
        print("DRY RUN — %d change(s) would be made, nothing written." % changes)
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
