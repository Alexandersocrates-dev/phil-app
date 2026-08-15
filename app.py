"""
Phil - main application.

Real, running web app covering the Phase 1 MVP from Phil_Technical_Build_Spec.docx
section 10: auth and roles, establishment/subscription setup with seat limits,
the 20 courses, pupil enrolment, session recording with the mandatory
safeguarding step and PDF export, progress tracking, automatic certificates,
and the parent/carer view.

Run with: python3 run.py, then open http://localhost:8000
"""

import datetime
import json
import os

import db
import auth as authlib
import billing
from framework import Router, Request, Response, render, redirect, pdf_response, make_wsgi_app
from pdf import generate as pdfgen

router = Router()
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

PILOT_DAYS = 21


# ---------------------------------------------------------------- helpers --

def current_user(request):
    conn = db.get_conn()
    try:
        token = request.cookie(authlib.SESSION_COOKIE)
        return authlib.user_from_token(conn, token)
    finally:
        conn.close()


def require(request, roles=None):
    """Returns the user row, or a redirect Response if not authorised."""
    user = current_user(request)
    if not user:
        return None, redirect("/login")
    if roles and user["role"] not in roles:
        return None, Response("Not authorised for this area.", status="403 Forbidden")
    if user["role"] != "phil_staff" and user["establishment_id"]:
        conn = db.get_conn()
        try:
            estab = conn.execute("SELECT status FROM establishments WHERE id=?",
                                  (user["establishment_id"],)).fetchone()
        finally:
            conn.close()
        if estab and estab["status"] == "suspended":
            return None, Response(
                "This establishment's access has been suspended. Contact Phil support to resolve this.",
                status="403 Forbidden")
    return user, None


def flash_from_query(request):
    kind = request.query.get("flash_kind", [None])[0]
    message = request.query.get("flash", [None])[0]
    if message:
        return {"kind": kind or "ok", "message": message}
    return None


def with_flash(location, message, kind="ok"):
    from urllib.parse import quote
    sep = "&" if "?" in location else "?"
    return redirect(f"{location}{sep}flash={quote(message)}&flash_kind={kind}")


def seats_used(conn, establishment_id):
    return conn.execute(
        "SELECT count(*) FROM users WHERE establishment_id=? AND role IN ('admin','mentor') AND status='active'",
        (establishment_id,),
    ).fetchone()[0]


def seat_limit(sub):
    return sub["included_seats"] + sub["extra_seats"]


