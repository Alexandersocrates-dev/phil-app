#!/usr/bin/env python3
"""
Module 07 week 4: fallbacks where the session will actually fail, and no preview.

Read end to end, this session assumes a pupil who answers the questions. Two of
them are the ones a disengaged fourteen-year-old is least likely to answer, and
neither had anywhere to go.

"What do you want to be doing in two years?" - the honest answer is often "I
don't know", and there was no next move. Step 2 now offers two smaller ways in:
what they'd want to avoid, or what they'd do with a free day.

"Which subject connects to it?" - the old step 4 said to try a different subject
if they can't see a link, which only helps if some subject does connect. For a
pupil whose goal is nothing to do with school, none will. Step 4 now says to
take the subject they dislike least and look for one small link, which is a
thing a mentor can actually do rather than an instruction to keep trying.

The input was half announcements. "Say you'll ask what they want to be doing"
and "say you'll then look for a subject" are the activity described in advance,
and step 4 asked the pupil a rhetorical question about a link that does not
exist yet. It now teaches the idea and says plainly that "I don't know" is an
allowed answer, which is what makes the activity's fallback land.

And the worksheet's last row - "One thing I'll do differently this week" - was
never filled by any step. The reflect asks the question and then the answer goes
nowhere. It now goes on the sheet the pupil takes away.

    python3 apply_module07_week4_pass2.py --dry-run --courses data/courses_data.js
    python3 apply_module07_week4_pass2.py --courses data/courses_data.js

Standard library only. Run AFTER apply_module07_week4.py and
apply_chunking_wording.py - it expects the activity and check-in those leave.
"""

import argparse
import json
import os
import sys

EDITS = [
    {
        "field": "checkin",
        "why": "'anything' is vaguer than the thing they were actually asked to do",
        "old": "1. Ask: 'did you break anything into steps last week, and in which lesson?'\n"
               "2. Ask: 'what was different about that lesson, if anything?'\n"
               "3. If they didn't, ask: 'what would have needed to be true for you to?'",
        "new": "1. Ask: 'did you break any tasks into steps last week? Which lesson?'\n"
               "2. Ask: 'what was different about that lesson, if anything?'\n"
               "3. If they didn't, ask what would have made it possible. Take the answer and move on.",
    },
    {
        "field": "input",
        "why": "steps 2 and 3 described the activity in advance; step 4 asked about a link that did not exist yet",
        "old": "1. Explain that effort holds better when it's tied to something they want, not to being told.\n"
               "2. Say you'll ask what they want to be doing, and that any answer counts \u2014 vague or unrealistic is fine.\n"
               "3. Say you'll then look for a subject that connects to it, however loosely.\n"
               "4. Ask: 'would a link I picked for you actually work?' It has to be theirs, or it won't hold.",
        "new": "1. Explain that effort lasts longer when it's tied to something they want, rather than to being told.\n"
               "2. Say the link doesn't have to be impressive. A loose one they believe beats a neat one they don't.\n"
               "3. Say there's no wrong answer coming, including 'I don't know'.",
    },
    {
        "field": "activity",
        "why": "no route through the two questions a pupil is most likely to be stuck on",
        "old": "1. Ask: 'what do you want to be doing in two years?' Pupil writes it on the goal-mapping worksheet.\n"
               "2. Ask: 'which subject has anything at all to do with that?' Even loosely. Pupil writes the subject down.\n"
               "3. Ask how it connects, and write that on the worksheet in their words.\n"
               "4. If they can't see a link, say so honestly and try a different subject.",
        "new": "1. Ask: 'what do you want to be doing in two years?' Pupil writes it on the goal-mapping worksheet.\n"
               "2. If they don't know, ask what they'd want to avoid, or what they'd do with a free day. Write that instead.\n"
               "3. Ask: 'which subject has anything at all to do with that?' Pupil writes the subject down.\n"
               "4. If nothing connects, take the subject they dislike least and find one small link \u2014 a teacher, or just turning up.\n"
               "5. Ask how it connects, and write that on the worksheet in their words.",
    },
    {
        "field": "reflect",
        "why": "the worksheet's last row was never filled by any step",
        "old": "1. Ask: 'what's one piece of work this week you'd do differently, thinking about that?'\n"
               "2. Pupil names the lesson and the piece of work.",
        "new": "1. Ask: 'what's one piece of work this week you'd do differently because of that link?'\n"
               "2. Pupil writes the lesson and the piece of work on the last row of the worksheet.",
    },
]

TIMING_OLD = {"input": 10, "activity": 20}
TIMING_NEW = {"input": 8, "activity": 22}


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
    week = next(m for m in data if m.get("num") == 7)["weeks"][3]

    changes = 0
    for edit in EDITS:
        text = week.get(edit["field"]) or ""
        if text == edit["new"]:
            print("week 4 %s: already applied, skipping" % edit["field"])
            continue
        if text != edit["old"]:
            print("week 4 %s: not the expected text. Run apply_module07_week4.py "
                  "and apply_chunking_wording.py first. Nothing written." % edit["field"])
            return 1
        print("=" * 72)
        print("module 07 week 4 - %s" % edit["field"])
        print("why: %s" % edit["why"])
        print("--- before ---\n%s\n--- after ---\n%s\n" % (text, edit["new"]))
        week[edit["field"]] = edit["new"]
        changes += 1

    timing = week.get("timing") or {}
    if all(timing.get(k) == v for k, v in TIMING_NEW.items()):
        print("timing: already applied, skipping")
    elif all(timing.get(k) == v for k, v in TIMING_OLD.items()):
        timing.update(TIMING_NEW)
        print("timing: input 10 -> 8, activity 20 -> 22 (total unchanged at %d)"
              % sum(timing.values()))
        changes += 1
    else:
        print("timing: not the expected 10/20 - left alone")

    if args.dry_run:
        print("\nDRY RUN - %d change(s) would be made, nothing written." % changes)
        return 0
    if not changes:
        print("\nNothing to do.")
        return 0

    with open(args.courses, "w", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    print("\n%d change(s) written to %s" % (changes, args.courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
