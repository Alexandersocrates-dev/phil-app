#!/usr/bin/env python3
"""
Applies the mechanical fixes from audit_templates.py across templates/.

Only the changes that are safe to make without judgement:
  1. rel="noopener" on target="_blank"
  2. autocomplete on email and password fields
  3. aria-label on form controls that have no label, derived from the name
  4. aria-hidden on decorative inline SVG icons

Deliberately NOT touched, because each needs a human decision:
  - duplicate <h1> (which one is the real page title?)
  - heading level jumps (changing them changes the visual style)
  - forms with no submit button (may be intentional auto-submit)
  - duplicate id attributes (needs to know which element owns the id)
  - font sizes under 11px: a dry run showed 38 of them, most deliberate
    (the phone mockup, card category labels). Raising them all would change
    the design, so they are reported by the audit and left to a person.

Run from the repo root. Use --dry-run first to see what it would do:

    python3 apply_ux_fixes.py --dry-run
    python3 apply_ux_fixes.py

Safe to run twice: every change checks whether it has already been applied.
"""
import os
import re
import sys

TEMPLATE_DIR = "templates"

# Which password fields are new passwords rather than existing ones. A browser
# offering "suggest strong password" on a login form is worse than no hint.
NEW_PASSWORD_FILES = {
    "signup.html", "reset_password.html", "account_password.html",
    "mentor_new.html", "staff_team_new.html", "staff_establishment_new.html",
    "link_parent.html", "parent_requests.html",
}

# Where the field name alone produces awkward English, say it properly. A label
# is read aloud, so "Check-in notes" beats "Checkin notes".
LABEL_OVERRIDES = {
    "checkin_note": "Check-in notes",
    "input_note": "Notes on the input step",
    "activity_note": "Notes on the activity",
    "reflect_note": "Notes on the reflection",
    "next_session_note": "Notes for the next session",
    "safeguarding_flag": "Flag a safeguarding concern",
    "safeguarding_note": "Safeguarding note",
    "mood_rating": "Mood rating, 1 to 5",
    "engagement_rating": "Engagement rating, 1 to 5",
    "weekx_input": "Week input content",
    "weekx_lookfor": "What to look for this week",
    "focus_area": "Focus area",
    "course_id": "Choose a course",
    "mentor_id": "Choose a mentor",
    "pupil_id": "Choose a pupil",
    "parent_access_enabled": "Give the parent or carer access",
    "response": "Your response",
}


# Field names that are self-describing enough to build a label from.
def label_from_name(name):
    if name in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[name]
    words = re.split(r"[_\-]", name)
    words = [w for w in words if w and w != "x"]
    if not words:
        return None
    text = " ".join(words)
    text = text.replace("weekx", "week").replace("note", "notes")
    return text[0].upper() + text[1:]


def fix_noopener(html):
    n = 0
    def repl(m):
        nonlocal n
        tag = m.group(0)
        if "noopener" in tag:
            return tag
        n += 1
        return tag[:-1].rstrip() + ' rel="noopener">'
    html = re.sub(r"<a\b[^>]*target=[\"']_blank[\"'][^>]*>", repl, html, flags=re.I)
    return html, n


def fix_autocomplete(html, filename):
    n = 0
    def repl(m):
        nonlocal n
        tag = m.group(0)
        if "autocomplete" in tag.lower():
            return tag
        t = re.search(r'type=["\']([^"\']+)', tag)
        t = t.group(1).lower() if t else ""
        if t == "email":
            value = "email"
        elif t == "password":
            value = "new-password" if filename in NEW_PASSWORD_FILES else "current-password"
        elif t == "tel":
            value = "tel"
        else:
            return tag
        n += 1
        return tag[:-1].rstrip() + f' autocomplete="{value}">'
    html = re.sub(r"<input\b[^>]*>", repl, html, flags=re.I)
    return html, n


def fix_aria_labels(html):
    """Adds aria-label to controls that have neither a label nor an id to bind one."""
    n = 0
    def repl(m):
        nonlocal n
        tag = m.group(0)
        low = tag.lower()
        if "aria-label" in low or 'type="hidden"' in low or "type='hidden'" in low:
            return tag
        if re.search(r'\bid=["\']', tag):
            return tag  # a label may bind to it; leave alone
        name = re.search(r'name=["\']([^"\']+)', tag)
        if not name:
            return tag
        text = label_from_name(name.group(1))
        if not text:
            return tag
        n += 1
        close = "/>" if tag.rstrip().endswith("/>") else ">"
        body = tag.rstrip()[:-len(close)].rstrip()
        return f'{body} aria-label="{text}"{close}'
    html = re.sub(r"<(?:input|select|textarea)\b[^>]*>", repl, html, flags=re.I)
    return html, n


def fix_font_sizes(html):
    n = 0
    def repl(m):
        nonlocal n
        size = float(m.group(1))
        if size >= 11:
            return m.group(0)
        n += 1
        return "font-size:11px"
    html = re.sub(r"font-size:\s*([\d.]+)px", repl, html)
    return html, n


def fix_svg_aria(html):
    """Marks inline SVGs decorative. Icons sit next to their own text label, so
    announcing them adds noise rather than meaning."""
    n = 0
    sprite = [(m.start(), m.end()) for m in
              re.finditer(r"<svg\b[^>]*display:\s*none.*?</svg>", html, re.S | re.I)]
    out, last = [], 0
    for m in re.finditer(r"<svg\b[^>]*>", html, re.I):
        if any(a <= m.start() < b for a, b in sprite):
            continue
        tag = m.group(0)
        if "aria-hidden" in tag.lower() or "role=" in tag.lower():
            continue
        out.append((m.start(), m.end(), tag[:-1].rstrip() + ' aria-hidden="true">'))
        n += 1
    if out:
        parts, last = [], 0
        for start, end, new in out:
            parts.append(html[last:start]); parts.append(new); last = end
        parts.append(html[last:])
        html = "".join(parts)
    return html, n


FIXES = [
    ("rel=noopener", lambda h, f: fix_noopener(h)),
    ("autocomplete", fix_autocomplete),
    ("aria-label", lambda h, f: fix_aria_labels(h)),
    ("svg aria-hidden", lambda h, f: fix_svg_aria(h)),
]


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.isdir(TEMPLATE_DIR):
        sys.exit("Run this from the repo root: no templates/ directory here.")

    totals = {name: 0 for name, _ in FIXES}
    touched = []
    for filename in sorted(f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html")):
        path = os.path.join(TEMPLATE_DIR, filename)
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        html = original
        per_file = []
        for name, fn in FIXES:
            html, n = fn(html, filename)
            if n:
                totals[name] += n
                per_file.append(f"{n} {name}")
        if html != original:
            touched.append((filename, ", ".join(per_file)))
            if not dry:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(html)

    print(("DRY RUN — nothing written\n" if dry else "") + f"templates changed: {len(touched)}\n")
    for filename, what in touched:
        print(f"  {filename:34} {what}")
    print("\ntotals:")
    for name, n in totals.items():
        print(f"  {n:4}  {name}")
    if dry:
        print("\nRun again without --dry-run to apply.")


if __name__ == "__main__":
    main()