def days_ago_label(iso_ts):
    """Human 'suspended X days ago' style label from an ISO timestamp, or None."""
    if not iso_ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
    except ValueError:
        return None
    days = (datetime.datetime.utcnow() - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


# -------------------------------------------------------------------- home --

def render_done(user, title, message, back_url, back_label="Back", accent="teal"):
    """Render a dedicated confirmation screen after a completed multi-step action."""
    return render("action_done.html", user=user, title=title, message=message,
                   back_url=back_url, back_label=back_label, accent=accent)


@router.get("/")
def home(request):
    user = current_user(request)
    if user:
        dest = {"admin": "/admin", "mentor": "/mentor", "parent_carer": "/parent",
                "phil_staff": "/staff"}.get(user["role"], "/courses")
        return redirect(dest)
    return render("home.html", user=None, flash=flash_from_query(request))


# --------------------------------------------------------------- auth/signup --

@router.get("/signup")
def signup_form(request):
    return render("signup.html", user=None, hide_nav_links=True, flash=flash_from_query(request))


@router.post("/signup")
def signup_submit(request):
    signup_type = request.field("signup_type", "pilot")
    establishment_name = request.field("establishment_name", "").strip()
    name = request.field("name", "").strip()
    email = request.field("email", "").strip().lower()
    password = request.field("password", "")

    if not name or not email or len(password) < 8:
        return with_flash("/signup", "Please fill in every field. Password needs at least 8 characters.", "error")

    conn = db.get_conn()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            return with_flash("/signup", "An account already exists with that email. Try signing in instead.", "error")

        now = db.now()

        if signup_type == "individual":
            estab_name = name or "Independent mentor"
            cur = conn.execute(
                "INSERT INTO establishments (type, name, status, created_at) VALUES (?,?,?,?)",
                ("individual", estab_name, "active", now),
            )
            establishment_id = cur.lastrowid
            conn.execute(
                """INSERT INTO subscriptions (establishment_id, plan_type, included_seats,
                   pupil_cap, status, payment_method, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (establishment_id, "individual", 1, None, "active", "card", now),
            )
            role = "mentor"
        else:
            if not establishment_name:
                return with_flash("/signup", "Establishment name is required.", "error")
            cur = conn.execute(
                "INSERT INTO establishments (type, name, status, created_at) VALUES (?,?,?,?)",
                ("school", establishment_name, "active", now),
            )
            establishment_id = cur.lastrowid
            if signup_type == "pilot":
                pilot_ends = (datetime.datetime.utcnow() + datetime.timedelta(days=PILOT_DAYS)).isoformat()
                conn.execute(
                    """INSERT INTO subscriptions (establishment_id, plan_type, included_seats,
                       pupil_cap, status, payment_method, pilot_ends_at, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (establishment_id, "pilot", 3, 10, "active", "none", pilot_ends, now),
                )
            else:
                conn.execute(
                    """INSERT INTO subscriptions (establishment_id, plan_type, included_seats,
                       pupil_cap, status, payment_method, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (establishment_id, "school", 15, None, "active", "invoice", now),
                )
            role = "admin"

        user_id = authlib.create_user(conn, establishment_id, role, name, email, password)
        token = authlib.create_session(conn, user_id)
        conn.commit()
    finally:
        conn.close()

    dest = "/mentor" if role == "mentor" else "/admin"
    response = with_flash(dest, "Welcome to Phil. Your account is ready.", "ok")
    response.set_cookie(authlib.SESSION_COOKIE, token, max_age=60 * 60 * 24 * 14)
    return response


@router.get("/login")
def login_form(request):
    return render("login.html", user=None, hide_nav_links=True, flash=flash_from_query(request))


@router.post("/login")
def login_submit(request):
    email = request.field("email", "").strip()
    password = request.field("password", "")
    conn = db.get_conn()
    try:
        user = authlib.authenticate(conn, email, password)
        if not user:
            return with_flash("/login", "Email or password not recognised.", "error")
        token = authlib.create_session(conn, user["id"])
        conn.commit()
    finally:
        conn.close()

    dest = {"admin": "/admin", "mentor": "/mentor", "parent_carer": "/parent",
            "phil_staff": "/staff"}.get(user["role"], "/courses")
    response = redirect(dest)
    response.set_cookie(authlib.SESSION_COOKIE, token, max_age=60 * 60 * 24 * 14)
    return response


@router.get("/logout")
def logout(request):
    conn = db.get_conn()
    try:
        token = request.cookie(authlib.SESSION_COOKIE)
        if token:
            authlib.destroy_session(conn, token)
            conn.commit()
    finally:
        conn.close()
    response = redirect("/")
    response.delete_cookie(authlib.SESSION_COOKIE)
    return response


# ------------------------------------------------------------------ courses --

@router.get("/courses")
def course_library(request):
    user = current_user(request)
    conn = db.get_conn()
    try:
        courses = conn.execute(
            "SELECT * FROM courses WHERE status='published' ORDER BY module_number"
        ).fetchall()
    finally:
        conn.close()
    return render("courses.html", user=user, courses=courses, flash=flash_from_query(request))


@router.get("/courses/<course_id>")
def course_detail(request):
    user = current_user(request)
    conn = db.get_conn()
    try:
        course = conn.execute("SELECT * FROM courses WHERE id=?", (request.params["course_id"],)).fetchone()
        weeks = conn.execute(
            "SELECT * FROM weeks WHERE course_id=? ORDER BY week_number", (request.params["course_id"],)
        ).fetchall()
    finally:
        conn.close()
    if not course:
        return Response("Course not found", status="404 Not Found")
    weeks = [dict(w, resources=json.loads(w["resources"] or "[]")) for w in weeks]
    return render("course_detail.html", user=user, course=course, weeks=weeks, flash=flash_from_query(request))


# ------------------------------------------------------------------- mentor --

@router.get("/mentor")
def mentor_home(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupils = conn.execute(
            """SELECT pupils.*,
                      (SELECT count(*) FROM enrolments WHERE enrolments.pupil_id = pupils.id AND enrolments.mentor_id = ? AND enrolments.status='active') as active_enrolments
               FROM pupils
               WHERE establishment_id=? AND status='active'
               AND id IN (SELECT pupil_id FROM enrolments WHERE mentor_id=?)
               ORDER BY surname""",
            (user["id"], user["establishment_id"], user["id"]),
        ).fetchall()
        enrolments = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title
               FROM enrolments
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
               WHERE enrolments.mentor_id=? ORDER BY enrolments.status, pupils.surname""",
            (user["id"],),
        ).fetchall()
        due_this_week = conn.execute(
            """SELECT count(*) FROM enrolments
               WHERE mentor_id=? AND status='active'
               AND id NOT IN (SELECT enrolment_id FROM session_records WHERE created_at >= date('now','-7 days'))""",
            (user["id"],),
        ).fetchone()[0]
    finally:
        conn.close()
    return render("mentor_home.html", user=user, pupils=pupils, enrolments=enrolments,
                  due_this_week=due_this_week,
                  flash=flash_from_query(request))


@router.get("/mentor/pupils/new")
def new_pupil_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    return render("pupil_new.html", user=user, flash=flash_from_query(request))


@router.post("/mentor/pupils/new")
def new_pupil_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    forename = request.field("forename", "").strip()
    surname = request.field("surname", "").strip()
    dob = request.field("date_of_birth", "").strip()
    year_group = request.field("year_group", "").strip()
    form_class = request.field("form_class", "").strip() or None

    if not (forename and surname and dob and year_group):
        return with_flash("/mentor/pupils/new", "Forename, surname, date of birth and year group are all required.", "error")

    conn = db.get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO pupils (establishment_id, forename, surname, date_of_birth,
               year_group, form_class, status, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user["establishment_id"], forename, surname, dob, year_group, form_class,
             "active", user["id"], db.now()),
        )
        pupil_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/enrol/{pupil_id}", f"{forename} {surname} added. Now enrol them on a course.", "ok")


@router.get("/mentor/pupils/<pupil_id>")
def pupil_profile(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (request.params["pupil_id"], user["establishment_id"])).fetchone()
        if not pupil:
            return Response("Pupil not found", status="404 Not Found")
        enrolments = conn.execute(
            """SELECT enrolments.*, courses.title as course_title, courses.id as course_id,
                      users.name as mentor_name
               FROM enrolments
               JOIN courses ON courses.id = enrolments.course_id
               JOIN users ON users.id = enrolments.mentor_id
               WHERE pupil_id=? ORDER BY enrolments.created_at DESC""",
            (pupil["id"],),
        ).fetchall()
        enrolment_data = []
        for e in enrolments:
            records = conn.execute(
                """SELECT session_records.*, weeks.title as week_title, weeks.week_number
                   FROM session_records JOIN weeks ON weeks.id = session_records.week_id
                   WHERE enrolment_id=? ORDER BY weeks.week_number""",
                (e["id"],),
            ).fetchall()
            cert = conn.execute("SELECT * FROM certificates WHERE enrolment_id=?", (e["id"],)).fetchone()
            reflection = conn.execute("SELECT * FROM completion_reflections WHERE enrolment_id=?", (e["id"],)).fetchone()
            next_planned = conn.execute(
                "SELECT planned_date FROM session_schedule WHERE enrolment_id=? AND week_number=?",
                (e["id"], e["current_week"] + 1),
            ).fetchone()
            enrolment_data.append({"enrolment": e, "records": records, "certificate": cert,
                                    "reflection": reflection,
                                    "next_planned": next_planned["planned_date"] if next_planned else None})
    finally:
        conn.close()
    return render("pupil_profile.html", user=user, pupil=pupil, enrolment_data=enrolment_data,
                  flash=flash_from_query(request))


@router.post("/mentor/pupils/<pupil_id>/archive")
def archive_pupil(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        conn.execute("UPDATE pupils SET status='archived' WHERE id=? AND establishment_id=?",
                      (request.params["pupil_id"], user["establishment_id"]))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Pupil archived", "Their records are kept and they can be reactivated at any time.", "/mentor")


@router.post("/mentor/pupils/<pupil_id>/reactivate")
def reactivate_pupil(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        conn.execute("UPDATE pupils SET status='active' WHERE id=? AND establishment_id=?",
                      (request.params["pupil_id"], user["establishment_id"]))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Pupil reactivated", "They're active again and back on their mentor's list.", f"/mentor/pupils/{request.params['pupil_id']}", back_label="View pupil")


@router.get("/admin/pupils")
def admin_pupils(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    status_filter = request.query.get("status", ["active"])[0]
    conn = db.get_conn()
    try:
        pupils = conn.execute(
            "SELECT * FROM pupils WHERE establishment_id=? AND status=? ORDER BY surname, forename",
            (user["establishment_id"], status_filter),
        ).fetchall()
        pupil_data = []
        for p in pupils:
            enrolments = conn.execute(
                """SELECT enrolments.status, courses.title as course_title, users.name as mentor_name
                   FROM enrolments
                   JOIN courses ON courses.id = enrolments.course_id
                   JOIN users ON users.id = enrolments.mentor_id
                   WHERE pupil_id=? ORDER BY enrolments.created_at DESC""",
                (p["id"],),
            ).fetchall()
            pupil_data.append({"pupil": p, "enrolments": enrolments})
    finally:
        conn.close()
    return render("admin_pupils.html", user=user, pupil_data=pupil_data, status_filter=status_filter,
                  flash=flash_from_query(request))


@router.get("/admin/enrolments/<enrolment_id>/reassign")
def admin_reassign_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, pupils.establishment_id,
                      courses.title as course_title, users.name as mentor_name
               FROM enrolments
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
               JOIN users ON users.id = enrolments.mentor_id
               WHERE enrolments.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not found", status="404 Not Found")
        mentors = conn.execute(
            """SELECT id, name FROM users WHERE establishment_id=? AND role IN ('admin','mentor')
               AND status='active' AND id != ? ORDER BY name""",
            (user["establishment_id"], enrolment["mentor_id"]),
        ).fetchall()
    finally:
        conn.close()
    return render("enrolment_reassign.html", user=user, enrolment=enrolment, mentors=mentors,
                  flash=flash_from_query(request))


@router.post("/admin/enrolments/<enrolment_id>/reassign")
def admin_reassign_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    new_mentor_id = request.field("mentor_id")
    if not new_mentor_id:
        return with_flash(f"/admin/enrolments/{request.params['enrolment_id']}/reassign",
                           "Choose a mentor to reassign to.", "error")
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, pupils.establishment_id
               FROM enrolments JOIN pupils ON pupils.id = enrolments.pupil_id
               WHERE enrolments.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not found", status="404 Not Found")
        new_mentor = conn.execute(
            "SELECT * FROM users WHERE id=? AND establishment_id=? AND role IN ('admin','mentor') AND status='active'",
            (new_mentor_id, user["establishment_id"]),
        ).fetchone()
        if not new_mentor:
            return with_flash(f"/admin/enrolments/{enrolment['id']}/reassign",
                               "That mentor could not be found.", "error")
        conn.execute("UPDATE enrolments SET mentor_id=? WHERE id=?", (new_mentor_id, enrolment["id"]))
        db.log_action(conn, user["id"], "enrolment_reassigned", "enrolment", enrolment["id"],
                      f"{enrolment['forename']} {enrolment['surname']}'s enrolment moved to {new_mentor['name']}")
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Case load reassigned",
                        f"{enrolment['forename']} {enrolment['surname']} is now with {new_mentor['name']}.",
                        f"/mentor/pupils/{enrolment['pupil_id']}", back_label="View pupil")


@router.get("/admin/pupils/<pupil_id>/delete")
def admin_pupil_delete_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (request.params["pupil_id"], user["establishment_id"])).fetchone()
        if not pupil:
            return Response("Not found", status="404 Not Found")
    finally:
        conn.close()
    return render("pupil_delete_confirm.html", user=user, pupil=pupil, flash=flash_from_query(request))


@router.post("/admin/pupils/<pupil_id>/delete")
def admin_pupil_delete_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (request.params["pupil_id"], user["establishment_id"])).fetchone()
        if not pupil:
            return Response("Not found", status="404 Not Found")
        expected = f"{pupil['forename']} {pupil['surname']}"
        typed = request.field("confirm_name", "").strip()
        if typed != expected:
            return with_flash(f"/admin/pupils/{pupil['id']}/delete",
                               "The typed name did not match. Nothing was deleted.", "error")
        enrolment_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM enrolments WHERE pupil_id=?", (pupil["id"],)).fetchall()]
        for eid in enrolment_ids:
            conn.execute("DELETE FROM session_records WHERE enrolment_id=?", (eid,))
            conn.execute("DELETE FROM session_schedule WHERE enrolment_id=?", (eid,))
            conn.execute("DELETE FROM certificates WHERE enrolment_id=?", (eid,))
            conn.execute("DELETE FROM completion_reflections WHERE enrolment_id=?", (eid,))
        conn.execute("DELETE FROM enrolments WHERE pupil_id=?", (pupil["id"],))
        conn.execute("DELETE FROM pupil_parent_links WHERE pupil_id=?", (pupil["id"],))
        conn.execute("DELETE FROM pupils WHERE id=?", (pupil["id"],))
        db.log_action(conn, user["id"], "pupil_permanently_deleted", "pupil", pupil["id"], expected)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Record deleted", f"{expected}'s record has been permanently deleted.", "/admin/pupils", back_label="Back to pupils")


@router.get("/admin/mentors/<mentor_id>/remove")
def admin_mentor_remove_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        mentor = conn.execute(
            "SELECT * FROM users WHERE id=? AND establishment_id=? AND role='mentor' AND status='active'",
            (request.params["mentor_id"], user["establishment_id"]),
        ).fetchone()
        if not mentor:
            return Response("Not found", status="404 Not Found")
        active_count = conn.execute(
            "SELECT count(*) c FROM enrolments WHERE mentor_id=? AND status='active'", (mentor["id"],)
        ).fetchone()["c"]
        other_mentors = conn.execute(
            """SELECT id, name FROM users WHERE establishment_id=? AND role IN ('admin','mentor')
               AND status='active' AND id != ? ORDER BY name""",
            (user["establishment_id"], mentor["id"]),
        ).fetchall()
    finally:
        conn.close()
    return render("mentor_remove_confirm.html", user=user, mentor=mentor, active_count=active_count,
                  other_mentors=other_mentors, flash=flash_from_query(request))


@router.post("/admin/mentors/<mentor_id>/remove")
def admin_mentor_remove_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        mentor = conn.execute(
            "SELECT * FROM users WHERE id=? AND establishment_id=? AND role='mentor' AND status='active'",
            (request.params["mentor_id"], user["establishment_id"]),
        ).fetchone()
        if not mentor:
            return Response("Not found", status="404 Not Found")
        active_count = conn.execute(
            "SELECT count(*) c FROM enrolments WHERE mentor_id=? AND status='active'", (mentor["id"],)
        ).fetchone()["c"]
        reassign_to = request.field("reassign_to")
        new_mentor = None
        if active_count > 0:
            if not reassign_to:
                return with_flash(f"/admin/mentors/{mentor['id']}/remove",
                                   "Choose who should take over their active case load.", "error")
            new_mentor = conn.execute(
                "SELECT * FROM users WHERE id=? AND establishment_id=? AND status='active'",
                (reassign_to, user["establishment_id"]),
            ).fetchone()
            if not new_mentor:
                return with_flash(f"/admin/mentors/{mentor['id']}/remove",
                                   "That mentor could not be found.", "error")
        typed = request.field("confirm_name", "").strip()
        if typed != mentor["name"]:
            return with_flash(f"/admin/mentors/{mentor['id']}/remove",
                               "The typed name did not match. Nothing was changed.", "error")
        if active_count > 0:
            conn.execute("UPDATE enrolments SET mentor_id=? WHERE mentor_id=? AND status='active'",
                         (reassign_to, mentor["id"]))
        conn.execute("UPDATE users SET status='removed' WHERE id=?", (mentor["id"],))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (mentor["id"],))
        db.log_action(conn, user["id"], "mentor_removed", "user", mentor["id"],
                      f"{mentor['name']} removed" + (f", case load moved to {new_mentor['name']}" if active_count > 0 else ""))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Mentor removed", f"{mentor['name']} has lost access immediately. Every pupil record and past session they wrote stays exactly as it is.", "/admin", back_label="Admin home")


@router.get("/mentor/pupils/<pupil_id>/link-parent")
def link_parent_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (request.params["pupil_id"], user["establishment_id"])).fetchone()
        if not pupil:
            return Response("Pupil not found", status="404 Not Found")
        links = conn.execute(
            """SELECT users.name, users.email, pupil_parent_links.relationship
               FROM pupil_parent_links JOIN users ON users.id = pupil_parent_links.parent_user_id
               WHERE pupil_id=?""",
            (pupil["id"],),
        ).fetchall()
        pending_requests = conn.execute(
            """SELECT parent_access_requests.*, users.name as requested_by_name
               FROM parent_access_requests JOIN users ON users.id = parent_access_requests.requested_by
               WHERE parent_access_requests.pupil_id=? AND parent_access_requests.status='pending'
               ORDER BY parent_access_requests.created_at DESC""",
            (pupil["id"],),
        ).fetchall()
    finally:
        conn.close()
    return render("link_parent.html", user=user, pupil=pupil, links=links,
                  pending_requests=pending_requests, flash=flash_from_query(request))


