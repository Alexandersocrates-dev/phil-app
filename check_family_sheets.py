"""Check that every home activity which needs a sheet can actually reach one.

A family gets one link. If the activity says "look at the avoidance ladder" and
no shareable sheet resolves for that week, the family is asked to use something
they have no way of seeing, and nothing anywhere reports it — the page simply
renders without a button.

This is the check that catches it. It reproduces exactly what the running app
does: the same normalisation, the same alias matching, the same share flag. Run
it after editing course text or the packs.

    python3 check_family_sheets.py            # report
    python3 check_family_sheets.py --quiet    # exit 1 on problems, print little

Run from the repo root.
"""

import json
import os
import re
import sys

COURSES = os.path.join("data", "courses_data.js")
PACKS = os.path.join("data", "resource_packs.json")

# Words that mean the activity expects something physical in front of them.
NEEDS_SHEET = re.compile(
    r"\b(card|sheet|chart|list|plan|map|template|scale|thermometer|timeline|"
    r"diagram|handout|tally|toolkit|worksheet|ladder|script|"
    r"fill (in|it)|tick|write (it|them) (down|on)|use the|look at the|"
    r"read (through )?the|keep a copy|put (it|them) on)\b", re.I)


def norm(name):
    """The app's own resource matching: case, spacing and punctuation ignored."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def load_courses(path):
    text = open(path, encoding="utf-8").read()
    match = re.search(r"=\s*(\[.*\])\s*;?\s*$", text, re.S)
    return json.loads(match.group(1) if match else text)


def shareable_for(pack, resource_names):
    """What a family could print for one week, matching names and aliases."""
    wanted = {norm(n) for n in resource_names}
    out = []
    for item in pack.get("items", []):
        if not item.get("share"):
            continue
        names = {norm(item.get("name"))}
        names |= {norm(a) for a in item.get("aliases", [])}
        if names & wanted:
            out.append(item["name"])
    return out


# Words too common to identify a sheet on their own: "card", "the plan" and
# "template" appear in half the catalogue.
GENERIC = {"card", "cards", "sheet", "template", "list", "plan", "set", "note",
           "notes", "options", "ideas", "my", "the", "and", "for", "how", "it",
           "in", "of", "a", "one", "page", "at", "school", "me", "week"}


def named_in(activity, pack):
    """Pack items this activity names, by their distinctive words.

    "Look at the avoidance ladder together" names the Avoidance ladder
    template. Checking only that some sheet is reachable is not enough: a week
    can carry two sheets, one shared and one not, and the activity can be
    asking for the one that isn't.
    """
    text = set(re.findall(r"[a-z]+", activity.lower()))
    hits = []
    for item in pack.get("items", []):
        words = {w for w in re.findall(r"[a-z]+", item.get("name", "").lower())
                 if w not in GENERIC and len(w) > 3}
        # Every distinctive word has to be there, so "toolkit list" does not
        # match on "list" alone.
        if words and words <= text:
            hits.append(item)
    return hits


def main():
    quiet = "--quiet" in sys.argv
    for path in (COURSES, PACKS):
        if not os.path.exists(path):
            sys.exit("%s not found — run this from the repo root." % path)
    courses = load_courses(COURSES)
    packs = json.load(open(PACKS, encoding="utf-8"))

    problems, ok = [], 0
    # A name in a week's resource list with no pack item behind it is a
    # separate fault, and worth catching in the same pass: it means the session
    # page shows nothing either.
    unmatched = []

    for course in courses:
        mod = "%02d" % course["num"]
        pack = packs.get(mod, {})
        by_name = {norm(i.get("name")) for i in pack.get("items", [])}
        for item in pack.get("items", []):
            by_name |= {norm(a) for a in item.get("aliases", [])}
        for index, week in enumerate(course["weeks"], start=1):
            for name in (week.get("resources") or []):
                if norm(name) not in by_name:
                    unmatched.append((course["num"], index, name))
            home = (week.get("home") or "").strip()
            if not home or not NEEDS_SHEET.search(home):
                continue
            # Anything the activity names by title has to be shareable itself,
            # not merely accompanied by something that is.
            named = named_in(home, pack)
            missing = [i["name"] for i in named if not i.get("share")]
            found = shareable_for(pack, week.get("resources") or [])
            if missing:
                problems.append((course["num"], index, home,
                                 "names %s, which is not shareable" % ", ".join(missing)))
            elif found:
                ok += 1
            else:
                problems.append((course["num"], index, home,
                                 "week's resources: %s — none marked shareable"
                                 % (week.get("resources") or "none listed")))

    if not quiet:
        print("Home activities needing a sheet: %d reachable, %d not\n"
              % (ok, len(problems)))
        for num, wk, home, why in problems:
            print("  M%-2d w%d  %s" % (num, wk, home[:110]))
            print("          %s\n" % why)
        if unmatched:
            print("Resources named in a week with no pack item behind them:")
            for num, wk, name in unmatched:
                print("  M%-2d w%d  %s" % (num, wk, name))
    if problems or unmatched:
        sys.exit(1)
    if not quiet:
        print("All good.")


if __name__ == "__main__":
    main()
