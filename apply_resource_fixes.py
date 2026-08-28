#!/usr/bin/env python3
"""
Names three pack cards in the step that already teaches their content.

Each of these three cards prints in the resource pack, and the week covers what
is on it out of the mentor's own mouth, but no step ever tells the mentor to
produce it. A mentor following the instructions literally never hands the card
over, so it is printed and wasted.

Nothing is reworded beyond naming the card. The teaching points, the order and
the wording all stay as they are.

    python3 apply_resource_fixes.py --dry-run      # show the diff, write nothing
    python3 apply_resource_fixes.py                # apply

Standard library only. Reads and writes courses_data.js in place, preserving the
`module.exports = ` wrapper and the file's two-space indentation.
"""

import argparse
import json
import sys

EDITS = [
    {
        "module": 13,
        "week": 2,
        "field": "input",
        "why": "the ranking card's three kinds are exactly what steps 1-2 explain",
        "old": (
            "1. Explain that triggers are often social as much as physical: being offered one, fitting in.\n"
            "2. Ask: 'when in the day would you most want one?' Boredom, stress, or simply habit at a particular time.\n"
            "3. Say why naming them matters — you can plan for a named trigger, not a vague urge.\n"
            "4. Explain the ranking you'll use: hardest means hardest to say no to, not most frequent."
        ),
        "new": (
            "1. Explain that triggers are often social as much as physical: being offered one, fitting in.\n"
            "2. Ask: 'when in the day would you most want one?' Boredom, stress, or simply habit at a particular time.\n"
            "3. Get out the trigger difficulty ranking card and read the three kinds together: social, emotional, habit.\n"
            "4. Say why naming them matters — you can plan for a named trigger, not a vague urge.\n"
            "5. Explain the ranking you'll use: hardest means hardest to say no to, not most frequent."
        ),
    },
    {
        "module": 17,
        "week": 2,
        "field": "input",
        "why": "step 3 recites the card's contents aloud instead of showing it",
        "old": (
            "3. Name the usual ones: corridors between lessons, assembly, the lunch hall, PE changing rooms."
        ),
        "new": (
            "3. Get out the difficult environments card and go through them together: corridors, "
            "assembly, the lunch hall, changing rooms."
        ),
    },
    {
        "module": 20,
        "week": 3,
        "field": "input",
        "why": "step 3 names the club route without producing the card that explains why it works",
        "old": (
            "3. Add the low-pressure routes in: sitting near others at lunch, joining a club in the first fortnight."
        ),
        "new": (
            "3. Add the low-pressure routes in: sitting near others at lunch, joining a club in the first fortnight.\n"
            "4. Get out the joining a club or group ideas card — a shared activity gives you a reason "
            "to talk, which is easier than talking for its own sake."
        ),
    },
]


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    prefix, body = src.split("=", 1)
    body = body.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return prefix + "= ", json.loads(body)


def renumber(text):
    """Rewrites 'n. ' prefixes so a field stays 1..n after an insertion."""
    out, n = [], 0
    for line in text.split("\n"):
        stripped = line.lstrip()
        head = stripped.split(". ", 1)
        if len(head) == 2 and head[0].isdigit():
            n += 1
            out.append("%d. %s" % (n, head[1]))
        else:
            out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="courses_data.js")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prefix, data = load(args.path)

    applied = 0
    for edit in EDITS:
        module = next((m for m in data if m.get("num") == edit["module"]), None)
        if module is None:
            print("module %02d not found — stopping, nothing written" % edit["module"])
            return 1
        week = (module.get("weeks") or [])[edit["week"] - 1]
        text = week.get(edit["field"]) or ""

        if edit["new"] in text:
            print("module %02d week %d %s: already applied, skipping"
                  % (edit["module"], edit["week"], edit["field"]))
            continue
        if text.count(edit["old"]) != 1:
            print("module %02d week %d %s: expected text not found exactly once "
                  "(found %d) — stopping, nothing written"
                  % (edit["module"], edit["week"], edit["field"], text.count(edit["old"])))
            return 1

        updated = renumber(text.replace(edit["old"], edit["new"]))
        print("=" * 72)
        print("module %02d week %d — %s" % (edit["module"], edit["week"], module["title"]))
        print("why: %s" % edit["why"])
        print("--- before ---")
        print(text)
        print("--- after ---")
        print(updated)
        print()
        week[edit["field"]] = updated
        applied += 1

    if args.dry_run:
        print("DRY RUN — %d edit(s) would be applied, nothing written." % applied)
        return 0

    if not applied:
        print("Nothing to do.")
        return 0

    with open(args.path, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("%d edit(s) written to %s" % (applied, args.path))
    print("Now run: python3 check_course_text.py %s --packs data/resource_packs.json" % args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
