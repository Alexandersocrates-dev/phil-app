#!/usr/bin/env python3
"""
Module 10: record which outlet the pupil chose, and show it again when it's asked about.

Week 4 opens "did you use one of the other outlets, and where?" and week 4 does
not list the safe outlet ideas card, so nothing appears on the page. Week 5 then
asks "what's your safe outlet, and where is it kept?" - also with nothing to
look at.

Underneath that is a bigger gap. The card is four illustrated cards and no
writing space. Week 3's activity agrees which outlet the pupil will use, where
it is kept and who needs to know, and the watch-for note says to settle that
with the class teacher before the session ends. None of it is written down
anywhere except the mentor's notes, so by week 4 the only record of the
agreement is whether somebody remembered it.

Three lines on the card fix that, and listing it in weeks 4 and 5 means the
pupil's own answers come back with it - attach_earlier_entries carries forward
what was written on a resource in an earlier week.

    python3 apply_module10_outlets.py --dry-run --courses data/courses_data.js --packs data/resource_packs.json
    python3 apply_module10_outlets.py --courses data/courses_data.js --packs data/resource_packs.json

Standard library only.
"""

import argparse
import json
import os
import sys

NAME = "Safe outlet ideas"
FIELDS = ["The outlet I am going to use",
          "Where it is kept",
          "Who knows it is there"]

BODY_OLD = ("Agree with the class teacher where each is kept. An outlet you "
            "can't reach is no use.")
BODY_NEW = ("Try them, then write down the one you will actually use. An outlet "
            "you cannot reach is no use, so agree where it is kept with the "
            "class teacher.")

ACT_OLD = "4. Agree where it would be kept, and who needs to know it is there."
ACT_NEW = ("4. Agree where it would be kept and who needs to know, and write all "
           "three on the card.")


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

    item = next((i for i in packs["10"]["items"] if i.get("name") == NAME), None)
    if item is None:
        print("pack 10: '%s' not found - nothing written." % NAME)
        return 1

    changes = 0

    if (item.get("form") or {}).get("fields") == FIELDS:
        print("write-on lines: already applied")
    elif item.get("form"):
        print("write-on lines: item already has a form - left alone")
    else:
        item["form"] = {"fields": list(FIELDS)}
        print("write-on lines added: %s" % ", ".join(FIELDS))
        changes += 1

    if item.get("body") == BODY_NEW:
        print("body: already applied")
    elif item.get("body") != BODY_OLD:
        print("body: not the expected text - left alone")
    else:
        print("body:\n  before: %s\n  after:  %s" % (BODY_OLD, BODY_NEW))
        item["body"] = BODY_NEW
        changes += 1

    module = next(m for m in data if m.get("num") == 10)

    # Weeks 4 and 5 both ask about the chosen outlet.
    for wi in (4, 5):
        week = module["weeks"][wi - 1]
        res = week.setdefault("resources", [])
        if NAME in res:
            print("week %d resources: already lists it" % wi)
        else:
            res.insert(0, NAME)
            print("week %d resources: now %s" % (wi, res))
            changes += 1

    week3 = module["weeks"][2]
    act = week3.get("activity") or ""
    if ACT_NEW in act:
        print("week 3 activity: already applied")
    elif act.count(ACT_OLD) != 1:
        print("week 3 activity: not the expected step 4. Run "
              "apply_module10_week3_register.py first - left alone.")
    else:
        week3["activity"] = act.replace(ACT_OLD, ACT_NEW)
        print("week 3 activity step 4 now writes the agreement on the card")
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
