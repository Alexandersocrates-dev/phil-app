#!/usr/bin/env python3
"""
Pre-ship checks for courses_data.js.

Run this in the local clone BEFORE pushing course text to main and before
running sync_course_text.py in the Railway shell.

Standard library only — no jinja2, no reportlab, no app import. It reads
courses_data.js as text, so it runs anywhere python3 does.

    python3 check_course_text.py courses_data.js
    python3 check_course_text.py courses_data.js --module 03
    python3 check_course_text.py courses_data.js --css templates/_card_art.svg

Exit status is 0 when nothing is flagged, 1 when anything is, so it can gate a
push. Findings are grouped ERROR (would ship broken) and WARNING (worth an eye,
often a deliberate choice).
"""

import argparse
import json
import re
import sys

# The order a mentor works through a session. Session 6 has no pupil, but the
# fields are the same, so one order serves both.
STEP_ORDER = ["checkin", "input", "activity", "reflect", "home"]

# Fields that must carry text in every week, pupil-facing or staff-only.
REQUIRED_WEEK_FIELDS = ["title", "objective", "checkin", "input", "activity",
                        "reflect", "lookfor", "home"]

REQUIRED_MODULE_FIELDS = ["num", "shortName", "title", "signs", "aims",
                          "approachNote", "relatedModule", "weeks"]

EXPECTED_MODULES = 20
EXPECTED_WEEKS = 6          # 5 with the pupil, 1 staff write-up

# Trailing nouns that get dropped when a week's wording differs from the pack's
# canonical name — "Body map handout" in the list, "the body map" in the text.
GENERIC_TAIL = ("handout", "card", "cards", "sheet", "sheets", "chart",
                "diagram", "list", "table", "form", "grid", "scale",
                "template", "poster", "checklist", "tracker", "map")

# A resource is "introduced" when a step tells the mentor to produce it.
INTRO_VERB = re.compile(
    r"\b(show|shows|showing|hand(?:\s+(?:out|over|them|the))?|give|gives|giving|"
    r"read|reads|bring\s+out|take\s+out|get\s+out|put\s+out|lay\s+out|"
    r"introduce|introduces|place|places|share|shares|open|opens|"
    r"fill\s+in|complete|completes|use|uses|using|work\s+through)\b",
    re.I)

NUM_LINE = re.compile(r"^\s*(\d+)[.)]\s+")


class Finding:
    def __init__(self, level, module, week, check, message, detail=None):
        self.level = level
        self.module = module
        self.week = week
        self.check = check
        self.message = message
        self.detail = detail

    def location(self):
        if self.module is None:
            return "file"
        if self.week is None:
            return "module %02d" % self.module
        return "module %02d week %d" % (self.module, self.week)


