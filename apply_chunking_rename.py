#!/usr/bin/env python3
"""
Module 07: rename "Chunking checklist template" and show a worked example.

"Chunking" is teacher-training vocabulary. The sheet is filled in by a pupil, and
the word tells them nothing about what to do with it. The week's own input line
already says it in plain English - "one task, broken into parts you can finish" -
so the sheet can too.

It becomes "Breaking a task into steps". The old name is kept as an alias so the
week's wording, the app's matching and anything already written still resolve.

Renaming safely: the app derives a resource's storage key from its name unless
the item pins its own slug, so a rename would otherwise orphan every entry a
pupil had made. This pins slug to "chunking-checklist-template" - exactly what
the old name derived to - before changing the name, so nothing moves.

And an example. The sheet says "break a task into small steps" without showing
what a step looks like, and a pupil who could already break a task down wouldn't
need the sheet. The example is deliberately a piece of ordinary written work,
since the activity uses a real piece of their classwork rather than a made-up
task.

    python3 apply_chunking_rename.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_chunking_rename.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.
"""

import argparse
import json
import os
import sys

OLD_NAME = "Chunking checklist template"
NEW_NAME = "Breaking a task into steps"
PINNED_SLUG = "chunking-checklist-template"

BODY_OLD = "Break a task into small steps and tick each one off."
BODY_NEW = ("One task, broken into parts you can actually finish. Write a step "
            "on each line, then tick them off as you go.")

CARDS = [
    {
        "cat": "Example",
        "title": "Write a paragraph on the water cycle",
        "art": "art-pencil",
        "text": "1. Read the question twice. 2. Write down three things you "
                "already know. 3. Turn the first one into a sentence. 4. Add the "
                "other two. 5. Read it back and change one word.",
        "note": "Each step is one thing",
    },
]

ACTIVITY_OLD = (
    "1. Get out the chunking checklist template.\n"
    "2. Get out a real piece of their classwork, not a made-up task.\n"
    "3. Break it into parts together on the chunking checklist.\n"
    "4. Pupil works on the first chunk for five minutes while you time it.\n"
    "5. Ask: 'was that easier or harder than doing the whole thing?'"
)
ACTIVITY_NEW = (
    "1. Get out the breaking a task into steps sheet.\n"
    "2. Get out a real piece of their classwork, not a made-up task.\n"
    "3. Read the example on the sheet together, then break their work into steps on it.\n"
    "4. Pupil works on the first step for five minutes while you time it.\n"
    "5. Ask: 'was that easier or harder than doing the whole thing?'"
)


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

    item = next((i for i in packs["07"]["items"]
                 if i.get("name") in (OLD_NAME, NEW_NAME)), None)
    if item is None:
        print("pack 07: item not found - nothing written.")
        return 1

    changes = 0

    # Pin the slug FIRST. If the rename landed without it, every entry a pupil
    # had written on this sheet would key off the new name and be lost.
    if item.get("slug") == PINNED_SLUG:
        print("slug: already pinned to %s" % PINNED_SLUG)
    elif item.get("slug"):
        print("slug: already pinned to something else (%s) - nothing written."
              % item["slug"])
        return 1
    else:
        item["slug"] = PINNED_SLUG
        print("slug: pinned to '%s' so existing entries survive the rename"
              % PINNED_SLUG)
        changes += 1

    if item.get("name") == NEW_NAME:
        print("name: already applied, skipping")
    else:
        print("name: '%s' -> '%s'" % (OLD_NAME, NEW_NAME))
        item["name"] = NEW_NAME
        changes += 1

    aliases = item.setdefault("aliases", [])
    if OLD_NAME in aliases:
        print("aliases: already lists the old name")
    else:
        aliases.append(OLD_NAME)
        print("aliases: %s" % aliases)
        changes += 1

    if item.get("body") == BODY_NEW:
        print("body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("body:\n  before: %s\n  after:  %s" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    if item.get("cards") == CARDS:
        print("example: already applied, skipping")
    elif item.get("cards"):
        print("example: item already has cards - left alone")
    else:
        item["cards"] = CARDS
        print("example added: %s" % CARDS[0]["title"])
        changes += 1

    week = next(m for m in data if m.get("num") == 7)["weeks"][2]

    resources = week.setdefault("resources", [])
    if NEW_NAME in resources:
        print("week 3 resources: already updated")
    elif OLD_NAME in resources:
        resources[resources.index(OLD_NAME)] = NEW_NAME
        print("week 3 resources: now %s" % resources)
        changes += 1
    else:
        print("week 3 resources: does not list this item - left alone")

    act = week.get("activity") or ""
    if act == ACTIVITY_NEW:
        print("week 3 activity: already applied, skipping")
    elif act != ACTIVITY_OLD:
        print("week 3 activity: not the expected text - left alone")
    else:
        print("\nmodule 07 week 3 - activity\n--- before ---\n%s\n--- after ---\n%s"
              % (act, ACTIVITY_NEW))
        week["activity"] = ACTIVITY_NEW
        changes += 1

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
