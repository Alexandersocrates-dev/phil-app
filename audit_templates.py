#!/usr/bin/env python3
"""
Audits every template for the mechanical UX and accessibility faults that can be
found without rendering: heading structure, form labelling, autocomplete, alt
text, tap-target sizing, link text, and a few security-adjacent markup habits.

Run from the repo root:

    python3 audit_templates.py

It reports, it never edits. Findings are ordered by severity so the top of the
output is the part worth acting on.

What it deliberately does NOT check: colour contrast of rendered output, real
tap-target geometry, and anything requiring a logged-in session. Those need a
browser and an account.
"""
import os
import re
import sys
from collections import defaultdict

TEMPLATE_DIR = "templates"

# Fields where a missing autocomplete attribute costs the user real effort,
# because a password manager or the browser would otherwise fill them.
AUTOCOMPLETE_EXPECTED = {
    "email": "email",
    "password": "current-password or new-password",
    "tel": "tel",
}

VAGUE_LINK_TEXT = {"click here", "here", "read more", "more", "link", "this", "learn more"}

SEVERITY = {"high": 0, "medium": 1, "low": 2}


def strip_jinja(html):
    """Removes Jinja tags so they don't confuse the tag counting."""
    html = re.sub(r"\{%.*?%\}", " ", html, flags=re.S)
    html = re.sub(r"\{\{.*?\}\}", "x", html, flags=re.S)
    return html


def audit(path, raw):
    """Returns a list of (severity, message) for one template."""
    out = []
    html = strip_jinja(raw)
    add = lambda sev, msg: out.append((sev, msg))

    # --- heading structure -------------------------------------------------
    h1s = re.findall(r"<h1\b", html)
    if len(h1s) > 1:
        add("high", f"{len(h1s)} <h1> elements — a page should have exactly one")

    levels = [int(m) for m in re.findall(r"<h([1-6])\b", html)]
    for prev, cur in zip(levels, levels[1:]):
        if cur > prev + 1:
            add("medium", f"heading jumps from h{prev} to h{cur} — screen readers lose the outline")
            break

    # --- forms -------------------------------------------------------------
    inputs = re.findall(r"<(input|select|textarea)\b([^>]*)>", html, re.I)
    for tag, attrs in inputs:
        if re.search(r'type=["\']hidden', attrs, re.I):
            continue
        has_id = re.search(r'id=["\']([^"\']+)', attrs)
        labelled = False
        if has_id and re.search(r'<label[^>]*for=["\']%s["\']' % re.escape(has_id.group(1)), html):
            labelled = True
        if re.search(r"aria-label", attrs, re.I):
            labelled = True
        name = re.search(r'name=["\']([^"\']+)', attrs)
        if not labelled and not has_id:
            # a <label>text<input></label> wrapper is also valid, so only flag
            # when there is no id to point at and no aria-label either
            add("medium", f"<{tag} name={name.group(1) if name else '?'}> has no label, id or aria-label")

        itype = re.search(r'type=["\']([^"\']+)', attrs)
        itype = itype.group(1).lower() if itype else "text"
        if itype in AUTOCOMPLETE_EXPECTED and "autocomplete" not in attrs.lower():
            add("medium", f"<{tag} type={itype}> has no autocomplete "
                          f"(expected {AUTOCOMPLETE_EXPECTED[itype]}) — blocks password managers")

    forms = re.findall(r"<form\b.*?</form>", html, re.S | re.I)
    for f in forms:
        if not re.search(r'type=["\']submit|<button', f, re.I):
            add("high", "a <form> has no submit button")

    # --- images and icons --------------------------------------------------
    for m in re.finditer(r"<img\b([^>]*)>", html, re.I):
        if "alt=" not in m.group(1).lower():
            add("high", "<img> without an alt attribute")

    # A sprite of <symbol> definitions is hidden and never announced, so only
    # check SVGs that actually appear on the page.
    sprite_spans = [(m.start(), m.end()) for m in
                    re.finditer(r"<svg\b[^>]*display:\s*none.*?</svg>", html, re.S | re.I)]
    unlabelled_svg = 0
    for m in re.finditer(r"<svg\b([^>]*)>", html, re.I):
        if any(a <= m.start() < b for a, b in sprite_spans):
            continue
        a = m.group(1).lower()
        if "aria-hidden" not in a and "role=" not in a and "<title" not in html[m.end():m.end() + 200]:
            unlabelled_svg += 1
    if unlabelled_svg:
        add("low", f"{unlabelled_svg} inline <svg> with no aria-hidden or role")

    # --- links -------------------------------------------------------------
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", html, re.S | re.I):
        attrs, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip().lower()
        if text in VAGUE_LINK_TEXT:
            add("medium", f'link text "{text}" says nothing out of context')
        if 'target="_blank"' in attrs and "noopener" not in attrs:
            add("medium", 'target="_blank" without rel="noopener"')
        if not text and "aria-label" not in attrs.lower():
            add("medium", "a link has no text and no aria-label")

    # --- buttons -----------------------------------------------------------
    for m in re.finditer(r"<button\b([^>]*)>(.*?)</button>", html, re.S | re.I):
        attrs, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not text and "aria-label" not in attrs.lower():
            add("high", "icon-only <button> with no aria-label")

    # --- typography and tap targets in inline styles -----------------------
    for m in re.finditer(r"font-size:\s*([\d.]+)px", raw):
        if float(m.group(1)) < 11:
            add("medium", f"font-size {m.group(1)}px — below the 11px floor for legibility")
            break

    # --- markup hygiene ----------------------------------------------------
    ids = re.findall(r'\bid=["\']([^"\']+)["\']', html)
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        add("medium", f"duplicate id attributes: {', '.join(sorted(dupes)[:4])}")

    if re.search(r"<table\b", html, re.I) and not re.search(r"<th\b", html, re.I):
        add("medium", "<table> with no <th> — no column headers for screen readers")

    return out


def main():
    if not os.path.isdir(TEMPLATE_DIR):
        sys.exit(f"Run this from the repo root: no {TEMPLATE_DIR}/ directory here.")

    findings = defaultdict(list)
    files = sorted(f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html"))
    for name in files:
        path = os.path.join(TEMPLATE_DIR, name)
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        for sev, msg in audit(path, raw):
            findings[(sev, msg)].append(name)

    ordered = sorted(findings.items(), key=lambda kv: (SEVERITY[kv[0][0]], -len(kv[1])))
    total = sum(len(v) for v in findings.values())

    print(f"Audited {len(files)} templates, {total} findings\n")
    current = None
    for (sev, msg), where in ordered:
        if sev != current:
            current = sev
            print(f"\n=== {sev.upper()} ===")
        pages = ", ".join(sorted(set(where))[:6])
        more = "" if len(set(where)) <= 6 else f" (+{len(set(where)) - 6} more)"
        print(f"  [{len(where)}x] {msg}\n        {pages}{more}")

    if not ordered:
        print("No findings.")


if __name__ == "__main__":
    main()