@router.post("/mentor/pupils/<pupil_id>/link-parent")
def link_parent_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    pupil_id = request.params["pupil_id"]
    name = request.field("name", "").strip()
    email = request.field("email", "").strip().lower()
    relationship = request.field("relationship", "").strip() or None

    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (pupil_id, user["establishment_id"])).fetchone()
        if not pupil:
            return Response("Pupil not found", status="404 Not Found")

        if user["role"] == "mentor":
            # Mentors can only flag that a parent/carer should get access. An
            # admin has to review and grant it, see the approve/decline routes
            # below, this never creates an account or a link by itself.
            note = request.field("note", "").strip() or None
            if not name or not email:
                return with_flash(f"/mentor/pupils/{pupil_id}/link-parent",
                                   "Fill in the parent/carer's name and email.", "error")
            conn.execute(
                """INSERT INTO parent_access_requests
                   (pupil_id, establishment_id, requested_by, parent_name, parent_email,
                    relationship, note, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pupil_id, user["establishment_id"], user["id"], name, email,
                 relationship, note, "pending", db.now()),
            )
            conn.execute(
                """INSERT INTO notifications (type, recipient, establishment_id, payload, status, sent_at)
                   VALUES (?,?,?,?,?,?)""",
                ("parent_access_requested", "admin", user["establishment_id"],
                 f"{user['name']} requested parent/carer access for {pupil['forename']} {pupil['surname']} "
                 f"(parent/carer: {name}). Review it from the pupil's page.",
                 "unread", db.now()),
            )
            conn.commit()
            return with_flash(f"/mentor/pupils/{pupil_id}",
                               "Request sent. An admin needs to review and approve it before "
                               f"{name} can sign in.", "ok")

        # Admin: grants access directly, same as before.
        password = request.field("password", "")
        if not name or not email or len(password) < 8:
            return with_flash(f"/mentor/pupils/{pupil_id}/link-parent",
                               "Fill in every field. Password needs at least 8 characters.", "error")

        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            parent_user_id = existing["id"]
            already_linked = conn.execute(
                "SELECT id FROM pupil_parent_links WHERE pupil_id=? AND parent_user_id=?",
                (pupil_id, parent_user_id),
            ).fetchone()
            if already_linked:
                return with_flash(f"/mentor/pupils/{pupil_id}/link-parent",
                                   "That parent/carer is already linked to this pupil.", "error")
        else:
            parent_user_id = authlib.create_user(conn, None, "parent_carer", name, email, password)

        conn.execute(
            """INSERT INTO pupil_parent_links (pupil_id, parent_user_id, relationship, verified_by, created_at)
               VALUES (?,?,?,?,?)""",
            (pupil_id, parent_user_id, relationship, user["id"], db.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", f"{name} linked as a parent/carer.", "ok")


@router.post("/admin/parent-requests/<request_id>/approve")
def parent_request_approve(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    request_id = request.params["request_id"]
    password = request.field("password", "")

    conn = db.get_conn()
    try:
        req = conn.execute(
            "SELECT * FROM parent_access_requests WHERE id=? AND establishment_id=? AND status='pending'",
            (request_id, user["establishment_id"]),
        ).fetchone()
        if not req:
            return Response("Request not found", status="404 Not Found")

        pupil = conn.execute("SELECT * FROM pupils WHERE id=?", (req["pupil_id"],)).fetchone()

        existing = conn.execute("SELECT id FROM users WHERE email=?", (req["parent_email"],)).fetchone()
        if existing:
            parent_user_id = existing["id"]
        else:
            if len(password) < 8:
                return with_flash(f"/mentor/pupils/{req['pupil_id']}/link-parent",
                                   "Set a temporary password of at least 8 characters to approve this request.",
                                   "error")
            parent_user_id = authlib.create_user(conn, None, "parent_carer",
                                                  req["parent_name"], req["parent_email"], password)

        already_linked = conn.execute(
            "SELECT id FROM pupil_parent_links WHERE pupil_id=? AND parent_user_id=?",
            (req["pupil_id"], parent_user_id),
        ).fetchone()
        if not already_linked:
            conn.execute(
                """INSERT INTO pupil_parent_links (pupil_id, parent_user_id, relationship, verified_by, created_at)
                   VALUES (?,?,?,?,?)""",
                (req["pupil_id"], parent_user_id, req["relationship"], user["id"], db.now()),
            )

        conn.execute(
            "UPDATE parent_access_requests SET status='approved', resolved_by=?, resolved_at=? WHERE id=?",
            (user["id"], db.now(), request_id),
        )
        db.log_action(conn, user["id"], "parent_access_approved", "pupil", req["pupil_id"],
                      f"{req['parent_name']} granted parent/carer access to {pupil['forename']} {pupil['surname']}")
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{req['pupil_id']}",
                       f"{req['parent_name']} has been granted parent/carer access.", "ok")


@router.post("/admin/parent-requests/<request_id>/decline")
def parent_request_decline(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    request_id = request.params["request_id"]

    conn = db.get_conn()
    try:
        req = conn.execute(
            "SELECT * FROM parent_access_requests WHERE id=? AND establishment_id=? AND status='pending'",
            (request_id, user["establishment_id"]),
        ).fetchone()
        if not req:
            return Response("Request not found", status="404 Not Found")

        conn.execute(
            "UPDATE parent_access_requests SET status='declined', resolved_by=?, resolved_at=? WHERE id=?",
            (user["id"], db.now(), request_id),
        )
        db.log_action(conn, user["id"], "parent_access_declined", "pupil", req["pupil_id"],
                      f"Declined parent/carer access request for {req['parent_name']}")
        conn.commit()
        pupil_id = req["pupil_id"]
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", "Request declined.", "ok")


@router.get("/mentor/enrol/<pupil_id>")
def enrol_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute("SELECT * FROM pupils WHERE id=? AND establishment_id=?",
                              (request.params["pupil_id"], user["establishment_id"])).fetchone()
        courses = conn.execute("SELECT * FROM courses WHERE status='published' ORDER BY module_number").fetchall()
    finally:
        conn.close()
    if not pupil:
        return Response("Pupil not found", status="404 Not Found")
    return render("enrol.html", user=user, pupil=pupil, courses=courses, flash=flash_from_query(request))


@router.post("/mentor/enrol/<pupil_id>")
def enrol_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    pupil_id = request.params["pupil_id"]
    course_id = request.field("course_id")
    parent_access_enabled = 1 if request.field("parent_access_enabled") == "on" else 0

    conn = db.get_conn()
    try:
        sub = conn.execute(
            """SELECT subscriptions.* FROM subscriptions WHERE establishment_id=?""",
            (user["establishment_id"],),
        ).fetchone()
        if sub and sub["pupil_cap"]:
            enrolled_pupils = conn.execute(
                "SELECT count(DISTINCT pupil_id) FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id WHERE pupils.establishment_id=?",
                (user["establishment_id"],),
            ).fetchone()[0]
            already_this_pupil = conn.execute(
                "SELECT count(*) FROM enrolments WHERE pupil_id=?", (pupil_id,)
            ).fetchone()[0]
            if enrolled_pupils >= sub["pupil_cap"] and already_this_pupil == 0:
                return with_flash(f"/mentor/pupils/{pupil_id}",
                                   f"Pilot pupil limit reached ({sub['pupil_cap']}). Convert to a paid plan to enrol more pupils.",
                                   "error")

        cur = conn.execute(
            """INSERT INTO enrolments (pupil_id, course_id, mentor_id, start_date, status,
               current_week, parent_access_enabled, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pupil_id, course_id, user["id"], datetime.date.today().isoformat(), "active",
             0, parent_access_enabled, db.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", "Enrolled. The first session can be recorded whenever it happens.", "ok")


@router.get("/mentor/session/<enrolment_id>")
def session_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, pupils.id as pupil_id,
            courses.title as course_title, courses.module_number as course_module_number
            FROM enrolments
            JOIN pupils ON pupils.id = enrolments.pupil_id
            JOIN courses ON courses.id = enrolments.course_id
            WHERE enrolments.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        if not enrolment:
            return Response("Enrolment not found", status="404 Not Found")
        next_week_number = enrolment["current_week"] + 1
        all_weeks = conn.execute(
            "SELECT * FROM weeks WHERE course_id=? ORDER BY week_number",
            (enrolment["course_id"],),
        ).fetchall()
        week = next((w for w in all_weeks if w["week_number"] == next_week_number), None)
        completed_records = conn.execute(
            """SELECT session_records.*, weeks.week_number as wn, weeks.title as week_title,
            users.name as recorder_name
            FROM session_records
            JOIN weeks ON weeks.id = session_records.week_id
            JOIN users ON users.id = session_records.recorded_by
            WHERE session_records.enrolment_id=? ORDER BY weeks.week_number""",
            (enrolment["id"],),
        ).fetchall()
        draft = conn.execute(
            "SELECT * FROM session_drafts WHERE enrolment_id=? AND week_number=?",
            (enrolment["id"], next_week_number),
        ).fetchone()
    finally:
        conn.close()
    if week:
        week = dict(week, resources=json.loads(week["resources"] or "[]"))
    prev_record = completed_records[-1] if completed_records else None
    progress = [{"number": n, "status": "done" if n < next_week_number else ("current" if n == next_week_number else "locked")} for n in range(1, 6)]
    upcoming_weeks = [w for w in all_weeks if w["week_number"] > next_week_number]
    return render("session_form.html", user=user, enrolment=enrolment, week=week,
                  next_week_number=next_week_number, completed_records=completed_records,
                  prev_record=prev_record, draft=draft, progress=progress,
                  upcoming_weeks=upcoming_weeks, flash=flash_from_query(request))

@router.post("/mentor/session/<enrolment_id>/autosave")
def session_autosave(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]
    field_name = request.field("field", "")
    value = request.field("value", "")
    allowed = {"checkin_note", "input_note", "activity_note", "reflect_note", "next_session_note"}
    if field_name not in allowed:
        return Response(json.dumps({"ok": False, "error": "bad field"}), status="400 Bad Request", content_type="application/json")
    conn = db.get_conn()
    try:
        enrolment = conn.execute("SELECT current_week FROM enrolments WHERE id=?", (enrolment_id,)).fetchone()
        if not enrolment:
            return Response(json.dumps({"ok": False}), status="404 Not Found", content_type="application/json")
        week_number = enrolment["current_week"] + 1
        existing = conn.execute(
            "SELECT id FROM session_drafts WHERE enrolment_id=? AND week_number=?",
            (enrolment_id, week_number),
        ).fetchone()
        if existing:
            conn.execute(f"UPDATE session_drafts SET {field_name}=?, updated_at=? WHERE id=?",
                         (value, db.now(), existing["id"]))
        else:
            conn.execute(
                f"INSERT INTO session_drafts (enrolment_id, week_number, {field_name}, updated_at) VALUES (?,?,?,?)",
                (enrolment_id, week_number, value, db.now()),
            )
        conn.commit()
    finally:
        conn.close()
    return Response(json.dumps({"ok": True}), content_type="application/json")

@router.post("/mentor/session/<enrolment_id>")
def session_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]
    safeguarding_flag = 1 if request.field("safeguarding_flag") == "yes" else 0
    safeguarding_note = request.field("safeguarding_note", "").strip()

    if not safeguarding_note:
        return with_flash(f"/mentor/session/{enrolment_id}",
            "The safeguarding note is mandatory, even to record 'no concerns this session'.", "error")

    checkin_note = request.field("checkin_note", "").strip()
    input_note = request.field("input_note", "").strip()
    activity_note = request.field("activity_note", "").strip()
    reflect_note = request.field("reflect_note", "").strip()
    next_session_note = request.field("next_session_note", "").strip()
    what_happened_parts = []
    if checkin_note:
        what_happened_parts.append(f"Check-in: {checkin_note}")
    if input_note:
        what_happened_parts.append(f"Input: {input_note}")
    if activity_note:
        what_happened_parts.append(f"Activity: {activity_note}")
    what_happened = "\n\n".join(what_happened_parts)

    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title
            FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id
            JOIN courses ON courses.id=enrolments.course_id WHERE enrolments.id=?""",
            (enrolment_id,),
        ).fetchone()
        next_week_number = enrolment["current_week"] + 1
        week = conn.execute("SELECT * FROM weeks WHERE course_id=? AND week_number=?",
                             (enrolment["course_id"], next_week_number)).fetchone()

        cur = conn.execute(
            """INSERT INTO session_records (enrolment_id, week_id, date, mood_rating,
            engagement_rating, safeguarding_flag, safeguarding_note, what_happened,
            reflection_goal, mentor_notes, resources_used, recorded_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (enrolment_id, week["id"], datetime.date.today().isoformat(),
             request.field("mood_rating") or None, request.field("engagement_rating") or None,
             safeguarding_flag, safeguarding_note, what_happened,
             reflect_note, next_session_note,
             request.field("resources_used", ""), user["id"], db.now()),
        )
        record_id = cur.lastrowid

        pupil_name = f"{enrolment['forename']} {enrolment['surname']}"
        mentor_name = user["name"]
        record = conn.execute("SELECT * FROM session_records WHERE id=?", (record_id,)).fetchone()
        pdf_path = pdfgen.session_record_pdf(record, enrolment, pupil_name, enrolment["course_title"],
                                              week["title"], mentor_name)
        conn.execute("UPDATE session_records SET pdf_path=? WHERE id=?", (pdf_path, record_id))

        new_current_week = next_week_number
        new_status = "completed" if new_current_week >= 5 else "active"
        conn.execute("UPDATE enrolments SET current_week=?, status=? WHERE id=?",
            (new_current_week, new_status, enrolment_id))

        conn.execute("DELETE FROM session_drafts WHERE enrolment_id=? AND week_number=?",
                     (enrolment_id, next_week_number))

        message = f"Week {next_week_number} session recorded."
        if new_status == "completed":
            issued = datetime.date.today().isoformat()
            cert_path = pdfgen.certificate_pdf(pupil_name, enrolment["course_title"], issued, enrolment_id)
            conn.execute(
                "INSERT INTO certificates (enrolment_id, issued_date, pdf_path) VALUES (?,?,?)",
                (enrolment_id, issued, cert_path),
            )
            message = f"Course complete. {pupil_name}'s certificate has been issued."

        conn.commit()
    finally:
        conn.close()

    return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}", message, "ok")

