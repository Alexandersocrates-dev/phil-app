#!/usr/bin/env python3
"""
Module 06: let the ladder's column headings do the explaining.

The body had grown into a four-sentence paragraph that told the pupil what went
in each column - which is what column headings are for. "What the situation is"
and "Worry 1-10" are labels rather than instructions, so the body had to repeat
them in prose above the table.

Headings now say what to write in them, so the body only has to say how many,
in what order, and how specific:

    Step | What you'd avoid | How worried, 1-10

"You start at step 1, not step 6" also comes off the sheet. That is an
instruction about what happens in week 3, not about filling this in, and week 3
already says it - the sheet only needs to cover writing it.

Runs whether or not apply_ladder_clarity.py has been applied: it accepts either
prior state and pads rows if they are still two cells wide.

    python3 apply_ladder_simpler.py --dry-run --packs data/resource_packs.json
    python3 apply_ladder_simpler.py --packs data/resource_packs.json

Standard library only. Touches resource_packs.json only, so no sync is needed.
"""

import argparse
import json
import os
import sys

BODY_TARGET = ("Six things you'd get out of if you could, one per row. Step 1 "
               "is the easiest, step 6 the hardest. Be specific: not 'lessons', "
               "but 'walking into maths late'.")

BODY_KNOWN = [
    "List situations from least to most anxiety-provoking, and rate each 1-10.",
    ("Six things you'd get out of if you could, in order: the one you'd find "
     "easiest at step 1, the hardest at step 6. Be specific - not 'lessons', "
     "but 'walking into maths late'. Then rate how worried each one makes you, "
     "1 to 10. You start at step 1, not step 6."),
]

HEADERS_TARGET = ["Step", "What you'd avoid", "How worried, 1-10"]

HEADERS_KNOWN = [
    ["Step", "Situation and worry rating (1-10)"],
    ["Step", "What the situation is", "Worry 1-10"],
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

    item = next((i for i in packs["06"]["items"]
                 if i.get("name") == "Avoidance ladder template"), None)
    if item is None:
        print("pack 06: ladder not found - nothing written.")
        return 1

    changes = 0

    body = item.get("body")
    if body == BODY_TARGET:
        print("body: already applied, skipping")
    elif body not in BODY_KNOWN:
        print("body: not a version this knows - left alone")
    else:
        print("=" * 72)
        print("pack 06 - Avoidance ladder template (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (body, BODY_TARGET))
        item["body"] = BODY_TARGET
        changes += 1

    table = item.get("table") or {}
    headers = table.get("headers")
    if headers == HEADERS_TARGET:
        print("headers: already applied, skipping")
    elif headers not in HEADERS_KNOWN:
        print("headers: not a version this knows - left alone")
    else:
        print("=" * 72)
        print("pack 06 - Avoidance ladder template (columns)")
        print("--- before --- %s" % headers)
        print("--- after  --- %s" % HEADERS_TARGET)
        table["headers"] = list(HEADERS_TARGET)
        for row in table.get("rows") or []:
            while len(row) < len(HEADERS_TARGET):
                row.append("")
        print("rows: %s\n" % [r[0] for r in table.get("rows") or []])
        changes += 1

    if args.dry_run:
        print("DRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("Nothing to do.")
        return 0

    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("%d change(s) written to %s" % (changes, args.packs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
