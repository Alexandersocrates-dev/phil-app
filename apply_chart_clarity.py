#!/usr/bin/env python3
"""
Module 05: say what the self-monitoring chart actually tracks.

The chart read "Rate your self-control each lesson, 1 (hard) to 5 (great)."

Self-control at what. The module is about calling out and talking over
instructions - the tally card in week 1 says exactly that - but the chart, which
is the thing a pupil fills in alone in a lesson without the mentor there, only
says "self-control". A pupil rating that has to guess what is being asked, and
two pupils will guess differently.

And the scale had two axes. "1 (hard)" asks how difficult it was; "5 (great)"
asks how well it went. Those are different questions with different answers - a
lesson can be hard and go well. Week 5 sets this chart beside week one's tally
to look for change, and that comparison is worth nothing if the numbers do not
mean one consistent thing.

The second column header said "Rating (1-5) and note" without saying what the
note was for, so it mostly stayed empty.

Column count and row count are untouched, so nothing already written by a pupil
is orphaned - resource_entries keys cells by position.

    python3 apply_chart_clarity.py --dry-run --packs data/resource_packs.json
    python3 apply_chart_clarity.py --packs data/resource_packs.json

Standard library only. Touches resource_packs.json only, so no sync is needed.
"""

import argparse
import json
import os
import sys

BODY_OLD = "Rate your self-control each lesson, 1 (hard) to 5 (great)."
BODY_NEW = ("One row per lesson. How well did you hold back from calling out? "
            "1 means it got away from you, 5 means you held it every time. "
            "Fill it in as the lesson ends, not at home time.")

HEADER_OLD = "Rating (1-5) and note"
HEADER_NEW = "1-5, and what made it that number"


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

    item = next((i for i in packs["05"]["items"]
                 if i.get("name") == "Self-monitoring chart"), None)
    if item is None:
        print("pack 05: self-monitoring chart not found - nothing written.")
        return 1

    changes = 0

    if item.get("body") == BODY_NEW:
        print("body: already applied, skipping")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 05 - Self-monitoring chart (body)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    headers = (item.get("table") or {}).get("headers") or []
    if HEADER_NEW in headers:
        print("header: already applied, skipping")
    elif HEADER_OLD not in headers:
        print("header: not the expected text - left alone")
    else:
        print("=" * 72)
        print("pack 05 - Self-monitoring chart (column header)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (HEADER_OLD, HEADER_NEW))
        headers[headers.index(HEADER_OLD)] = HEADER_NEW
        changes += 1

    rows = (item.get("table") or {}).get("rows") or []
    print("columns: %d, rows: %d (unchanged - cell keys are positional)"
          % (len(headers), len(rows)))

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