@router.get("/mentor/schedule/<enrolment_id>")
def schedule_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title
               FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id
               JOIN courses ON courses.id=enrolments.course_id WHERE enrolments.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        if not enrolment:
            return Response("Enrolment not found", status="404 Not Found")
        rows = conn.execute("SELECT week_number, planned_date FROM session_schedule WHERE enrolment_id=?",
                             (enrolment["id"],)).fetchall()
        planned = {r["week_number"]: r["planned_date"] for r in rows}
        if not planned:
            start = datetime.date.fromisoformat(enrolment["start_date"])
            for i in range(1, 6):
                planned[i] = (start + datetime.timedelta(days=7 * (i - 1))).isoformat()
    finally:
        conn.close()
    return render("schedule_form.html", user=user, enrolment=enrolment, planned=planned,
                  flash=flash_from_query(request))


@router.post("/mentor/schedule/<enrolment_id>")
def schedule_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]
    conn = db.get_conn()
    try:
        enrolment = conn.execute("SELECT pupil_id FROM enrolments WHERE id=?", (enrolment_id,)).fetchone()
        conn.execute("DELETE FROM session_schedule WHERE enrolment_id=?", (enrolment_id,))
        for i in range(1, 6):
            date_val = request.field(f"week{i}_date", "").strip()
            if date_val:
                conn.execute(
                    "INSERT INTO session_schedule (enrolment_id, week_number, planned_date) VALUES (?,?,?)",
                    (enrolment_id, i, date_val),
                )
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}", "Planned dates saved.", "ok")


@router.get("/mentor/reflection/<enrolment_id>")
def reflection_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title
               FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id
               JOIN courses ON courses.id=enrolments.course_id WHERE enrolments.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        reflection = conn.execute("SELECT * FROM completion_reflections WHERE enrolment_id=?",
                                   (request.params["enrolment_id"],)).fetchone()
    finally:
        conn.close()
    return render("reflection_form.html", user=user, enrolment=enrolment, reflection=reflection,
                  flash=flash_from_query(request))


@router.post("/mentor/reflection/<enrolment_id>")
def reflection_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]
    pupil_engagement = request.field("pupil_engagement", "")
    course_effectiveness = request.field("course_effectiveness", "")
    recommended_next_steps = request.field("recommended_next_steps", "")

    conn = db.get_conn()
    try:
        existing = conn.execute("SELECT id FROM completion_reflections WHERE enrolment_id=?", (enrolment_id,)).fetchone()
        now = db.now()
        if existing:
            conn.execute(
                """UPDATE completion_reflections SET pupil_engagement=?, course_effectiveness=?,
                   recommended_next_steps=?, updated_at=? WHERE enrolment_id=?""",
                (pupil_engagement, course_effectiveness, recommended_next_steps, now, enrolment_id),
            )
        else:
            conn.execute(
                """INSERT INTO completion_reflections (enrolment_id, pupil_engagement,
                   course_effectiveness, recommended_next_steps, completed_by, completed_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (enrolment_id, pupil_engagement, course_effectiveness, recommended_next_steps,
                 user["id"], now, now),
            )
        pupil_id = conn.execute("SELECT pupil_id FROM enrolments WHERE id=?", (enrolment_id,)).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", "Reflection saved.", "ok")


# -------------------------------------------------------------------- admin --

@router.get("/admin")
def admin_home(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        establishment = conn.execute("SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)).fetchone()
        sub = conn.execute("SELECT * FROM subscriptions WHERE establishment_id=? ORDER BY id DESC LIMIT 1",
                            (user["establishment_id"],)).fetchone()
        mentors = conn.execute(
            "SELECT * FROM users WHERE establishment_id=? AND role IN ('admin','mentor') AND status='active' ORDER BY role, name",
            (user["establishment_id"],),
        ).fetchall()
        pupils = conn.execute(
            "SELECT * FROM pupils WHERE establishment_id=? AND status='active' ORDER BY surname",
            (user["establishment_id"],),
        ).fetchall()
        used = seats_used(conn, user["establishment_id"])

        if sub and sub["plan_type"] == "pilot" and sub["pilot_ends_at"]:
            days_left = (datetime.date.fromisoformat(sub["pilot_ends_at"][:10]) - datetime.date.today()).days
            if days_left <= 5:
                existing_note = conn.execute(
                    "SELECT id FROM notifications WHERE type='pilot_ending' AND establishment_id=? AND status='unread'",
                    (user["establishment_id"],),
                ).fetchone()
                if not existing_note:
                    conn.execute(
                        """INSERT INTO notifications (type, recipient, establishment_id, payload, status, sent_at)
                           VALUES (?,?,?,?,?,?)""",
                        ("pilot_ending", "admin", user["establishment_id"],
                         f"Your free pilot ends in {max(days_left, 0)} day(s). Convert to a paid plan any time, nothing recorded is lost.",
                         "unread", db.now()),
                    )
                    conn.commit()

        admin_notes = conn.execute(
            "SELECT * FROM notifications WHERE recipient='admin' AND establishment_id=? AND status='unread' ORDER BY sent_at DESC",
            (user["establishment_id"],),
        ).fetchall()

        sessions = conn.execute(
            """SELECT session_records.*, pupils.forename, pupils.surname, courses.title as course_title,
                      weeks.week_number, users.name as mentor_name
               FROM session_records
               JOIN enrolments ON enrolments.id = session_records.enrolment_id
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
               JOIN weeks ON weeks.id = session_records.week_id
               JOIN users ON users.id = session_records.recorded_by
               WHERE pupils.establishment_id=?
               ORDER BY session_records.created_at DESC LIMIT 20""",
            (user["establishment_id"],),
        ).fetchall()
    finally:
        conn.close()
    return render("admin_home.html", user=user, establishment=establishment, sub=sub, mentors=mentors,
                  pupils=pupils, used=used, limit=seat_limit(sub) if sub else 0, sessions=sessions,
                  admin_notes=admin_notes,
                  stripe_configured=billing.is_configured(), flash=flash_from_query(request))


@router.get("/admin/mentors/new")
def new_mentor_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    return render("mentor_new.html", user=user, flash=flash_from_query(request))


@router.post("/admin/mentors/new")
def new_mentor_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    name = request.field("name", "").strip()
    email = request.field("email", "").strip().lower()
    password = request.field("password", "")

    if not name or not email or len(password) < 8:
        return with_flash("/admin/mentors/new", "Fill in every field. Password needs at least 8 characters.", "error")

    conn = db.get_conn()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            return with_flash("/admin/mentors/new", "That email is already registered.", "error")

        sub = conn.execute("SELECT * FROM subscriptions WHERE establishment_id=? ORDER BY id DESC LIMIT 1",
                            (user["establishment_id"],)).fetchone()
        used = seats_used(conn, user["establishment_id"])
        if sub and used >= seat_limit(sub):
            estab = conn.execute("SELECT name FROM establishments WHERE id=?", (user["establishment_id"],)).fetchone()
            conn.execute(
                """INSERT INTO seat_alerts (establishment_id, requested_by, requested_extra_seats,
                   status, created_at) VALUES (?,?,?,?,?)""",
                (user["establishment_id"], user["id"], 1, "pending", db.now()),
            )
            conn.execute(
                """INSERT INTO notifications (type, recipient, establishment_id, payload, status, sent_at)
                   VALUES (?,?,?,?,?,?)""",
                ("seat_alert", "phil_staff", user["establishment_id"],
                 f"{estab['name']} has reached its seat limit and requested an extra seat.", "unread", db.now()),
            )
            conn.commit()
            return with_flash("/admin", "Seat limit reached. We've logged a request for an extra seat, "
                                          "someone from Phil will be in touch.", "error")

        authlib.create_user(conn, user["establishment_id"], "mentor", name, email, password)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Mentor added", f"{name} can now sign in and start mentoring.", "/admin", back_label="Admin home")


@router.get("/admin/session/<record_id>")
def admin_view_session(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        record = conn.execute(
            """SELECT session_records.*, pupils.forename, pupils.surname, courses.title as course_title,
                      weeks.title as week_title, weeks.week_number, users.name as mentor_name,
                      pupils.establishment_id as pupil_establishment_id
               FROM session_records
               JOIN enrolments ON enrolments.id = session_records.enrolment_id
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
               JOIN weeks ON weeks.id = session_records.week_id
               JOIN users ON users.id = session_records.recorded_by
               WHERE session_records.id=?""",
            (request.params["record_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not record or record["pupil_establishment_id"] != user["establishment_id"]:
        return Response("Not found", status="404 Not Found")
    return render("session_view.html", user=user, record=record, flash=flash_from_query(request))


@router.get("/admin/courses")
def admin_courses(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        courses = conn.execute("SELECT * FROM courses ORDER BY module_number").fetchall()
    finally:
        conn.close()
    return render("admin_courses.html", user=user, courses=courses, flash=flash_from_query(request))


def _week_field(request, i, name):
    return request.field(f"week{i}_{name}", "")


def _save_weeks(conn, course_id, request):
    conn.execute("DELETE FROM weeks WHERE course_id=?", (course_id,))
    for i in range(1, 6):
        resources_raw = _week_field(request, i, "resources")
        resources = [r.strip() for r in resources_raw.split(",") if r.strip()]
        conn.execute(
            """INSERT INTO weeks (course_id, week_number, title, objective, checkin,
               input_content, activity, reflect, lookfor, resources, home_activity)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (course_id, i, _week_field(request, i, "title") or f"Week {i}",
             _week_field(request, i, "objective"), _week_field(request, i, "checkin"),
             _week_field(request, i, "input"), _week_field(request, i, "activity"),
             _week_field(request, i, "reflect"), _week_field(request, i, "lookfor"),
             json.dumps(resources), _week_field(request, i, "home")),
        )


