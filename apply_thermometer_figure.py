"""Switch module 11's anger thermometer from a five-row table to a drawn figure.

Dry run by default, as with the other apply/delete scripts in the repo root.
Nothing is written until --confirm.

The item's NAME is never touched: `resource_entries` keys pupil-written content
off the pack's canonical name, so a rename there orphans entries. Only the
`table` block is removed and `figure: "thermometer"` added, which is what both
renderers key off.

    python3 apply_thermometer_figure.py                 # show the change
    python3 apply_thermometer_figure.py --confirm       # write it

Run from the repo root. Resource packs are read from the file at runtime, so no
database sync is needed afterwards - only a push.
"""

import argparse
import json
import os
import re
import sys

import thermometer

PACKS = os.path.join("data", "resource_packs.json")
MODULE = "11"


def find_indent(text):
    """Keep the file's own indentation so the diff is the item, not the file."""
    m = re.search(r"\n(\s+)\"", text)
    return len(m.group(1)) if m else 2


def looks_like_the_level_table(table):
    """Five rows whose first column is the five level names, in order."""
    rows = table.get("rows") or []
    if len(rows) != len(thermometer.LEVELS):
        return False
    names = [str(r[0]).strip().lower() for r in rows if r]
    return names == [name.lower() for name, _, _, _ in thermometer.LEVELS]


def describe_drift(table):
    """What the table says that the figure would not, cell by cell.

    The figure draws thermometer.LEVELS. If the pack's wording has moved on from
    that, converting would quietly delete the newer wording, so say so and stop.
    """
    drift = []
    for row, (name, span, feels, do) in zip(table.get("rows") or [], thermometer.LEVELS):
        cells = [str(c).strip() for c in row]
        for got, want, label in zip(cells, [name, span, feels, do],
                                    ["level", "range", "feels like", "what to do"]):
            if got != want:
                drift.append("  %-11s %s: file has %r, figure draws %r"
                             % (name, label, got, want))
    return drift


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true", help="write the change")
    ap.add_argument("--name", help="pack item name, if it is not found automatically")
    ap.add_argument("--force", action="store_true",
                    help="convert even if the table's wording differs from thermometer.LEVELS")
    args = ap.parse_args()

    if not os.path.exists(PACKS):
        sys.exit("%s not found - run this from the repo root." % PACKS)

    raw = open(PACKS, encoding="utf-8").read()
    packs = json.loads(raw)
    pack = packs.get(MODULE)
    if pack is None:
        sys.exit("module %s is not in %s" % (MODULE, PACKS))

    items = pack.get("items") if isinstance(pack, dict) else pack
    if not isinstance(items, list):
        sys.exit("could not find module %s's item list - check the pack's shape" % MODULE)

    matches = []
    for item in items:
        if args.name:
            if item.get("name", "") == args.name:
                matches.append(item)
        elif thermometer.is_thermometer(item):
            matches.append(item)          # so a second run says "already done"
        elif item.get("table") and looks_like_the_level_table(item["table"]):
            matches.append(item)

    if not matches:
        sys.exit("no matching item in module %s. Items present:\n  %s"
                 % (MODULE, "\n  ".join(i.get("name", "?") for i in items)))
    if len(matches) > 1:
        sys.exit("%d items matched - pass --name to pick one:\n  %s"
                 % (len(matches), "\n  ".join(i.get("name", "?") for i in matches)))

    item = matches[0]
    name = item.get("name", "")
    print("module %s item: %s" % (MODULE, name))

    if thermometer.is_thermometer(item) and not item.get("table"):
        print("already a figure - nothing to do.")
        return

    table = item.get("table")
    if not table:
        sys.exit("that item has no table to replace.")

    drift = describe_drift(table)
    if drift:
        print("\nThe table's wording differs from thermometer.LEVELS:")
        print("\n".join(drift))
        if not args.force:
            sys.exit("\nConverting would drop that wording. Update thermometer.LEVELS to "
                     "match, or re-run with --force if the figure's wording is the one "
                     "you want.")
        print("\n--force given: the figure's wording wins.")

    print("\n  remove: table, %d rows x %d columns"
          % (len(table.get("rows") or []), len(table.get("headers") or [])))
    print("  add:    figure: \"thermometer\"")
    print("  keep:   name, body%s"
          % ("".join(", " + k for k in ("cards", "steps", "form", "checklist", "note")
                     if item.get(k)) or ""))

    if not args.confirm:
        print("\nDry run. Re-run with --confirm to write.")
        print("Before confirming, check nothing is stored against that table on Railway:")
        print("  sqlite3 /data/phil.db \"select count(*) from resource_entries "
              "where resource_name = '%s';\"" % name.replace("'", "''"))
        print("A count above 0 means a pupil has written into the table's cells, and "
              "removing it would orphan those rows.")
        return

    item.pop("table", None)
    item["figure"] = "thermometer"

    indent = find_indent(raw)
    text = json.dumps(packs, indent=indent, ensure_ascii=False)
    if raw.endswith("\n"):
        text += "\n"
    with open(PACKS, "w", encoding="utf-8") as fh:
        fh.write(text)

    json.loads(open(PACKS, encoding="utf-8").read())   # it still parses
    print("\nWritten. %s now renders as a drawn thermometer on screen and in the pack." % name)
    print("Resource packs are read from the file, so there is no sync to run - push and it is live.")


if __name__ == "__main__":
    main()
