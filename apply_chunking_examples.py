#!/usr/bin/env python3
"""
Module 07: examples a pupil recognises, on the breaking-a-task-into-steps sheet.

The single example was "Write a paragraph on the water cycle", broken into five
steps that ran together as one block of prose. Two problems with it.

It is the wrong kind of task. A pupil on this module has stopped starting things.
The water cycle is a topic they may never have been set, and the example has to
be something they can picture themselves in front of, or it teaches nothing.

And five steps in a paragraph is not a demonstration of breaking a task down. It
looks like the wall of work the sheet exists to break up.

Three examples now, each four steps, each with a first step small enough to be
almost silly - get the sheet out, write the title. That is the whole idea being
taught: the first step is not the work, it is the thing that makes the work
start. Three also shows the pattern holds across different kinds of task, which
one example cannot.

    python3 apply_chunking_examples.py --dry-run --packs data/resource_packs.json
    python3 apply_chunking_examples.py --packs data/resource_packs.json

Standard library only. Touches resource_packs.json only, so no sync is needed.
"""

import argparse
import json
import os
import sys

OLD_CARDS = [
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

NEW_CARDS = [
    {
        "cat": "Example",
        "title": "A page of maths questions",
        "art": "art-pencil",
        "text": "1. Get the sheet and a pen out. 2. Do question one. 3. Do the "
                "next two. 4. Finish the rest.",
        "note": "Starting is the hard bit, not the maths",
    },
    {
        "cat": "Example",
        "title": "Writing you don't know how to start",
        "art": "art-document",
        "text": "1. Write the title. 2. Write one sentence, even a bad one. "
                "3. Add two more. 4. Read it back and fix one thing.",
        "note": "A bad first sentence still counts",
    },
    {
        "cat": "Example",
        "title": "Work you've fallen behind on",
        "art": "art-behind",
        "text": "1. Find out exactly what's missing. 2. Pick the shortest one. "
                "3. Do that one today. 4. Ask about the rest tomorrow.",
        "note": "Shortest first, not most important",
    },
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--packs", default=os.path.join("data", "resource_packs.json"))
    args = ap.parse_args()

    if not os.path.exists(args.packs):
        print("cannot find %s" % args.packs)
        return 1

    with open(args.packs, "r", encoding="utf-8") as fh:
        packs = json.load(fh)

    item = next((i for i in packs["07"]["items"]
                 if i.get("slug") == "chunking-checklist-template"
                 or i.get("name") in ("Breaking a task into steps",
                                      "Chunking checklist template")), None)
    if item is None:
        print("pack 07: sheet not found. Run apply_chunking_rename.py first. "
              "Nothing written.")
        return 1

    if item.get("cards") == NEW_CARDS:
        print("already applied, nothing to do.")
        return 0
    if item.get("cards") != OLD_CARDS:
        print("the example cards are not what was expected - nothing written.")
        return 1

    print("=" * 72)
    print("pack 07 - %s" % item["name"])
    print("--- before ---")
    print("  %s" % OLD_CARDS[0]["title"])
    print("     %s" % OLD_CARDS[0]["text"])
    print("--- after ---")
    for c in NEW_CARDS:
        print("  %s" % c["title"])
        print("     %s" % c["text"])
        print("     (%s)" % c["note"])
    print()

    item["cards"] = NEW_CARDS

    if args.dry_run:
        print("DRY RUN - nothing written.")
        return 0

    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("1 change written to %s" % args.packs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
