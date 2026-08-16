"""
Phil - PDF generation (certificates and session records).

Uses reportlab directly rather than a template engine, matching the approach
already used in the project's build_certificate_pdf.py / build_session_record_pdf.py
scripts, so a future production build can port this straight into the small
internal PDF microservice the Technical Build Spec recommends (section 2.1),
reusing this logic rather than rewriting it.
"""

import os
import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

NAVY = HexColor("#1B2A4A")
TEAL = HexColor("#1D9E75")
TEAL_DARK = HexColor("#0F6E56")
AMBER = HexColor("#EF9F27")
CREAM = HexColor("#FBF8F2")
INK = HexColor("#2C2C2A")
MUTED = HexColor("#5F5E5A")
RED = HexColor("#A32D2D")
CARD = HexColor("#FFFFFF")
BORDER = HexColor("#E4E1D6")

PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pdfs")
os.makedirs(PDF_DIR, exist_ok=True)


def certificate_pdf(pupil_name, course_title, issued_date, enrolment_id):
    path = os.path.join(PDF_DIR, f"certificate_{enrolment_id}.pdf")
    w, h = landscape(A4)
    c = canvas.Canvas(path, pagesize=(w, h))

    c.setFillColor(CREAM)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    margin = 14 * mm
    c.setStrokeColor(TEAL)
    c.setLineWidth(3)
    c.rect(margin, margin, w - 2 * margin, h - 2 * margin, fill=0, stroke=1)
    c.setStrokeColor(AMBER)
    c.setLineWidth(1)
    c.rect(margin + 4 * mm, margin + 4 * mm, w - 2 * margin - 8 * mm,
           h - 2 * margin - 8 * mm, fill=0, stroke=1)

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 34 * mm, "PHIL")

    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w / 2, h - 52 * mm, "Certificate of Completion")

    c.setFillColor(INK)
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 68 * mm, "This certifies that")

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 82 * mm, pupil_name)

    c.setFillColor(INK)
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 96 * mm, "has completed the five-week course")

    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 110 * mm, course_title)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, margin + 16 * mm, f"Issued {issued_date}")
    c.drawCentredString(w / 2, margin + 10 * mm, "Phil, structured support, real growth.")

    c.showPage()
    c.save()
    return path


def _wrap(c, text, x, y, max_width, font="Helvetica", size=9, leading=12, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    lines = simpleSplit(text or "", font, size, max_width)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def session_record_pdf(record, enrolment, pupil_name, course_title, week_title, mentor_name):
    """
    record: sqlite3.Row from session_records
    """
    path = os.path.join(PDF_DIR, f"session_{record['id']}.pdf")
    w, h = A4
    c = canvas.Canvas(path, pagesize=A4)
    margin = 18 * mm
    x = margin
    y = h - margin

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Phil - Session Record")
    y -= 8 * mm

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Pupil: {pupil_name}    Course: {course_title}    Week: {week_title}")
    y -= 5 * mm
    c.drawString(x, y, f"Date: {record['date']}    Mentor: {mentor_name}")
    y -= 5 * mm
    c.setStrokeColor(BORDER)
    c.line(x, y, w - margin, y)
    y -= 8 * mm

    max_width = w - 2 * margin

    def section(label, text):
        nonlocal y
        c.setFillColor(TEAL_DARK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, label)
        y -= 5 * mm
        y = _wrap(c, text or "-", x, y, max_width)
        y -= 4 * mm

    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Mood rating: {record['mood_rating']}/5    Engagement rating: {record['engagement_rating']}/5")
    y -= 8 * mm

    section("What happened", record["what_happened"])
    section("Reflection / goal for the pupil", record["reflection_goal"])
    section("Mentor notes", record["mentor_notes"])
    section("Resources used", record["resources_used"])

    # Safeguarding block, always rendered, matching the mandatory-step convention
    # established across the project's other PDF exports.
    flagged = bool(record["safeguarding_flag"])
    box_h = 26 * mm
    if y - box_h < margin:
        c.showPage()
        y = h - margin
    c.setFillColor(HexColor("#FCEBEB") if flagged else HexColor("#E1F5EE"))
    c.rect(x, y - box_h, max_width, box_h, fill=1, stroke=0)
    c.setStrokeColor(RED if flagged else TEAL)
    c.setLineWidth(1.2)
    c.rect(x, y - box_h, max_width, box_h, fill=0, stroke=1)

    c.setFillColor(RED if flagged else TEAL_DARK)
    c.setFont("Helvetica-Bold", 11)
    label = "Safeguarding: flagged" if flagged else "Safeguarding: not flagged this session"
    c.drawString(x + 4 * mm, y - 7 * mm, label)

    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    note_y = _wrap(c, record["safeguarding_note"] or "-", x + 4 * mm, y - 12 * mm, max_width - 8 * mm, size=9)

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 7.5)
    disclaimer = ("This record is not a safeguarding report and Phil takes no action on it. "
                  "The mentor remains responsible for following their establishment's own "
                  "safeguarding procedure.")
    _wrap(c, disclaimer, x + 4 * mm, y - box_h + 3 * mm, max_width - 8 * mm, size=7.5, leading=9, color=MUTED)

    c.showPage()
    c.save()
    return path


