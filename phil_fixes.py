#!/usr/bin/env python3
"""Phil fixes, 22 Sep 2026. Run from the root of ~/Desktop/phil-app-clone:

    python3 ~/Downloads/phil_fixes.py

1. Mentoring list report: pupils enrolled but not yet started now appear,
   shown as "Not started".
2. Course summary record (the staff-only final session): each part prints
   under its own heading with more space between, the duplicated sections are
   gone, and the last section is "Summary for this course".
3. Session flow: the final session's last step is "Summary for this course".

Every change is checked before anything is written. If a check fails, nothing
is written. If the edited Python fails to compile, the originals are restored.
"""
import os
import py_compile
import re
import sys

FILES = {
    "app": "app.py",
    "gen": os.path.join("pdf", "generate.py"),
    "form": os.path.join("templates", "session_form.html"),
}

for path in FILES.values():
    if not os.path.exists(path):
        sys.exit(f"Can't find {path}. Run this from ~/Desktop/phil-app-clone. Nothing changed.")

orig = {k: open(p, encoding="utf-8").read() for k, p in FILES.items()}
text = dict(orig)
problems = []

if "_caseload_period_filter" in text["app"] or "_staff_write_up" in text["gen"]:
    sys.exit("These fixes are already in. Nothing changed.")


def func_bounds(src, name):
    """Start and end of a top-level function, so a change can't land elsewhere."""
    start = src.find(f"\ndef {name}(")
    if start == -1 or src.count(f"\ndef {name}(") != 1:
        return None
    ends = [i for i in (src.find("\ndef ", start + 1), src.find("\n@", start + 1)) if i != -1]
    return start, (min(ends) if ends else len(src))


def replace_in(key, func, old, new, label, regex=False, flags=0):
    """Replace exactly one match, optionally only inside one function."""
    src = text[key]
    lo, hi = 0, len(src)
    if func:
        bounds = func_bounds(src, func)
        if not bounds:
            problems.append(f"{label}: couldn't find function {func}()")
            return
        lo, hi = bounds
    part = src[lo:hi]
    if regex:
        found = len(re.findall(old, part, flags))
        if found != 1:
            problems.append(f"{label}: expected 1 match, found {found}")
            return
        part = re.sub(old, new, part, count=1, flags=flags)
    else:
        found = part.count(old)
        if found != 1:
            problems.append(f"{label}: expected 1 match, found {found}")
            return
        part = part.replace(old, new, 1)
    text[key] = src[:lo] + part + src[hi:]


def insert_before(key, marker, block, label):
    src = text[key]
    if src.count(marker) != 1:
        problems.append(f"{label}: expected 1 '{marker.strip()}', found {src.count(marker)}")
        return
    i = src.index(marker)
    text[key] = src[:i] + block + src[i:]


# ---------------------------------------------------------------- 1. app.py

CASELOAD_FILTER = '''def _caseload_period_filter(date_from, date_to):
    """_year_filter, plus courses that haven't had a session yet.

    _year_filter puts a course in the year its sessions ran. That is right for
    the impact figures, but wrong for a list of who a mentor is working with:
    a pupil enrolled and not yet seen has no sessions, so they matched no year
    or term and vanished from the list. Until their first session they count
    from the day they were enrolled.
    """
    if not (date_from and date_to):
        return "", []
    return (""" AND (EXISTS (SELECT 1 FROM session_records sr
                             WHERE sr.enrolment_id = enrolments.id
                               AND sr.date BETWEEN ? AND ?)
                 OR (NOT EXISTS (SELECT 1 FROM session_records sr
                                 WHERE sr.enrolment_id = enrolments.id)
                     AND enrolments.status = 'active'
                     AND enrolments.start_date <= ?))""",
            [date_from, date_to, date_to])


'''

insert_before("app", "def _caseload_rows(", CASELOAD_FILTER, "caseload filter helper")
replace_in("app", "_caseload_rows", "_year_filter(year_from, year_to)",
           "_caseload_period_filter(year_from, year_to)", "caseload year filter")
replace_in("app", "_caseload_rows", "_year_filter(term_from, term_to)",
           "_caseload_period_filter(term_from, term_to)", "caseload term filter")
replace_in("app", "_caseload_rows",
           r"""^([ \t]*)(else f"Week \{r\['current_week'\]\} of \{SESSIONS_PER_COURSE\}"\))""",
           lambda m: f'{m.group(1)}else "Not started" if not r["current_week"]\n'
                     f'{m.group(1)}{m.group(2)}',
           "caseload 'Not started' progress", regex=True, flags=re.M)

# Tell the PDF which session it is printing: once when the session is saved...
replace_in("app", None,
           r'week\["title"\], mentor_name,(\s*)resource_work=resource_work\)',
           lambda m: f'week["title"], mentor_name,{m.group(1)}'
                     f'resource_work=resource_work, staff_only=staff_session)',
           "session save PDF call", regex=True)

