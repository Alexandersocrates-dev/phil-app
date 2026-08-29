#!/usr/bin/env python3
"""
Course summary write-up: three sections, and the two questions it never asked.

Session 6 is one shared template across all twenty modules. Its five boxes
already reach the reports as labelled sections, but two things the summary
needs were missing.

The reason for referral. Box 1 asked where the pupil was when the course
started and never why they were put on it. A teacher picking the plan up in
March has the pupil's starting point with no idea what prompted any of it, and
the school cannot show a referral led anywhere without recording what the
referral was for.

The effect of the course. Box 5 went straight from the plan's contents to who
does what by when. Nobody ever wrote what the course actually did. That is the
line a governor, a parent or the next school reads first, and it was the one
line the write-up did not contain.

The five boxes now group into the three sections the report needs:

    1  Starting point and referral        box 1
    2  What was worked on, and results    boxes 2 and 3
    3  Summary and plan                   boxes 4 and 5

Also removes the job title from box 5, which named a post in the same breath as
telling the writer not to.

    python3 apply_summary_sections.py --dry-run --courses data/courses_data.js
    python3 apply_summary_sections.py --courses data/courses_data.js

Standard library only. Applies to session 6 of all twenty modules.
"""

import argparse
import json
import os
import sys

CHECKIN_OLD = (
    "1. No pupil in this one. Twenty minutes on your own, after the course.\n"
    "2. Read the session summaries and the pupil's own sheets below before writing anything.\n"
    "3. In the box: where they were when the course started, and what has changed since. "
    "Their week one rating and their own words are below."
)
CHECKIN_NEW = (
    "1. No pupil in this one. Twenty minutes on your own, after the course.\n"
    "2. Read the session summaries and the pupil's own sheets below before writing anything.\n"
    "3. In the box: why this pupil was referred, and what was happening at the time.\n"
    "4. Then where they were when the course started. Their week one rating and "
    "their own words are below."
)

HOME_OLD = (
    "1. In the box: who is doing what, and by when. Name people, not job titles.\n"
    "2. Agree it with your line manager before it goes anywhere.\n"
    "3. Share it with the pupil's class teachers and your pastoral lead, and bring "
    "it to the follow-up chat you agreed."
)
HOME_NEW = (
    "1. In the box, first: two or three lines on what the course did. What changed, "
    "what did not, and whether it met what they were referred for.\n"
    "2. Then who is doing what, and by when. Name people, not job titles.\n"
    "3. Agree it with your line manager before it goes anywhere.\n"
    "4. Share it with the pupil's class teachers and whoever leads on pastoral "
    "support, and bring it to the follow-up chat you agreed."
)

OBJ_OLD = "The mentor has a one-page plan that other staff can pick up and use."
OBJ_NEW = ("The mentor has a one-page record of why the pupil was referred, what "
           "the course did, and what happens next.")


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
    args = ap.parse_args()

    if not os.path.exists(args.courses):
        print("cannot find %s" % args.courses)
        return 1

    prefix, data = load_courses(args.courses)

    edits = (("objective", OBJ_OLD, OBJ_NEW),
             ("checkin", CHECKIN_OLD, CHECKIN_NEW),
             ("home", HOME_OLD, HOME_NEW))

    # Check every module before writing anything: a template shared by twenty
    # weeks should not end up applied to some of them.
    for m in data:
        week = m["weeks"][5]
        if not week.get("staff_only"):
            print("module %02d week 6 is not the staff write-up - nothing written."
                  % m.get("num"))
            return 1
        for field, old, new in edits:
            text = week.get(field) or ""
            if text not in (old, new):
                print("module %02d %s: not the expected text - nothing written."
                      % (m.get("num"), field))
                return 1

    changed_modules = 0
    for m in data:
        week = m["weeks"][5]
        touched = False
        for field, old, new in edits:
            if (week.get(field) or "") == old:
                week[field] = new
                touched = True
        if touched:
            changed_modules += 1

    if not changed_modules:
        print("Nothing to do - all twenty already applied.")
        return 0

    print("=" * 72)
    for field, old, new in edits:
        print("session 6 - %s" % field)
        print("--- before ---\n%s\n--- after ---\n%s\n" % (old, new))
    print("applies to session 6 of %d module(s)" % changed_modules)

    if args.dry_run:
        print("\nDRY RUN - nothing written.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("\nwritten to %s" % args.courses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