def mentee_report_pdf(enrolment_id, pupil_name, course_title, mentor_name, start_date,
                       current_week, status, weeks, reflection=None):
    """
    weeks: list of dicts with keys week_number, title, objective, date (session date recorded)
    reflection: optional dict with pupil_engagement, course_effectiveness, recommended_next_steps
                (only pass this when the viewer is entitled to see it, per spec 7.5a/7.6)
    """
    path = os.path.join(PDF_DIR, f"mentee_report_{enrolment_id}.pdf")
    w, h = A4
    c = canvas.Canvas(path, pagesize=A4)
    margin = 18 * mm
    x = margin
    y = h - margin
    max_width = w - 2 * margin

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Phil - Individual Mentee Report")
    y -= 8 * mm

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Pupil: {pupil_name}    Course: {course_title}")
    y -= 5 * mm
    c.drawString(x, y, f"Mentor: {mentor_name}    Started: {start_date}    "
                        f"Status: {'Completed' if status == 'completed' else f'Week {current_week} of 5'}")
    y -= 6 * mm
    c.setStrokeColor(BORDER)
    c.line(x, y, w - margin, y)
    y -= 8 * mm

    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Coverage so far")
    y -= 7 * mm

    for wk in weeks:
        if y < margin + 20 * mm:
            c.showPage()
            y = h - margin
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(x, y, f"Week {wk['week_number']}: {wk['title']}  ({wk.get('date','')})")
        y -= 5 * mm
        y = _wrap(c, wk.get("objective", ""), x + 4 * mm, y, max_width - 4 * mm, size=9.5)
        y -= 4 * mm

    if not weeks:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(x, y, "No sessions recorded yet.")
        y -= 6 * mm

    if reflection:
        if y < margin + 40 * mm:
            c.showPage()
            y = h - margin
        y -= 4 * mm
        c.setStrokeColor(BORDER)
        c.line(x, y, w - margin, y)
        y -= 8 * mm
        c.setFillColor(AMBER)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, "Completion reflection")
        y -= 7 * mm
        for label, key in (("Pupil engagement", "pupil_engagement"),
                            ("Course effectiveness", "course_effectiveness"),
                            ("Recommended next steps", "recommended_next_steps")):
            c.setFillColor(TEAL_DARK)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x, y, label)
            y -= 5 * mm
            y = _wrap(c, reflection.get(key, "") or "-", x + 4 * mm, y, max_width - 4 * mm, size=9.5)
            y -= 4 * mm

    c.showPage()
    c.save()
    return path


def full_mentoring_report_pdf(title, entries, out_name):
    """
    entries: list of dicts, each with pupil_name, course_title, mentor_name, start_date,
             current_week, status, weeks (list), reflection (dict or None)
    One section per entry, all in a single PDF, for a whole-establishment bulk export
    or a single named pupil. Same restricted fields as the individual mentee report
    (Enrolment, Course, Week, SessionRecord.date only), plus CompletionReflection
    where the enrolment is completed, per spec section 7.7a.
    """
    path = os.path.join(PDF_DIR, f"{out_name}.pdf")
    w, h = A4
    c = canvas.Canvas(path, pagesize=A4)
    margin = 18 * mm
    max_width = w - 2 * margin
    x = margin
    y = h - margin

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 10 * mm

    if not entries:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 11)
        c.drawString(x, y, "No enrolments to report.")
        c.showPage()
        c.save()
        return path

    for entry in entries:
        if y < margin + 40 * mm:
            c.showPage()
            y = h - margin

        c.setStrokeColor(BORDER)
        c.line(x, y, w - margin, y)
        y -= 8 * mm

        c.setFillColor(TEAL_DARK)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(x, y, f"{entry['pupil_name']}  -  {entry['course_title']}")
        y -= 6 * mm

        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9.5)
        status_label = "Completed" if entry["status"] == "completed" else f"Week {entry['current_week']} of 5"
        c.drawString(x, y, f"Mentor: {entry['mentor_name']}    Started: {entry['start_date']}    Status: {status_label}")
        y -= 8 * mm

        for wk in entry["weeks"]:
            if y < margin + 20 * mm:
                c.showPage()
                y = h - margin
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x, y, f"Week {wk['week_number']}: {wk['title']}  ({wk.get('date','')})")
            y -= 5 * mm
            y = _wrap(c, wk.get("objective", ""), x + 4 * mm, y, max_width - 4 * mm, size=9)
            y -= 3 * mm

        if not entry["weeks"]:
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 9.5)
            c.drawString(x, y, "No sessions recorded yet.")
            y -= 6 * mm

        if entry.get("reflection"):
            if y < margin + 30 * mm:
                c.showPage()
                y = h - margin
            r = entry["reflection"]
            c.setFillColor(AMBER)
            c.setFont("Helvetica-Bold", 10.5)
            c.drawString(x, y, "Completion reflection")
            y -= 5 * mm
            for label, key in (("Engagement", "pupil_engagement"), ("Effectiveness", "course_effectiveness"),
                                ("Next steps", "recommended_next_steps")):
                c.setFillColor(TEAL_DARK)
                c.setFont("Helvetica-Bold", 9)
                c.drawString(x + 2, y, label + ":")
                y -= 4.5 * mm
                y = _wrap(c, r.get(key, "") or "-", x + 6 * mm, y, max_width - 6 * mm, size=9)
                y -= 3 * mm

        y -= 6 * mm

    c.showPage()
    c.save()
    return path


