#!/usr/bin/env python3
"""
Module 11: make the anger thermometer look like a scale, not a second card set.

The thermometer and the feeling word cards print as the same thing: dashed
cut-out cards, drawn with the same five level motifs. Side by side in a pack a
mentor cannot tell which is which, and week 1 asks the pupil to sort one onto
the other - hard when both look like a pile of cards.

Only one of them is meant to be cut up. The word cards are sorted by hand; the
thermometer is the surface they are sorted onto. It becomes a table, five rows
running cool to hot, which is what a thermometer is and is visually nothing like
a card set.

Every cell is filled, so none of it renders as a writable box. It is a reference
scale, not a worksheet.

    python3 apply_module11_thermometer.py --dry-run --packs data/resource_packs.json
    python3 apply_module11_thermometer.py --packs data/resource_packs.json

Standard library only. Touches resource_packs.json only, so no sync is needed.
"""

import argparse
import json
import os
import sys

BODY_OLD = "Most people use one word for all of this. Point at where you are."
BODY_NEW = ("Most people use one word for all of this. Five levels, coolest at "
            "the top. Point at where you are.")

TABLE_NEW = {
    "headers": ["Level", "Word for it", "What it feels like", "What to do"],
    "rows": [
        ["1-2", "Calm", "Totally settled", "Nothing needed"],
        ["3-4", "Annoyed", "Slightly irritated", "You can act on this one"],
        ["5-6", "Frustrated", "Building now", "The gap is still open"],
        ["7-8", "Angry", "Hard to think past it", "STOP goes here"],
        ["9-10", "Furious", "About to lose control", "Leave, then talk later"],
    ],
}


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

    item = next((i for i in packs["11"]["items"]
                 if i.get("name") == "Anger thermometer"), None)
    if item is None:
        print("pack 11: thermometer not found - nothing written.")
        return 1

    changes = 0

    if item.get("table") == TABLE_NEW:
        print("scale: already applied")
    else:
        if item.pop("cards", None) is not None:
            print("cut-out cards removed - only the word cards get cut up")
        item["table"] = json.loads(json.dumps(TABLE_NEW))
        print("scale: %s" % " | ".join(TABLE_NEW["headers"]))
        for r in TABLE_NEW["rows"]:
            print("   %-6s %-12s %-24s %s" % tuple(r))
        changes += 1

    if item.get("body") == BODY_NEW:
        print("body: already applied")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        item["body"] = BODY_NEW
        print("\nbody: %s" % BODY_NEW)
        changes += 1

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.packs, "w", encoding="utf-8") as fh:
        json.dump(packs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\n%d change(s) written to %s" % (changes, args.packs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
