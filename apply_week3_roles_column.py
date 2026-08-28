#!/usr/bin/env python3
"""
Module 04 week 3: write into the handout's second column.

The week's objective is that a pupil can identify which roles were played "and
what each role needs". The handout has a column for exactly that, left blank for
the pupil. Nothing ever filled it: the activity asked what the role needs out
loud, then moved on, and step 4 raised the other roles without recording any of
them. So the sheet came out of the session with one mark on it and three empty
rows, and none of the "what it needs" half of the objective was written down.

Two changes.

The activity now says to write the answers in. Step 3 puts what the role needs
into the next column, and step 4 fills a row for each other role the pupil names
— which is what makes the four-row table worth being four rows.

The column header asked two questions at once: "What this looks like / what this
role needs". The activity only ever asks the second, and a pupil writing in a
narrow cell shouldn't have to work out which half to answer. It now asks one.

Safe to change: table cells are keyed by position (t<row>_<col>) in
resource_entries, not by header text, so nothing already written is orphaned.
The rows are left exactly as they are, since changing those WOULD orphan.

    python3 apply_week3_roles_column.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_week3_roles_column.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only. Run after apply_week3_roles.py.
"""

import argparse
import json
import os
import sys

ACTIVITY_OLD = (
    "1. Ask: 'thinking about something that's happened this term, which of these four roles were you?'\n"
    "2. Pupil marks that role on the handout.\n"
    "3. Ask: 'what would someone in that role need — to feel safe, to get help, or a way to stop?'\n"
    "4. Ask: 'have you ever been one of the other roles too?' Most people have."
)

ACTIVITY_NEW = (
    "1. Ask: 'thinking about something that's happened this term, which of these four roles were you?'\n"
    "2. Pupil marks that role on the handout.\n"
    "3. Ask: 'what would someone in that role need — to feel safe, to get help, or a way to stop?' "
    "Pupil writes that in the next column.\n"
    "4. Ask: 'have you ever been one of the other roles too?' Most people have. "
    "Fill in a row for each one they name."
)

HEADER_OLD = "What this looks like / what this role needs"
HEADER_NEW = "What this role needs"


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

    changes = 0

    week = next(m for m in data if m.get("num") == 4)["weeks"][2]
    text = week.get("activity") or ""
    if text == ACTIVITY_NEW:
        print("week 3 activity: already applied, skipping")
    elif text != ACTIVITY_OLD:
        print("week 3 activity: not the expected text — nothing written.")
        return 1
    else:
        print("=" * 72)
        print("module 04 week 3 — activity")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, ACTIVITY_NEW))
        week["activity"] = ACTIVITY_NEW
        changes += 1

    item = next((i for i in packs["04"]["items"]
                 if i.get("name") == "Roles-in-bullying handout"), None)
    if item is None:
        print("pack 04: handout not found — nothing written.")
        return 1
    headers = (item.get("table") or {}).get("headers") or []
    if HEADER_NEW in headers:
        print("pack 04 handout header: already applied, skipping")
    elif HEADER_OLD not in headers:
        print("pack 04 handout header: not the expected text — left alone")
    else:
        print("=" * 72)
        print("pack 04 — Roles-in-bullying handout (column header)")
        print("--- before ---\n%s\n--- after ---\n%s\n" % (HEADER_OLD, HEADER_NEW))
        headers[headers.index(HEADER_OLD)] = HEADER_NEW
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