# ...and once when a record's PDF is rebuilt for download.
replace_in("app", None,
           r'^([ \t]*)(resource_work = resource_work_for\(conn, ctx\["enrolment_id"\], record\["week_id"\]\))$',
           lambda m: f'{m.group(1)}{m.group(2)}\n'
                     f'{m.group(1)}staff_week = conn.execute("SELECT staff_only FROM weeks WHERE id=?", '
                     f'(record["week_id"],)).fetchone()',
           "download route week lookup", regex=True, flags=re.M)
replace_in("app", None,
           r'(ctx\["mentor_name"\] or "Mentor",\s*resource_work=resource_work)\)',
           lambda m: f'{m.group(1)}, staff_only=bool(staff_week and staff_week["staff_only"]))',
           "download route PDF call", regex=True)

# ---------------------------------------------------------------- 2. pdf/generate.py

STAFF_HELPER = '''# The staff session saves its five boxes into one field as "Label: text"
# paragraphs (see the staff_session branch in app.py). The course write-up
# prints them back out under their own headings. Stored label, printed heading.
STAFF_WRITE_UP = [
    ("Starting point and reason for referral", "Starting point and reason for referral"),
    ("What was worked on", "What was worked on"),
    ("What worked", "What worked"),
    ("If it happens again", "If it happens again"),
    ("Summary and next steps", "Summary for this course"),
]


def _staff_write_up(record):
    """(heading, text) pairs for the course write-up, in order."""
    import re
    text = record["what_happened"] or ""
    pattern = re.compile(r"^(%s): " % "|".join(re.escape(s) for s, _ in STAFF_WRITE_UP),
                         re.M)
    found = list(pattern.finditer(text))
    parts = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        parts[m.group(1)] = text[m.end():end].strip()
    # The edit page saves the last two boxes to their own columns, so those
    # hold the current wording if the record was corrected after saving.
    if (record["reflection_goal"] or "").strip():
        parts["If it happens again"] = record["reflection_goal"].strip()
    if (record["mentor_notes"] or "").strip():
        parts["Summary and next steps"] = record["mentor_notes"].strip()
    pairs = []
    if not found and text.strip():
        # No labels in it (written before they existed, or edited out of
        # shape): print it whole rather than lose it.
        pairs.append(("What happened", text.strip()))
    pairs += [(shown, parts.get(stored, "")) for stored, shown in STAFF_WRITE_UP]
    return pairs


'''

insert_before("gen", "def session_record_pdf(", STAFF_HELPER, "course write-up helper")

replace_in("gen", "session_record_pdf",
           r"(def session_record_pdf\([^)]*?resource_work=None)\):",
           lambda m: f"{m.group(1)}, staff_only=False):",
           "session_record_pdf signature", regex=True, flags=re.S)

replace_in("gen", "session_record_pdf",
           '''    def section(label, text):
        nonlocal y
        y = _doc_section(c, x, y, label, max_width)
        c.setFillColor(INK)
        y = _wrap(c, text or "-", x, y, max_width)
        y -= 5 * mm
''',
           '''    def section(label, text, size=9, leading=12, gap=5 * mm):
        nonlocal y
        y = _doc_section(c, x, y, label, max_width)
        c.setFillColor(INK)
        y = _wrap(c, text or "-", x, y, max_width, size=size, leading=leading)
        y -= gap
''', "section() spacing options")

OLD_BODY = '''    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    mood = _rating_word(record["mood_rating"], MOOD_LABELS)
    engagement = _rating_word(record["engagement_rating"], ENGAGEMENT_LABELS)
    c.drawString(x, y, f"Mood: {mood}    Took part: {engagement}")
    y -= 8 * mm

    section("What happened", record["what_happened"])
    section("Reflect", record["reflection_goal"])
    section("Summary for this session", record["mentor_notes"])
'''
NEW_BODY = ('''    if staff_only:
        # The course write-up. Its five parts print under their own headings
        # with more room between them, instead of as one block of text, and
        # without the ratings line: there is no pupil in the room.
        for label, text in _staff_write_up(record):
            section(label, text, size=10, leading=14, gap=9 * mm)
    else:
'''
            + "".join(("    " + line) if line.strip() else line
                      for line in OLD_BODY.splitlines(keepends=True)))

replace_in("gen", "session_record_pdf", OLD_BODY, NEW_BODY, "session record body")

# ---------------------------------------------------------------- 3. session flow

replace_in("form", None,
           "{% if week.staff_only %}Plan moving forward{% else %}",
           "{% if week.staff_only %}Summary for this course{% else %}",
           "final session heading")

# ---------------------------------------------------------------- write

if problems:
    print("Stopped before writing anything:")
    for p in problems:
        print("  -", p)
    print("\nNo files were changed. Paste this output back to Claude.")
    sys.exit(1)

for key, path in FILES.items():
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text[key])

try:
    py_compile.compile(FILES["app"], doraise=True)
    py_compile.compile(FILES["gen"], doraise=True)
except py_compile.PyCompileError as err:
    for key, path in FILES.items():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(orig[key])
    print("Compile check failed, so the original files were put back:\n")
    print(err)
    sys.exit(1)

print("Done. app.py, pdf/generate.py and templates/session_form.html updated,")
print("and both Python files compile. Check with: git diff --stat")