@router.get("/admin/courses/new")
def new_course_form(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    return render("course_builder.html", user=user, course=None, weeks=None, flash=flash_from_query(request))


@router.post("/admin/courses/new")
def new_course_submit(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    title = request.field("title", "").strip()
    if not title:
        return with_flash("/admin/courses/new", "Title is required.", "error")

    conn = db.get_conn()
    try:
        next_module = (conn.execute("SELECT max(module_number) FROM courses").fetchone()[0] or 0) + 1
        cur = conn.execute(
            """INSERT INTO courses (module_number, title, focus_area, description, status, created_by)
               VALUES (?,?,?,?,?,?)""",
            (next_module, title, request.field("focus_area", ""), request.field("description", ""),
             "draft", user["id"]),
        )
        course_id = cur.lastrowid
        _save_weeks(conn, course_id, request)
        conn.commit()
    finally:
        conn.close()
    return with_flash("/admin/courses", f"{title} created as a draft. Publish it when it's ready.", "ok")


@router.get("/admin/courses/<course_id>/edit")
def edit_course_form(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        course = conn.execute("SELECT * FROM courses WHERE id=?", (request.params["course_id"],)).fetchone()
        weeks = conn.execute("SELECT * FROM weeks WHERE course_id=? ORDER BY week_number",
                              (request.params["course_id"],)).fetchall()
    finally:
        conn.close()
    if not course:
        return Response("Course not found", status="404 Not Found")
    weeks = [dict(w, resources=json.loads(w["resources"] or "[]")) for w in weeks]
    return render("course_builder.html", user=user, course=course, weeks=weeks, flash=flash_from_query(request))


@router.post("/admin/courses/<course_id>/edit")
def edit_course_submit(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    course_id = request.params["course_id"]
    title = request.field("title", "").strip()
    if not title:
        return with_flash(f"/admin/courses/{course_id}/edit", "Title is required.", "error")

    conn = db.get_conn()
    try:
        conn.execute("UPDATE courses SET title=?, focus_area=?, description=? WHERE id=?",
                      (title, request.field("focus_area", ""), request.field("description", ""), course_id))
        _save_weeks(conn, course_id, request)
        conn.commit()
    finally:
        conn.close()
    return with_flash("/admin/courses", f"{title} updated.", "ok")


@router.post("/admin/courses/<course_id>/publish")
def publish_course(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        conn.execute("UPDATE courses SET status='published', published_at=? WHERE id=?",
                      (db.now(), request.params["course_id"]))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Course published", "It's now visible to every mentor.", "/admin/courses", back_label="Back to courses")


@router.post("/admin/courses/<course_id>/unpublish")
def unpublish_course(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        conn.execute("UPDATE courses SET status='draft' WHERE id=?", (request.params["course_id"],))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Course unpublished", "Existing enrolments are unaffected.", "/admin/courses", back_label="Back to courses")


# ------------------------------------------------------------------- parent --

@router.get("/parent")
def parent_home(request):
    user, err = require(request, roles=["parent_carer"])
    if err:
        return err
    conn = db.get_conn()
    try:
        links = conn.execute(
            "SELECT * FROM pupil_parent_links WHERE parent_user_id=?", (user["id"],)
        ).fetchall()
        pupil_ids = [l["pupil_id"] for l in links]
        enrolments = []
        for pid in pupil_ids:
            rows = conn.execute(
                """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title,
                          courses.id as course_id
                   FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id
                   JOIN courses ON courses.id=enrolments.course_id
                   WHERE pupil_id=? AND parent_access_enabled=1""",
                (pid,),
            ).fetchall()
            for e in rows:
                week = None
                if 1 <= e["current_week"] + 1 <= 5:
                    week = conn.execute("SELECT * FROM weeks WHERE course_id=? AND week_number=?",
                                         (e["course_id"], min(e["current_week"] + 1, 5))).fetchone()
                cert = conn.execute("SELECT * FROM certificates WHERE enrolment_id=?", (e["id"],)).fetchone()
                next_planned = conn.execute(
                    "SELECT planned_date FROM session_schedule WHERE enrolment_id=? AND week_number=?",
                    (e["id"], e["current_week"] + 1),
                ).fetchone()
                enrolments.append({"enrolment": e, "week": week, "certificate": cert,
                                    "next_planned": next_planned["planned_date"] if next_planned else None})
    finally:
        conn.close()
    return render("parent_home.html", user=user, enrolments=enrolments, flash=flash_from_query(request))


# ---------------------------------------------------------------- reports --

_ICON_LIST = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></svg>'
_ICON_DOC = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/></svg>'
_ICON_USERS = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'


@router.get("/admin/reports")
def admin_reports_chooser(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    cards = [
        {"title": "Whole-establishment report", "desc": "Every pupil, who mentors them, course(s), sessions completed and progress.",
         "href": "/admin/reports/full", "icon": _ICON_LIST, "bg": "var(--teal-light)"},
        {"title": "Pupil report", "desc": "Search for a pupil, their details, courses and progress in one file.",
         "href": "/admin/reports/full", "icon": _ICON_DOC, "bg": "var(--coral-light)"},
        {"title": "Mentor reports", "desc": "Choose a mentor, then download their mentoring list as a PDF or spreadsheet.",
         "href": "/admin/reports/caseload", "icon": _ICON_USERS, "bg": "var(--amber-light)"},
    ]
    return render("reports_chooser.html", user=user, cards=cards, intro=None, note=None,
                  flash=flash_from_query(request))


@router.get("/mentor/reports")
def mentor_reports_chooser(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    cards = [
        {"title": "Your mentoring list", "desc": "Every mentee, one file \u00b7 progress only, no notes.",
         "href": "/mentor/reports/caseload", "icon": _ICON_USERS, "bg": "var(--teal-light)"},
        {"title": "Pupil report", "desc": "One mentee's full report, courses, progress and session notes. Open your mentoring list below, then pick a mentee to view.",
         "href": "/mentor/reports/caseload", "icon": _ICON_DOC, "bg": "var(--coral-light)"},
    ]
    return render("reports_chooser.html", user=user, cards=cards,
                  intro="Download your mentoring list, or a full report for one of your mentees.",
                  note="Limited to pupils you mentor. For anyone else, ask an admin.",
                  flash=flash_from_query(request))


def _mentee_report_context(conn, enrolment_id, user):
    """Returns (enrolment, weeks_covered, reflection_or_None) or (None, None, None) if not authorised."""
    enrolment = conn.execute(
        """SELECT enrolments.*, pupils.forename, pupils.surname, pupils.establishment_id,
                  courses.title as course_title, users.name as mentor_name
           FROM enrolments
           JOIN pupils ON pupils.id = enrolments.pupil_id
           JOIN courses ON courses.id = enrolments.course_id
           JOIN users ON users.id = enrolments.mentor_id
           WHERE enrolments.id=?""",
        (enrolment_id,),
    ).fetchone()
    if not enrolment:
        return None, None, None

    authorised = False
    include_reflection = False
    if user["role"] in ("admin", "phil_staff") and enrolment["establishment_id"] == user["establishment_id"]:
        authorised = True
        include_reflection = True
    elif user["role"] == "mentor" and enrolment["mentor_id"] == user["id"]:
        authorised = True
        include_reflection = True
    elif user["role"] == "parent_carer" and enrolment["parent_access_enabled"]:
        link = conn.execute(
            "SELECT id FROM pupil_parent_links WHERE pupil_id=? AND parent_user_id=?",
            (enrolment["pupil_id"], user["id"]),
        ).fetchone()
        authorised = bool(link)
        include_reflection = False

    if not authorised:
        return None, None, None

    weeks = conn.execute(
        """SELECT weeks.week_number, weeks.title, weeks.objective, session_records.date
           FROM session_records JOIN weeks ON weeks.id = session_records.week_id
           WHERE session_records.enrolment_id=? ORDER BY weeks.week_number""",
        (enrolment_id,),
    ).fetchall()

    reflection = None
    if include_reflection and enrolment["status"] == "completed":
        reflection = conn.execute("SELECT * FROM completion_reflections WHERE enrolment_id=?",
                                   (enrolment_id,)).fetchone()

    return enrolment, weeks, reflection


@router.get("/report/mentee/<enrolment_id>")
def mentee_report_view(request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    conn = db.get_conn()
    try:
        enrolment, weeks, reflection = _mentee_report_context(conn, request.params["enrolment_id"], user)
    finally:
        conn.close()
    if not enrolment:
        return Response("Not found or not authorised", status="404 Not Found")
    return render("report_mentee.html", user=user, enrolment=enrolment, weeks=weeks, reflection=reflection,
                  flash=flash_from_query(request))


@router.get("/report/mentee/<enrolment_id>/pdf")
def mentee_report_pdf_download(request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    conn = db.get_conn()
    try:
        enrolment, weeks, reflection = _mentee_report_context(conn, request.params["enrolment_id"], user)
    finally:
        conn.close()
    if not enrolment:
        return Response("Not found or not authorised", status="404 Not Found")
    weeks_list = [dict(w) for w in weeks]
    reflection_dict = dict(reflection) if reflection else None
    path = pdfgen.mentee_report_pdf(
        enrolment["id"], f"{enrolment['forename']} {enrolment['surname']}", enrolment["course_title"],
        enrolment["mentor_name"], enrolment["start_date"], enrolment["current_week"], enrolment["status"],
        weeks_list, reflection_dict,
    )
    return pdf_response(path, "mentee-report.pdf")


def _caseload_rows(conn, mentor_id=None, establishment_id=None, show_mentor=False):
    query = """
        SELECT enrolments.id, enrolments.start_date, enrolments.current_week, enrolments.status,
               pupils.forename, pupils.surname, courses.title as course_title, users.name as mentor_name,
               enrolments.id as enrolment_id
        FROM enrolments
        JOIN pupils ON pupils.id = enrolments.pupil_id
        JOIN courses ON courses.id = enrolments.course_id
        JOIN users ON users.id = enrolments.mentor_id
        WHERE 1=1
    """
    params = []
    if mentor_id:
        query += " AND enrolments.mentor_id=?"
        params.append(mentor_id)
    if establishment_id:
        query += " AND pupils.establishment_id=?"
        params.append(establishment_id)
    query += " ORDER BY enrolments.status, pupils.surname"
    rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        start = datetime.date.fromisoformat(r["start_date"])
        scheduled_end = (start + datetime.timedelta(days=35)).isoformat()
        cert = conn.execute("SELECT id FROM certificates WHERE enrolment_id=?", (r["id"],)).fetchone()
        reflection = conn.execute("SELECT id FROM completion_reflections WHERE enrolment_id=?", (r["id"],)).fetchone()
        progress = "Completed" if r["status"] == "completed" else f"Week {r['current_week']} of 5"
        row = {
            "pupil": f"{r['forename']} {r['surname']}",
            "course": r["course_title"],
            "started": r["start_date"],
            "scheduled_end": scheduled_end,
            "progress": progress,
            "certificate": "Issued" if cert else "Not yet",
            "reflection": ("Done" if reflection else "Needed") if r["status"] == "completed" else "-",
            "enrolment_id": r["enrolment_id"],
        }
        if show_mentor:
            row["mentor"] = r["mentor_name"]
        result.append(row)
    return result


@router.get("/mentor/reports/caseload")
def mentor_caseload(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = _caseload_rows(conn, mentor_id=user["id"])
    finally:
        conn.close()
    return render("report_caseload.html", user=user, rows=rows, show_mentor=False,
                  title="My case load", pdf_url="/mentor/reports/caseload/pdf",
                  xlsx_url="/mentor/reports/caseload/xlsx",
                  filter_form=None, flash=flash_from_query(request))


@router.get("/mentor/reports/caseload/pdf")
def mentor_caseload_pdf(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = _caseload_rows(conn, mentor_id=user["id"])
    finally:
        conn.close()
    path = pdfgen.caseload_report_pdf("Case load report", rows, False, f"caseload_{user['id']}")
    return pdf_response(path, "caseload-report.pdf")


@router.get("/admin/reports/caseload")
def admin_caseload(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    mentor_filter = request.query.get("mentor_id", ["all"])[0]
    conn = db.get_conn()
    try:
        mentors = conn.execute(
            "SELECT id, name FROM users WHERE establishment_id=? AND role IN ('admin','mentor') ORDER BY name",
            (user["establishment_id"],),
        ).fetchall()
        mid = int(mentor_filter) if mentor_filter != "all" else None
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"))
    finally:
        conn.close()
    pdf_url = f"/admin/reports/caseload/pdf?mentor_id={mentor_filter}"
    xlsx_url = f"/admin/reports/caseload/xlsx?mentor_id={mentor_filter}"
    return render("report_caseload.html", user=user, rows=rows, show_mentor=(mentor_filter == "all"),
                  title="Establishment case load", pdf_url=pdf_url, xlsx_url=xlsx_url, mentors=mentors,
                  selected_mentor=mentor_filter, flash=flash_from_query(request))


@router.get("/admin/reports/caseload/pdf")
def admin_caseload_pdf(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    mentor_filter = request.query.get("mentor_id", ["all"])[0]
    conn = db.get_conn()
    try:
        mid = int(mentor_filter) if mentor_filter != "all" else None
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"))
    finally:
        conn.close()
    path = pdfgen.caseload_report_pdf("Establishment case load", rows, mentor_filter == "all",
                                       f"caseload_admin_{user['establishment_id']}")
    return pdf_response(path, "caseload-report.pdf")


@router.get("/mentor/reports/caseload/xlsx")
def mentor_caseload_xlsx(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = _caseload_rows(conn, mentor_id=user["id"])
    finally:
        conn.close()
    path = pdfgen.caseload_report_xlsx(rows, False, f"caseload_{user['id']}")
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=[("Content-Disposition", 'attachment; filename="caseload-report.xlsx"')],
    )


@router.get("/admin/reports/caseload/xlsx")
def admin_caseload_xlsx(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    mentor_filter = request.query.get("mentor_id", ["all"])[0]
    conn = db.get_conn()
    try:
        mid = int(mentor_filter) if mentor_filter != "all" else None
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"))
    finally:
        conn.close()
    path = pdfgen.caseload_report_xlsx(rows, mentor_filter == "all", f"caseload_admin_{user['establishment_id']}")
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=[("Content-Disposition", 'attachment; filename="caseload-report.xlsx"')],
    )


def _full_report_entries(conn, establishment_id, pupil_id=None):
    query = """
        SELECT enrolments.id, enrolments.start_date, enrolments.current_week, enrolments.status,
               pupils.forename, pupils.surname, courses.title as course_title, users.name as mentor_name
        FROM enrolments
        JOIN pupils ON pupils.id = enrolments.pupil_id
        JOIN courses ON courses.id = enrolments.course_id
        JOIN users ON users.id = enrolments.mentor_id
        WHERE pupils.establishment_id=?
    """
    params = [establishment_id]
    if pupil_id:
        query += " AND pupils.id=?"
        params.append(pupil_id)
    query += " ORDER BY pupils.surname, enrolments.created_at"
    rows = conn.execute(query, params).fetchall()

    entries = []
    for r in rows:
        weeks = conn.execute(
            """SELECT weeks.week_number, weeks.title, weeks.objective, session_records.date
               FROM session_records JOIN weeks ON weeks.id = session_records.week_id
               WHERE session_records.enrolment_id=? ORDER BY weeks.week_number""",
            (r["id"],),
        ).fetchall()
        reflection = None
        if r["status"] == "completed":
            refl_row = conn.execute("SELECT * FROM completion_reflections WHERE enrolment_id=?", (r["id"],)).fetchone()
            reflection = dict(refl_row) if refl_row else None
        entries.append({
            "pupil_name": f"{r['forename']} {r['surname']}",
            "course_title": r["course_title"],
            "mentor_name": r["mentor_name"],
            "start_date": r["start_date"],
            "current_week": r["current_week"],
            "status": r["status"],
            "weeks": [dict(w) for w in weeks],
            "reflection": reflection,
        })
    return entries


@router.get("/admin/reports/full")
def admin_full_report_form(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    selected_pupil = request.query.get("pupil_id", ["all"])[0]
    conn = db.get_conn()
    try:
        pupils = conn.execute("SELECT * FROM pupils WHERE establishment_id=? AND status='active' ORDER BY surname",
                               (user["establishment_id"],)).fetchall()
    finally:
        conn.close()
    return render("report_full.html", user=user, pupils=pupils, selected_pupil=selected_pupil,
                  flash=flash_from_query(request))


@router.get("/admin/reports/full/pdf")
def admin_full_report_pdf(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    pupil_filter = request.query.get("pupil_id", ["all"])[0]
    conn = db.get_conn()
    try:
        pupil_id = int(pupil_filter) if pupil_filter != "all" else None
        entries = _full_report_entries(conn, user["establishment_id"], pupil_id)
        title = "Full mentoring report"
        if pupil_id:
            p = conn.execute("SELECT forename, surname FROM pupils WHERE id=?", (pupil_id,)).fetchone()
            title = f"Full mentoring report - {p['forename']} {p['surname']}" if p else title
    finally:
        conn.close()
    path = pdfgen.full_mentoring_report_pdf(title, entries, f"full_report_{user['establishment_id']}_{pupil_filter}")
    return pdf_response(path, "full-mentoring-report.pdf")


# --------------------------------------------------------------- phil staff --

@router.get("/staff")
def staff_home(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        active_estabs = conn.execute("SELECT count(*) FROM establishments WHERE type='school' AND status='active'").fetchone()[0]
        individual_mentors = conn.execute("SELECT count(*) FROM establishments WHERE type='individual' AND status='active'").fetchone()[0]
        open_support = conn.execute("SELECT count(*) FROM support_requests WHERE status='open'").fetchone()[0]
        pending_requests = conn.execute("SELECT count(*) FROM course_requests WHERE status='open'").fetchone()[0]
        notes = conn.execute(
            "SELECT * FROM notifications WHERE recipient='phil_staff' AND status='unread' ORDER BY sent_at DESC LIMIT 10"
        ).fetchall()
        suspended_count = conn.execute("SELECT count(*) FROM establishments WHERE status='suspended'").fetchone()[0]
    finally:
        conn.close()
    return render("staff_home.html", user=user, active_estabs=active_estabs,
                  individual_mentors=individual_mentors, open_support=open_support,
                  pending_requests=pending_requests, notes=notes, suspended_count=suspended_count,
                  flash=flash_from_query(request))


@router.get("/staff/establishments")
def staff_establishments(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM establishments WHERE type='school' ORDER BY name").fetchall()
    finally:
        conn.close()
    return render("staff_establishments.html", user=user, establishments=rows, flash=flash_from_query(request))


@router.get("/staff/establishments/new")
def staff_new_establishment_form(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    return render("staff_establishment_new.html", user=user, flash=flash_from_query(request))


@router.post("/staff/establishments/new")
def staff_new_establishment_submit(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    name = request.field("establishment_name", "").strip()
    plan_type = request.field("plan_type", "pilot")
    admin_name = request.field("admin_name", "").strip()
    admin_email = request.field("admin_email", "").strip().lower()
    admin_password = request.field("admin_password", "")

    if not (name and admin_name and admin_email and len(admin_password) >= 8):
        return with_flash("/staff/establishments/new",
                           "Fill in every field. Password needs at least 8 characters.", "error")

    conn = db.get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone():
            return with_flash("/staff/establishments/new", "That admin email is already registered.", "error")
        now = db.now()
        cur = conn.execute("INSERT INTO establishments (type, name, status, created_at) VALUES (?,?,?,?)",
                            ("school", name, "active", now))
        establishment_id = cur.lastrowid
        if plan_type == "pilot":
            pilot_ends = (datetime.datetime.utcnow() + datetime.timedelta(days=PILOT_DAYS)).isoformat()
            conn.execute(
                """INSERT INTO subscriptions (establishment_id, plan_type, included_seats, pupil_cap,
                   status, payment_method, pilot_ends_at, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (establishment_id, "pilot", 3, 10, "active", "none", pilot_ends, now))
        else:
            conn.execute(
                """INSERT INTO subscriptions (establishment_id, plan_type, included_seats, pupil_cap,
                   status, payment_method, created_at) VALUES (?,?,?,?,?,?,?)""",
                (establishment_id, "school", 15, None, "active", request.field("payment_method", "invoice"), now))
        authlib.create_user(conn, establishment_id, "admin", admin_name, admin_email, admin_password)
        db.log_action(conn, user["id"], "establishment_created", "establishment", establishment_id,
                       f"Created {name} on behalf of the school ({plan_type})")
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Establishment added", f"{name} has been created and can sign in now.", "/staff/establishments", back_label="Back to establishments")


@router.get("/staff/establishments/<establishment_id>")
def staff_establishment_detail(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT * FROM establishments WHERE id=?", (request.params["establishment_id"],)).fetchone()
        sub = conn.execute("SELECT * FROM subscriptions WHERE establishment_id=? ORDER BY id DESC LIMIT 1",
                            (request.params["establishment_id"],)).fetchone()
        admin = conn.execute("SELECT * FROM users WHERE establishment_id=? AND role='admin' LIMIT 1",
                              (request.params["establishment_id"],)).fetchone()
        used = seats_used(conn, request.params["establishment_id"])
        pupil_count = conn.execute("SELECT count(*) FROM pupils WHERE establishment_id=? AND status='active'",
                                    (request.params["establishment_id"],)).fetchone()[0]
    finally:
        conn.close()
    if not estab:
        return Response("Not found", status="404 Not Found")
    return render("staff_establishment_detail.html", user=user, estab=estab, sub=sub, admin=admin, used=used,
                  limit=seat_limit(sub) if sub else 0, pupil_count=pupil_count, flash=flash_from_query(request))


@router.post("/staff/establishments/<establishment_id>/suspend")
def staff_suspend_establishment(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    eid = request.params["establishment_id"]
    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT name FROM establishments WHERE id=?", (eid,)).fetchone()
        conn.execute("UPDATE establishments SET status='suspended' WHERE id=?", (eid,))
        db.log_action(conn, user["id"], "establishment_suspended", "establishment", eid,
                       request.field("reason", "") or "No reason given")
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Establishment suspended", f"{estab['name']} has lost access immediately.", f"/staff/establishments/{eid}", back_label="Back to establishment")


@router.post("/staff/establishments/<establishment_id>/reactivate")
def staff_reactivate_establishment(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    eid = request.params["establishment_id"]
    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT name FROM establishments WHERE id=?", (eid,)).fetchone()
        conn.execute("UPDATE establishments SET status='active' WHERE id=?", (eid,))
        db.log_action(conn, user["id"], "establishment_reactivated", "establishment", eid, None)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Establishment reactivated", f"{estab['name']} is active again.", f"/staff/establishments/{eid}", back_label="Back to establishment")


@router.get("/staff/mentors")
def staff_individual_mentors(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT establishments.*, users.name as mentor_name, users.email as mentor_email, users.id as user_id
               FROM establishments JOIN users ON users.establishment_id = establishments.id AND users.role='mentor'
               WHERE establishments.type='individual' ORDER BY users.name"""
        ).fetchall()
    finally:
        conn.close()
    return render("staff_mentors.html", user=user, mentors=rows, flash=flash_from_query(request))


@router.post("/staff/mentors/<establishment_id>/suspend")
def staff_suspend_mentor(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    eid = request.params["establishment_id"]
    conn = db.get_conn()
    try:
        conn.execute("UPDATE establishments SET status='suspended' WHERE id=?", (eid,))
        db.log_action(conn, user["id"], "individual_mentor_suspended", "establishment", eid, None)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Mentor suspended", "This individual mentor account has lost access.", "/staff/mentors", back_label="Back to mentors")


@router.post("/staff/mentors/<establishment_id>/reactivate")
def staff_reactivate_mentor(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    eid = request.params["establishment_id"]
    conn = db.get_conn()
    try:
        conn.execute("UPDATE establishments SET status='active' WHERE id=?", (eid,))
        db.log_action(conn, user["id"], "individual_mentor_reactivated", "establishment", eid, None)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Mentor reactivated", "This individual mentor account is active again.", "/staff/mentors", back_label="Back to mentors")


@router.get("/staff/suspended")
def staff_suspended_accounts(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        suspended_estabs = conn.execute(
            "SELECT * FROM establishments WHERE type='school' AND status='suspended' ORDER BY name"
        ).fetchall()
        suspended_mentors = conn.execute(
            """SELECT establishments.*, users.name as mentor_name, users.email as mentor_email
               FROM establishments JOIN users ON users.establishment_id = establishments.id AND users.role='mentor'
               WHERE establishments.type='individual' AND establishments.status='suspended' ORDER BY users.name"""
        ).fetchall()
        suspend_times = {}
        for row in conn.execute(
            """SELECT target_id, MAX(created_at) as at FROM audit_log
               WHERE action IN ('establishment_suspended','individual_mentor_suspended')
               GROUP BY target_id"""
        ).fetchall():
            suspend_times[row["target_id"]] = row["at"]
    finally:
        conn.close()
    suspend_labels = {tid: days_ago_label(ts) for tid, ts in suspend_times.items()}
    return render("staff_suspended.html", user=user, suspended_estabs=suspended_estabs,
                  suspended_mentors=suspended_mentors, suspend_labels=suspend_labels,
                  flash=flash_from_query(request))


@router.get("/staff/help")
def staff_help(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    return render("staff_help.html", user=user, flash=flash_from_query(request))


@router.get("/staff/course-requests")
def staff_course_requests(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT course_requests.*, establishments.name as establishment_name, users.name as requester_name
               FROM course_requests
               JOIN establishments ON establishments.id = course_requests.establishment_id
               JOIN users ON users.id = course_requests.requested_by
               ORDER BY (course_requests.status='open') DESC, course_requests.created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return render("staff_course_requests.html", user=user, requests=rows, flash=flash_from_query(request))


@router.post("/staff/course-requests/<request_id>/status")
def staff_course_request_status(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    rid = request.params["request_id"]
    new_status = request.field("status", "in_progress")
    conn = db.get_conn()
    try:
        conn.execute("UPDATE course_requests SET status=?, updated_at=? WHERE id=?", (new_status, db.now(), rid))
        db.log_action(conn, user["id"], "course_request_updated", "course_request", rid, f"status -> {new_status}")
        conn.commit()
    finally:
        conn.close()
    return with_flash("/staff/course-requests", "Updated.", "ok")


@router.get("/admin/course-requests/new")
def new_course_request_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    return render("course_request_new.html", user=user, flash=flash_from_query(request))


@router.post("/admin/course-requests/new")
def new_course_request_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    topic = request.field("topic", "").strip()
    if not topic:
        return with_flash("/admin/course-requests/new", "Please describe the course topic.", "error")
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO course_requests (establishment_id, requested_by, topic, note, status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (user["establishment_id"], user["id"], topic, request.field("note", ""), "open", db.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Request sent", "The Phil team will review your course request.", "/admin", back_label="Admin home")


@router.get("/support/new")
def new_support_request_form(request):
    user, err = require(request, roles=["admin", "mentor", "parent_carer"])
    if err:
        return err
    return render("support_new.html", user=user, flash=flash_from_query(request))


@router.post("/support/new")
def new_support_request_submit(request):
    user, err = require(request, roles=["admin", "mentor", "parent_carer"])
    if err:
        return err
    subject = request.field("subject", "").strip()
    message = request.field("message", "").strip()
    if not subject or not message:
        return with_flash("/support/new", "Subject and message are both required.", "error")
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO support_requests (establishment_id, requester_user_id, subject, message,
               status, created_at) VALUES (?,?,?,?,?,?)""",
            (user["establishment_id"], user["id"], subject, message, "open", db.now()),
        )
        conn.commit()
    finally:
        conn.close()
    dest = {"admin": "/admin", "mentor": "/mentor", "parent_carer": "/parent"}.get(user["role"], "/mentor")
    return with_flash(dest, "Support request sent. The Phil team will follow up.", "ok")


@router.get("/staff/support")
def staff_support_inbox(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT support_requests.*, establishments.name as establishment_name, users.name as requester_name
               FROM support_requests
               LEFT JOIN establishments ON establishments.id = support_requests.establishment_id
               JOIN users ON users.id = support_requests.requester_user_id
               ORDER BY (support_requests.status='open') DESC, support_requests.created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return render("staff_support.html", user=user, requests=rows, flash=flash_from_query(request))


@router.get("/staff/support/<request_id>")
def staff_support_detail(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        ticket = conn.execute(
            """SELECT support_requests.*, establishments.name as establishment_name, users.name as requester_name
               FROM support_requests
               LEFT JOIN establishments ON establishments.id = support_requests.establishment_id
               JOIN users ON users.id = support_requests.requester_user_id
               WHERE support_requests.id=?""",
            (request.params["request_id"],),
        ).fetchone()
        pupil = None
        if ticket and ticket["pupil_id"]:
            pupil = conn.execute("SELECT * FROM pupils WHERE id=?", (ticket["pupil_id"],)).fetchone()
            db.log_action(conn, user["id"], "safeguarding_scoped_access", "pupil", ticket["pupil_id"],
                           f"Viewed via support ticket #{ticket['id']}")
            conn.commit()
    finally:
        conn.close()
    if not ticket:
        return Response("Not found", status="404 Not Found")
    return render("staff_support_detail.html", user=user, ticket=ticket, pupil=pupil, flash=flash_from_query(request))


@router.post("/staff/support/<request_id>/resolve")
def staff_support_resolve(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    rid = request.params["request_id"]
    conn = db.get_conn()
    try:
        conn.execute("UPDATE support_requests SET status='resolved', response=?, resolved_at=? WHERE id=?",
                      (request.field("response", ""), db.now(), rid))
        db.log_action(conn, user["id"], "support_resolved", "support_request", rid, None)
        conn.commit()
    finally:
        conn.close()
    return with_flash("/staff/support", "Ticket resolved.", "ok")


@router.get("/staff/billing")
def staff_billing(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        subs = conn.execute(
            """SELECT subscriptions.*, establishments.name as establishment_name, establishments.type as establishment_type
               FROM subscriptions JOIN establishments ON establishments.id = subscriptions.establishment_id
               WHERE subscriptions.id IN (SELECT max(id) FROM subscriptions GROUP BY establishment_id)
               ORDER BY subscriptions.plan_type, establishments.name"""
        ).fetchall()
        annual_school_prices = {"school": 750}
        mrr = 0
        active_paid = 0
        pilots = []
        for s in subs:
            if s["plan_type"] == "school" and s["status"] == "active":
                mrr += 750 / 12
                active_paid += 1
            elif s["plan_type"] == "individual" and s["status"] == "active":
                mrr += 22
                active_paid += 1
            if s["plan_type"] == "pilot" and s["status"] == "active":
                pilots.append(s)
        invoices = conn.execute(
            """SELECT invoices.*, establishments.name as establishment_name
               FROM invoices JOIN subscriptions ON subscriptions.id = invoices.subscription_id
               JOIN establishments ON establishments.id = subscriptions.establishment_id
               ORDER BY invoices.created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return render("staff_billing.html", user=user, subs=subs, mrr=round(mrr, 2), active_paid=active_paid,
                  pilots=pilots, invoices=invoices, flash=flash_from_query(request))


@router.get("/staff/team")
def staff_team(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM users WHERE role='phil_staff' ORDER BY name").fetchall()
    finally:
        conn.close()
    return render("staff_team.html", user=user, team=rows, flash=flash_from_query(request))


@router.get("/staff/team/new")
def staff_team_new_form(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    return render("staff_team_new.html", user=user, flash=flash_from_query(request))


@router.post("/staff/team/new")
def staff_team_new_submit(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    name = request.field("name", "").strip()
    email = request.field("email", "").strip().lower()
    password = request.field("password", "")
    if not name or not email or len(password) < 8:
        return with_flash("/staff/team/new", "Fill in every field. Password needs at least 8 characters.", "error")
    conn = db.get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            return with_flash("/staff/team/new", "That email is already registered.", "error")
        authlib.create_user(conn, None, "phil_staff", name, email, password)
        db.log_action(conn, user["id"], "phil_staff_invited", "user", None, email)
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Invite sent", f"{name} added to the Phil team and can sign in now.", "/staff/team", back_label="Back to team")


@router.get("/staff/audit-log")
def staff_audit_log(request):
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT audit_log.*, users.name as actor_name
               FROM audit_log LEFT JOIN users ON users.id = audit_log.actor_user_id
               ORDER BY audit_log.created_at DESC LIMIT 200"""
        ).fetchall()
    finally:
        conn.close()
    return render("staff_audit_log.html", user=user, rows=rows, flash=flash_from_query(request))


@router.post("/staff/notifications/<notification_id>/read")
def mark_notification_read(request):
    user, err = require(request, roles=["phil_staff", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        conn.execute("UPDATE notifications SET status='read' WHERE id=?", (request.params["notification_id"],))
        conn.commit()
    finally:
        conn.close()
    default_dest = "/staff" if user["role"] == "phil_staff" else "/admin"
    dest = request.field("next", "") or default_dest
    return redirect(dest)


@router.post("/admin/convert-pilot")
def convert_pilot(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        sub = conn.execute("SELECT * FROM subscriptions WHERE establishment_id=? ORDER BY id DESC LIMIT 1",
                            (user["establishment_id"],)).fetchone()
        if not sub or sub["plan_type"] != "pilot":
            return with_flash("/admin", "No active pilot to convert.", "error")
        conn.execute(
            """UPDATE subscriptions SET plan_type='school', included_seats=15, pupil_cap=NULL,
               payment_method='invoice', pilot_ends_at=NULL WHERE id=?""",
            (sub["id"],),
        )
        db.log_action(conn, user["id"], "pilot_converted", "subscription", sub["id"], None)
        conn.commit()
    finally:
        conn.close()
    return with_flash("/admin", "Converted to a paid plan. Every pupil, mentor and session record carries over unchanged.", "ok")


# -------------------------------------------------------------- card billing --

@router.get("/admin/billing/checkout")
def billing_checkout(request):
    """Starts a Stripe Checkout session for the establishment's plan and
    redirects the admin's browser to Stripe's hosted payment page. This is
    the card-payment alternative to the manual/invoice path above; both can
    coexist, an establishment isn't forced onto one or the other."""
    user, err = require(request, roles=["admin"])
    if err:
        return err
    if not billing.is_configured():
        return with_flash(
            "/admin",
            "Card payments aren't set up on this deployment yet. Pay by invoice below, "
            "or contact Phil support once Stripe is configured.",
            "error",
        )
    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)).fetchone()
    finally:
        conn.close()
    if not estab:
        return with_flash("/admin", "Establishment not found.", "error")
    try:
        checkout_url = billing.create_checkout_session(estab["id"], estab["name"], user["email"], estab["type"])
    except RuntimeError as exc:
        return with_flash("/admin", str(exc), "error")
    return redirect(checkout_url)


@router.get("/billing/success")
def billing_success(request):
    user = current_user(request)
    return render("billing_result.html", user=user, outcome="success", flash=flash_from_query(request))


@router.get("/billing/cancel")
def billing_cancel(request):
    user = current_user(request)
    return render("billing_result.html", user=user, outcome="cancel", flash=flash_from_query(request))


@router.post("/webhooks/stripe")
def stripe_webhook(request):
    """Stripe calls this directly, no session cookie, no CSRF token, its
    identity comes entirely from the signature header verified below. Per
    Stripe's own guidance this always acknowledges with 200 once the
    signature checks out, even for event types Phil doesn't act on,
    otherwise Stripe interprets a non-200 as 'try again later' and retries
    for up to three days."""
    if not billing.is_configured():
        return Response("Stripe not configured", status="503 Service Unavailable")
    sig_header = request.header("Stripe-Signature")
    try:
        event = billing.verify_webhook(request.raw_body, sig_header)
    except Exception:
        return Response("Invalid signature", status="400 Bad Request")

    conn = db.get_conn()
    try:
        if billing.already_processed(conn, event["id"]):
            return Response("", status="200 OK")

        if event["type"] == "checkout.session.completed":
            session_obj = event["data"]["object"]
            estab_id = session_obj.get("client_reference_id") or session_obj.get("metadata", {}).get("establishment_id")
            if estab_id:
                estab = conn.execute("SELECT * FROM establishments WHERE id=?", (estab_id,)).fetchone()
                sub = conn.execute(
                    "SELECT * FROM subscriptions WHERE establishment_id=? ORDER BY id DESC LIMIT 1", (estab_id,)
                ).fetchone()
                if estab and sub:
                    if estab["type"] == "school":
                        plan_type, included_seats, pupil_cap = "school", 15, None
                    else:
                        plan_type, included_seats, pupil_cap = "individual", 1, None
                    conn.execute(
                        """UPDATE subscriptions SET plan_type=?, included_seats=?, pupil_cap=?,
                           payment_method='card', stripe_customer_id=?, stripe_subscription_id=?,
                           status='active', pilot_ends_at=NULL WHERE id=?""",
                        (plan_type, included_seats, pupil_cap, session_obj.get("customer"),
                         session_obj.get("subscription"), sub["id"]),
                    )
                    db.log_action(conn, None, "card_payment_completed", "subscription", sub["id"],
                                  f"Stripe checkout completed for {estab['name']}")

        elif event["type"] in ("customer.subscription.deleted", "customer.subscription.paused"):
            stripe_sub_id = event["data"]["object"].get("id")
            sub = conn.execute(
                "SELECT * FROM subscriptions WHERE stripe_subscription_id=?", (stripe_sub_id,)
            ).fetchone()
            if sub:
                conn.execute("UPDATE subscriptions SET status='cancelled' WHERE id=?", (sub["id"],))
                db.log_action(conn, None, "card_subscription_cancelled", "subscription", sub["id"], None)

        billing.mark_processed(conn, event["id"], event["type"], db.now())
        conn.commit()
    finally:
        conn.close()
    return Response("", status="200 OK")


# --------------------------------------------------------------- downloads --

@router.get("/certificate/<enrolment_id>/pdf")
def certificate_download(request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    conn = db.get_conn()
    try:
        cert = conn.execute("SELECT * FROM certificates WHERE enrolment_id=?",
                             (request.params["enrolment_id"],)).fetchone()
    finally:
        conn.close()
    if not cert or not cert["pdf_path"] or not os.path.exists(cert["pdf_path"]):
        return Response("Certificate not found", status="404 Not Found")
    return pdf_response(cert["pdf_path"], "certificate.pdf")


@router.get("/session/<record_id>/pdf")
def session_pdf_download(request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    conn = db.get_conn()
    try:
        record = conn.execute("SELECT * FROM session_records WHERE id=?",
                               (request.params["record_id"],)).fetchone()
    finally:
        conn.close()
    if not record or not record["pdf_path"] or not os.path.exists(record["pdf_path"]):
        return Response("Session record not found", status="404 Not Found")
    return pdf_response(record["pdf_path"], "session-record.pdf")


# --------------------------------------------------------------------- wsgi --

wsgi_app = make_wsgi_app(router, static_dir=STATIC_DIR)