def caseload_report_xlsx(rows, show_mentor_col, out_name):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    path = os.path.join(PDF_DIR, f"{out_name}.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Case load"

    headers = ["Pupil", "Course"]
    if show_mentor_col:
        headers.append("Mentor")
    headers += ["Started", "Scheduled end", "Progress", "Certificate", "Reflection"]

    ws.append(headers)
    header_font = Font(bold=True, name="Arial")
    header_fill = PatternFill(start_color="F2EFE6", end_color="F2EFE6", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    for r in rows:
        row = [r["pupil"], r["course"]]
        if show_mentor_col:
            row.append(r.get("mentor", ""))
        row += [r["started"], r["scheduled_end"], r["progress"], r["certificate"], r["reflection"]]
        ws.append(row)

    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 12), 40)

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial")

    wb.save(path)
    return path


def caseload_report_pdf(title, rows, show_mentor_col, out_name):
    """
    rows: list of dicts with pupil, course, mentor (optional), started, scheduled_end,
          progress, certificate, reflection
    """
    path = os.path.join(PDF_DIR, f"{out_name}.pdf")
    w, h = landscape(A4)
    c = canvas.Canvas(path, pagesize=(w, h))
    margin = 14 * mm
    x = margin
    y = h - margin

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 10 * mm

    cols = ["Pupil", "Course"]
    if show_mentor_col:
        cols.append("Mentor")
    cols += ["Started", "Scheduled end", "Progress", "Certificate", "Reflection"]
    col_w = (w - 2 * margin) / len(cols)

    def draw_row(values, bold=False, fill=None):
        nonlocal y
        if fill:
            c.setFillColor(fill)
            c.rect(x, y - 6 * mm, w - 2 * margin, 7 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8.5)
        c.setFillColor(NAVY if bold else INK)
        for i, val in enumerate(values):
            c.drawString(x + i * col_w + 2, y - 4.5 * mm, str(val)[:28])
        y -= 7 * mm

    draw_row(cols, bold=True, fill=HexColor("#F2EFE6"))
    c.setStrokeColor(BORDER)
    c.line(x, y + 2, w - margin, y + 2)

    for r in rows:
        if y < margin + 10 * mm:
            c.showPage()
            y = h - margin
            draw_row(cols, bold=True, fill=HexColor("#F2EFE6"))
        values = [r["pupil"], r["course"]]
        if show_mentor_col:
            values.append(r.get("mentor", ""))
        values += [r["started"], r["scheduled_end"], r["progress"], r["certificate"], r["reflection"]]
        draw_row(values)

    c.showPage()
    c.save()
    return path


def _clean_pdf_text(text):
    if not text:
        return ""
    return text.replace("\uf0b7", "-").replace("\ue0b7", "-")


def resource_pack_pdf(course_num, course_title, items):
    """
    Generates the full downloadable resource pack for a course, containing
    every handout/card/template referenced by that course's sessions.
    course_num: two-digit string, e.g. "01"
    course_title: str
    items: list of {"name": str, "body": str}
    """
    path = os.path.join(PDF_DIR, f"resource_pack_{course_num}.pdf")
    w, h = A4
    c = canvas.Canvas(path, pagesize=A4)
    margin = 18 * mm
    max_width = w - margin * 2
    state = {"y": h - margin}

    def header():
        state["y"] = h - margin
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, state["y"], "Phil - Resource Pack")
        state["y"] -= 7 * mm
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        c.drawString(margin, state["y"], _clean_pdf_text(course_title))
        state["y"] -= 6 * mm
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.75)
        c.line(margin, state["y"], w - margin, state["y"])
        state["y"] -= 9 * mm

    def new_page():
        c.showPage()
        header()

    header()

    for item in items:
        if state["y"] < margin + 28 * mm:
            new_page()

        c.setFillColor(TEAL_DARK)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, state["y"], _clean_pdf_text(item.get("name", "")))
        state["y"] -= 7 * mm

        body = _clean_pdf_text(item.get("body", ""))
        for para in body.split("\n"):
            if state["y"] < margin + 14 * mm:
                new_page()
            state["y"] = _wrap(c, para, margin, state["y"], max_width, font="Helvetica", size=9.5, leading=13, color=INK)
        state["y"] -= 7 * mm

    c.showPage()
    c.save()
    return path