def load(path):
    """Reads courses_data.js and returns the array it exports.

    The file is `module.exports = [ ... ];` — everything after the first `=` is
    JSON, so it parses without a JS engine. A JSONDecodeError here is itself a
    finding worth stopping on: the file would not load in the app either.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    if "=" not in src:
        raise ValueError("no assignment found — is this courses_data.js?")
    body = src.split("=", 1)[1].strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return json.loads(body)


def load_aliases(path):
    """Canonical pack name -> its aliases, from data/resource_packs.json.

    A week's wording legitimately differs from the pack's canonical name in
    places, and the pack carries `aliases` for exactly that reason. Without this
    file the resource checks flag wording drift as a missing resource, so the
    check runs but reports itself as unverified.
    """
    with open(path, "r", encoding="utf-8") as fh:
        packs = json.load(fh)

    groups = []
    def walk(node):
        if isinstance(node, dict):
            name = node.get("name")
            if isinstance(name, str):
                found = [a for a in (node.get("aliases") or []) if isinstance(a, str)]
                groups.append([name] + found)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(packs)

    # Every name in a group resolves to every other name in it, both ways. A
    # week may list either the canonical name or an alias while the step text
    # uses the other — pack 02 lists "First/then visual cue cards" and the step
    # says "first-time response card", which are the same item.
    aliases = {}
    for group in groups:
        for name in group:
            aliases.setdefault(name, [])
            aliases[name].extend(other for other in group if other != name)
    return aliases


def normalise(text):
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_keys(name, aliases=None):
    """Phrases that would count as naming this resource in a mentor's wording.

    Longest first, so the fullest match wins. The shortened forms exist because
    a week's wording legitimately differs from the pack's canonical name.
    """
    base = normalise(name)
    keys = [base]
    for alias in (aliases or {}).get(name, []):
        keys.append(normalise(alias))
    words = base.split()
    # Strip generic tails, but never down to a single word: "Trigger list"
    # reduced to "trigger" matches every mention of a trigger in the prose, and
    # "Body map handout" reduced to "body" matches almost anything.
    while len(words) > 2 and words[-1] in GENERIC_TAIL:
        words = words[:-1]
        keys.append(" ".join(words))
    # "the anger cycle diagram" also reads as "the cycle diagram"
    if len(base.split()) > 2:
        keys.append(" ".join(base.split()[-2:]))
    seen, out = set(), []
    for k in keys:
        if k and k not in seen and len(k.split()) >= min(2, len(base.split())):
            seen.add(k)
            out.append(k)
    return sorted(out, key=len, reverse=True)


def find_mentions(week, keys):
    """Step indices where any of these phrases appears, and the sentences."""
    hits = {}
    for idx, field in enumerate(STEP_ORDER):
        text = week.get(field) or ""
        flat = normalise(text)
        for key in keys:
            if key in flat:
                sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n", text)
                             if key in normalise(s)]
                hits.setdefault(idx, []).extend(sentences)
                break
    return hits


def check_structure(data, findings):
    if len(data) != EXPECTED_MODULES:
        findings.append(Finding("ERROR", None, None, "structure",
                                "%d modules, expected %d" % (len(data), EXPECTED_MODULES)))
    nums = [m.get("num") for m in data]
    if nums != list(range(1, len(data) + 1)):
        findings.append(Finding("ERROR", None, None, "numbering",
                                "module numbers are not 1..%d in order: %s" % (len(data), nums)))
    seen = {}
    for m in data:
        num = m.get("num")
        if num in seen:
            findings.append(Finding("ERROR", num, None, "numbering",
                                    "duplicate module number"))
        seen[num] = True


def check_module(module, findings, aliases=None):
    num = module.get("num")
    for field in REQUIRED_MODULE_FIELDS:
        value = module.get(field)
        if value is None or (isinstance(value, (str, list)) and not value):
            findings.append(Finding("ERROR", num, None, "renders",
                                    "module field '%s' is missing or empty" % field))

    weeks = module.get("weeks") or []
    if len(weeks) != EXPECTED_WEEKS:
        findings.append(Finding("ERROR", num, None, "renders",
                                "%d weeks, expected %d (5 pupil sessions + the staff write-up)"
                                % (len(weeks), EXPECTED_WEEKS)))

    staff = [i for i, w in enumerate(weeks, 1) if w.get("staff_only")]
    if staff != [EXPECTED_WEEKS]:
        findings.append(Finding("ERROR", num, None, "renders",
                                "staff_only should be set on week %d only, found on %s"
                                % (EXPECTED_WEEKS, staff or "no week")))

    for i, week in enumerate(weeks, 1):
        check_week(num, i, week, findings, aliases)

    check_resource_vocabulary(module, findings, aliases)


def check_week(num, index, week, findings, aliases=None):
    for field in REQUIRED_WEEK_FIELDS:
        value = week.get(field)
        if not value or not str(value).strip():
            findings.append(Finding("ERROR", num, index, "renders",
                                    "week field '%s' is missing or empty" % field))

    # Numbering inside each instruction field.
    for field in STEP_ORDER:
        text = week.get(field) or ""
        lines = [ln for ln in text.split("\n") if NUM_LINE.match(ln)]
        if not lines:
            continue
        got = [int(NUM_LINE.match(ln).group(1)) for ln in lines]
        want = list(range(1, len(got) + 1))
        if got != want:
            findings.append(Finding("ERROR", num, index, "numbering",
                                    "'%s' is numbered %s, expected %s"
                                    % (field, got, want)))
        if len(lines) != len([ln for ln in text.split("\n") if ln.strip()]):
            unnumbered = [ln.strip() for ln in text.split("\n")
                          if ln.strip() and not NUM_LINE.match(ln)]
            findings.append(Finding("WARNING", num, index, "numbering",
                                    "'%s' mixes numbered and unnumbered lines" % field,
                                    unnumbered[:2]))

    if week.get("staff_only"):
        if week.get("resources"):
            findings.append(Finding("WARNING", num, index, "stranded",
                                    "the staff write-up lists resources; it has no pupil present",
                                    week.get("resources")))
        return

    if not week.get("timing"):
        findings.append(Finding("WARNING", num, index, "renders",
                                "no timing block on a pupil session"))

    check_resource_order(num, index, week, findings, aliases)


def check_resource_order(num, index, week, findings, aliases=None):
    resources = week.get("resources") or []
    if not resources:
        findings.append(Finding("WARNING", num, index, "stranded",
                                "pupil session lists no resources"))
        return

    for name in resources:
        keys = match_keys(name, aliases)
        hits = find_mentions(week, keys)

        if not hits:
            # Without the pack's aliases this cannot tell a genuinely unused
            # resource from a week that words it differently, so it stays a
            # warning until resource_packs.json is supplied.
            level = "ERROR" if aliases else "WARNING"
            note = ("it prints in the pack and is never used" if aliases
                    else "may just be worded differently — rerun with --packs to be sure")
            findings.append(Finding(level, num, index, "stranded",
                                    "'%s' is listed but never named in any step; %s"
                                    % (name, note)))
            continue

        first = min(hits)
        intro = None
        for idx in sorted(hits):
            if any(INTRO_VERB.search(s) for s in hits[idx]):
                intro = idx
                break

        if intro is None:
            findings.append(Finding("WARNING", num, index, "order",
                                    "'%s' is referred to but never handed out — "
                                    "no step tells the mentor to produce it" % name,
                                    hits[first][:1]))
        elif first < intro:
            findings.append(Finding("ERROR", num, index, "order",
                                    "'%s' is used in '%s' but not produced until '%s'"
                                    % (name, STEP_ORDER[first], STEP_ORDER[intro]),
                                    hits[first][:1]))


def check_resource_vocabulary(module, findings, aliases=None):
    """A resource named in a week's text but missing from that week's list.

    Only names that appear in some other week's list are checked, so this reads
    the course's own vocabulary rather than guessing at what a resource is.
    """
    num = module.get("num")
    weeks = module.get("weeks") or []
    vocabulary = {}
    for week in weeks:
        for name in week.get("resources") or []:
            vocabulary[name] = match_keys(name, aliases)

    for i, week in enumerate(weeks, 1):
        if week.get("staff_only"):
            continue
        listed = set(week.get("resources") or [])
        for name, keys in vocabulary.items():
            if name in listed:
                continue
            hits = find_mentions(week, keys)
            if hits:
                findings.append(Finding("WARNING", num, i, "stranded",
                                        "'%s' is named in the steps but not in this week's "
                                        "resources list, so it won't be in the printed pack"
                                        % name, hits[min(hits)][:1]))


def check_css(path, findings):
    """Brace balance and repeated selectors in a stylesheet or an SVG's <style>."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    blocks = re.findall(r"<style[^>]*>(.*?)</style>", text, re.S)
    css = "\n".join(blocks) if blocks else text

    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    opens = stripped.count("{")
    closes = stripped.count("}")
    if opens != closes:
        findings.append(Finding("ERROR", None, None, "css",
                                "%d '{' against %d '}' in %s — everything after the "
                                "imbalance is silently dropped by the browser"
                                % (opens, closes, path)))

    depth = 0
    for i, ch in enumerate(stripped):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                line = stripped[:i].count("\n") + 1
                findings.append(Finding("ERROR", None, None, "css",
                                        "unmatched '}' at line %d of %s" % (line, path)))
                depth = 0

    selectors = {}
    for m in re.finditer(r"(^|[};])\s*([^{}@;/][^{}]*?)\{", stripped):
        raw = m.group(2)
        if "\n\n" in raw:
            raw = raw.rsplit("\n\n", 1)[1]
        key = re.sub(r"\s+", " ", raw).strip().rstrip(",")
        if not key or key.startswith("@"):
            continue
        line = stripped[:m.start(2)].count("\n") + 1
        selectors.setdefault(key, []).append(line)

    for key, lines in sorted(selectors.items()):
        if len(lines) > 1:
            findings.append(Finding("WARNING", None, None, "css",
                                    "selector '%s' declared %d times (lines %s) — "
                                    "the last one wins"
                                    % (key[:60], len(lines),
                                       ", ".join(str(n) for n in lines))))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default="courses_data.js")
    ap.add_argument("--module", help="check one module only, e.g. 03")
    ap.add_argument("--packs", help="data/resource_packs.json — supplies each pack item's "
                                    "aliases, without which wording drift reads as a "
                                    "missing resource")
    ap.add_argument("--css", help="also check a stylesheet or an SVG's <style> block")
    ap.add_argument("--errors-only", action="store_true")
    args = ap.parse_args()

    try:
        data = load(args.path)
    except Exception as exc:
        print("could not read %s: %s" % (args.path, exc))
        return 2

    aliases = None
    if args.packs:
        try:
            aliases = load_aliases(args.packs)
        except Exception as exc:
            print("could not read %s: %s" % (args.packs, exc))
            return 2

    findings = []
    check_structure(data, findings)

    wanted = int(args.module) if args.module else None
    for module in data:
        if wanted and module.get("num") != wanted:
            continue
        check_module(module, findings, aliases)

    if args.css:
        check_css(args.css, findings)

    if args.errors_only:
        findings = [f for f in findings if f.level == "ERROR"]

    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level == "WARNING"]

    sessions = sum(len(m.get("weeks") or []) for m in data)
    print("%s — %d modules, %d sessions" % (args.path, len(data), sessions))
    print("%d error(s), %d warning(s)" % (len(errors), len(warnings)))
    if aliases is None:
        print("resource checks UNVERIFIED — no --packs given, so a week that words a "
              "resource differently reads as a missing one")
    else:
        print("resource aliases loaded for %d pack items" % len(aliases))
    print()

    for level in ("ERROR", "WARNING"):
        group = [f for f in findings if f.level == level]
        if not group:
            continue
        print("=" * 72)
        print(level + "S")
        print("=" * 72)
        for f in sorted(group, key=lambda f: (f.module or 0, f.week or 0, f.check)):
            print("[%s] %s: %s" % (f.check, f.location(), f.message))
            for line in f.detail or []:
                print("        > %s" % str(line).strip()[:150])
        print()

    if not findings:
        print("Nothing flagged. Safe to push, then sync.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
