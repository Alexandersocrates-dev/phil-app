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
import re

import db
import body_map
import auth as authlib
import billing
from framework import Router, Request, Response, render, redirect, pdf_response, make_wsgi_app
from framework import jinja_env as framework_jinja
from pdf import generate as pdfgen

router = Router()
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _static_version():
    """A cache-busting stamp derived from the stylesheet's own timestamp.

    Browsers cache /static/style.css hard, so a colour change can sit invisible
    for days on a returning mentor's machine while looking fine to whoever
    deployed it. Deriving the stamp from the file's modification time means it
    changes exactly when the CSS does, with nobody having to remember to bump a
    number. Falls back to a fixed value if the file can't be read, which only
    costs the cache-busting, never the page."""
    try:
        return str(int(os.path.getmtime(os.path.join(STATIC_DIR, "style.css"))))
    except OSError:
        return "1"


# Exposed to every template, so the link tag in base.html needs no per-render
# plumbing and no route has to remember to pass it.
# Five sessions with the pupil, then a sixth the mentor writes alone. Named
# rather than repeated as a literal: it appeared in six places and they would
# have drifted apart.
SESSIONS_PER_COURSE = 6
PUPIL_SESSIONS = 5

framework_jinja.globals["static_v"] = _static_version()
framework_jinja.globals["sessions_total"] = SESSIONS_PER_COURSE


def uk_date(value):
    """2026-09-07 as 07/09/2026. Anything unparseable is returned untouched."""
    if not value:
        return ""
    try:
        return datetime.date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


def uk_date_long(value):
    """2026-09-07 as 7 September 2026, for headings and certificates."""
    if not value:
        return ""
    try:
        d = datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return value
    return "%d %s %d" % (d.day, d.strftime("%B"), d.year)


def year_group(value):
    """"9" as "Year 9", but "Reception" left alone.

    Schools type all sorts into this field — 9, Year 9, Reception, Nursery,
    Sixth form — so the word is added only when the value is a bare number.
    Anything a human has already written stays exactly as they wrote it.
    """
    if value is None:
        return ""
    text = str(value).strip()
    return f"Year {text}" if text.isdigit() else text


framework_jinja.filters["year_group"] = year_group
framework_jinja.filters["uk_date"] = uk_date
framework_jinja.filters["uk_date_long"] = uk_date_long
framework_jinja.globals["pupil_sessions"] = PUPIL_SESSIONS
RESOURCE_PACKS_PATH = os.path.join(os.path.dirname(__file__), "data", "resource_packs.json")
_resource_packs_cache = None


SESSION_STEPS = ("checkin", "input", "activity", "reflect", "home")
_STEP_TEXT_FIELD = {"checkin": "checkin", "input": "input_content",
                    "activity": "activity", "reflect": "reflect", "home": "home_activity"}
_RESOURCE_STOPWORDS = {"template", "card", "cards", "sheet", "handout", "set", "options",
                       "note", "notes", "plan", "chart", "log", "the", "and", "for", "my"}


def _stem(word):
    """Crude suffix stripping, enough to match a resource name against the prose
    that introduces it. "Calm-down strategy cards" has to match "practical
    calming strategies", which exact-word matching misses entirely."""
    for suffix in ("ing", "ies", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return word


def _resource_keywords(name):
    return {_stem(w) for w in re.findall(r"[a-z]+", (name or "").lower())
            if w not in _RESOURCE_STOPWORDS and len(w) > 2}


def assign_resources_to_steps(week, items):
    """Works out which step of the session each resource belongs to, so it can be
    shown at the point of use rather than in a list at the top.

    Nothing in the data records this, but the step text names its own resources:
    'agree to track one trigger using a simple tally on a card' is what places
    the tally card at Reflect. Matching on the distinctive words in the resource
    name recovers that. Anything with no clear match goes to Activity, which is
    where most resources are used and where a mentor would look first."""
    texts = {step: (week.get(_STEP_TEXT_FIELD[step]) or "") for step in SESSION_STEPS}
    by_step = {step: [] for step in SESSION_STEPS}
    for item in items:
        keywords = _resource_keywords(item.get("name"))
        best, best_score = None, 0
        for step in SESSION_STEPS:
            score = len(keywords & _resource_keywords(texts[step]))
            if score > best_score:
                best, best_score = step, score
        by_step[best or "activity"].append(item)
    return by_step


def attach_figures(items):
    """Give a body-map resource the geometry both renderers draw from."""
    for item in items:
        if body_map.is_body_map(item):
            rows = (item.get("checklist") or {}).get("items") or []
            item["figure_points"] = body_map.points_for(rows)
            item["figure_parts"] = body_map.PARTS
            item["figure_view"] = (body_map.VIEW_W, body_map.VIEW_H)
    return items


def assign_resources_to_lines(week, items):
    """Which numbered instruction each resource belongs under.

    assign_resources_to_steps gets a resource to the right step; this gets it to
    the right line within it. A session that says "1. Show the anger cycle
    diagram ... 4. Use the body map handout" should show each sheet under the
    instruction that calls for it, in that order — otherwise both land in a heap
    at the foot of the step and a mentor reads step 1 while looking at step 4's
    handout.

    Returns, per step: the numbered lines, each with the resources that belong
    to it, and any leftovers that matched the step but no particular line.
    """
    out = {}
    for step in SESSION_STEPS:
        text = (week.get(_STEP_TEXT_FIELD[step]) or "")
        lines = [ln for ln in text.split("\n") if ln.strip()]
        step_items = [i for i in items if i.get("_step") == step]
        placed = {}
        leftover = []
        for item in step_items:
            keywords = _resource_keywords(item.get("name"))
            best, best_score = None, 0
            for n, line in enumerate(lines):
                score = len(keywords & _resource_keywords(line))
                if score > best_score:
                    best, best_score = n, score
            if best is None:
                leftover.append(item)
            else:
                placed.setdefault(best, []).append(item)
        out[step] = {
            "lines": [{"text": ln, "items": placed.get(n, [])}
                      for n, ln in enumerate(lines)],
            "leftover": leftover,
        }
    return out


def resource_slug(name):
    """A stable key for a resource, so entries survive a rename of the display
    text. Deliberately not the display name."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60]


def resource_work_for(conn, enrolment_id, week_id):
    """The pupil's written work, grouped by resource and formatted for the PDF.

    Shape matters here. A tally printed as a flat list of cells is unreadable —
    it has to come out as rows. A ticked checklist has to print what was ticked,
    not the word "yes"."""
    rows = conn.execute(
        """SELECT resource_slug, field_key, value FROM resource_entries
           WHERE enrolment_id=? AND week_id=? ORDER BY resource_slug, field_key""",
        (enrolment_id, week_id)).fetchall()
    if not rows:
        return []

    items = {}
    for pack in _load_resource_packs().values():
        for item in pack.get("items", []):
            items[resource_slug(item.get("name"))] = item

    by_slug = {}
    for row in rows:
        by_slug.setdefault(row["resource_slug"], {})[row["field_key"]] = row["value"]

    out = []
    for slug, fields in by_slug.items():
        item = items.get(slug, {})
        name = item.get("name") or slug.replace("-", " ").capitalize()
        lines = []

        # Table cells come back as t<row>_<col>; rebuild the rows so a tally
        # reads across rather than down.
        table_rows = {}
        for key, value in fields.items():
            if key.startswith("t"):
                try:
                    r, c = key[1:].split("_")
                    table_rows.setdefault(int(r), {})[int(c)] = value
                except ValueError:
                    continue
        table = item.get("table") or {}
        headers = table.get("headers") or []
        for r in sorted(table_rows):
            cells = table_rows[r]
            # Include the printed cells around what was written, so a row that
            # was partly pre-filled still makes sense.
            source = (table.get("rows") or [])
            width = len(source[r]) if r < len(source) else (max(cells) + 1)
            parts = []
            for c in range(width):
                value = cells.get(c) or (source[r][c] if r < len(source) and c < len(source[r]) else "")
                if value:
                    label = headers[c] if c < len(headers) else ""
                    parts.append(f"{label}: {value}" if label and len(headers) > 2 else value)
            if parts:
                lines.append("  \u00b7  ".join(parts))

        # Plan fields: print the question with the answer.
        form_fields = (item.get("form") or {}).get("fields") or []
        for key in sorted(k for k in fields if k.startswith("f")):
            try:
                i = int(key[1:])
            except ValueError:
                continue
            label = form_fields[i] if i < len(form_fields) else "Answer"
            lines.append(f"{label}: {fields[key]}")

        # Checklists: print what was ticked, not the word "yes".
        check_items = (item.get("checklist") or {}).get("items") or []
        ticked = []
        for key in sorted(k for k in fields if k.startswith("c")):
            try:
                i = int(key[1:])
            except ValueError:
                continue
            if i < len(check_items):
                ticked.append(check_items[i])
        if ticked:
            lines.append("Ticked: " + ", ".join(ticked))

        if lines:
            out.append((name, lines))
    return sorted(out)


def resource_entries_for(conn, enrolment_id, week_id):
    """Everything written on this week's resources, as {slug: {field: value}}."""
    rows = conn.execute(
        """SELECT resource_slug, field_key, value FROM resource_entries
           WHERE enrolment_id=? AND week_id=?""",
        (enrolment_id, week_id)).fetchall()
    out = {}
    for row in rows:
        out.setdefault(row["resource_slug"], {})[row["field_key"]] = row["value"]
    return out


def save_resource_entries(conn, enrolment_id, week_id, request, user_id):
    """Stores what was typed into a resource this session.

    Fields arrive named res__<slug>__<field>. An empty value deletes the row
    rather than storing a blank, so a cleared cell doesn't linger as data and
    the table only holds what a pupil actually wrote."""
    saved = 0
    for name, values in request.form.items():
        if not name.startswith("res__"):
            continue
        parts = name.split("__", 2)
        if len(parts) != 3:
            continue
        _, slug, field_key = parts
        value = (values[0] if isinstance(values, list) else values or "").strip()
        if value:
            conn.execute(
                """INSERT INTO resource_entries
                   (enrolment_id, week_id, resource_slug, field_key, value, updated_by, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(enrolment_id, week_id, resource_slug, field_key)
                   DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by,
                                 updated_at=excluded.updated_at""",
                (enrolment_id, week_id, slug, field_key, value, user_id, db.now()))
            saved += 1
        else:
            conn.execute(
                """DELETE FROM resource_entries
                   WHERE enrolment_id=? AND week_id=? AND resource_slug=? AND field_key=?""",
                (enrolment_id, week_id, slug, field_key))
    return saved


def resource_items_for(module_number, resource_names):
    """Returns the full pack entries for a list of resource names, in the order
    the week lists them. Names are matched loosely because a week's list and the
    pack are maintained separately; an exact-match requirement would fail
    silently on a stray capital and show the mentor nothing."""
    packs = _load_resource_packs()
    entry = packs.get(str(module_number).zfill(2)) or {}
    # A week and a pack are edited separately, so the same sheet ends up with two
    # names: "Trigger list" in the pack, "Trigger list template" in the week. An
    # item's aliases carry those alternatives, so a rewording never silently
    # leaves a mentor with a resource that has no content behind it.
    by_name = {}
    for item in entry.get("items", []):
        by_name[_norm_resource(item.get("name"))] = item
        for alias in item.get("aliases", []):
            by_name.setdefault(_norm_resource(alias), item)
    out = []
    for name in resource_names or []:
        item = by_name.get(_norm_resource(name))
        if item:
            # The slug keys anything a pupil writes on this resource, so it comes
            # from the pack's own name rather than the week's wording — the two
            # differ, and entries must not move when a week is reworded.
            out.append(dict(item, slug=resource_slug(item.get("name"))))
    return out


def _load_resource_packs():
    global _resource_packs_cache
    if _resource_packs_cache is None:
        with open(RESOURCE_PACKS_PATH, "r", encoding="utf-8") as f:
            _resource_packs_cache = json.load(f)
    return _resource_packs_cache


LEGAL_DOCS_PATH = os.path.join(os.path.dirname(__file__), "data", "legal_docs.json")
_legal_docs_cache = None


def _load_legal_docs():
    global _legal_docs_cache
    if _legal_docs_cache is None:
        with open(LEGAL_DOCS_PATH, "r", encoding="utf-8") as f:
            _legal_docs_cache = json.load(f)
    return _legal_docs_cache



PILOT_DAYS = 21


# ---------------------------------------------------------------- helpers --

def current_user(request):
    conn = db.get_conn()
    try:
        token = request.cookie(authlib.SESSION_COOKIE)
        return authlib.user_from_token(conn, token)
    finally:
        conn.close()


def unread_notification_count(conn, user):
    if user["role"] == "phil_staff":
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE recipient='phil_staff' AND status='unread'"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE recipient=? AND establishment_id=? AND status='unread'",
            (user["role"], user["establishment_id"]),
        ).fetchone()
    return row["c"] if row else 0


def require(request, roles=None):
    """Returns the user row (as a dict, with unread_notifications attached), or a redirect Response if not authorised."""
    user = current_user(request)
    if not user:
        return None, redirect("/login")
    if roles and user["role"] not in roles:
        # A signed-in person who lands somewhere their role can't go is almost
        # always looking at a stale page, or has switched accounts in another
        # tab. Sending them to their own home explains itself; a bare 403 with
        # no navigation looks like the app has broken.
        home = {"admin": "/admin", "mentor": "/mentor",
                "parent_carer": "/parent", "phil_staff": "/staff"}.get(user["role"])
        if home:
            return None, with_flash(
                home, "That area isn't available to your account. "
                      "If you've just switched accounts, this is the right place for "
                      f"{user['name']}.", "error")
        return None, Response("Not authorised for this area.", status="403 Forbidden")
    user = dict(user)
    conn = db.get_conn()
    try:
        if user["role"] != "phil_staff" and user["establishment_id"]:
            estab = conn.execute("SELECT status FROM establishments WHERE id=?",
                                  (user["establishment_id"],)).fetchone()
            if estab and estab["status"] == "suspended":
                return None, Response(
                    "This establishment's access has been suspended. Contact Phil support to resolve this.",
                    status="403 Forbidden")
        user["unread_notifications"] = unread_notification_count(conn, user)
    finally:
        conn.close()
    return user, None


def stripe_field(obj, key, default=None):
    """Reads one field from a Stripe API object.

    Stripe's objects are not dicts and, in this version of the library, expose
    no .get() at all: attribute lookup falls through to __getattr__, which
    raises AttributeError(key), and item access raises KeyError for a missing
    key. So neither obj.get(key) nor a bare obj[key] is safe. This tries item
    access, then attribute access, and returns the default rather than raising,
    which is what a webhook handler wants: a missing optional field should
    never turn a real payment into a 500."""
    try:
        value = obj[key]
    except (KeyError, TypeError, AttributeError):
        value = getattr(obj, key, None)
    return default if value is None else value


# How much of a course each kind of visitor may see. A five-session course is
# the deliverable, so it is released in step with what someone has committed to.
WEEKS_VISITOR = 1   # not signed in: enough to judge quality
WEEKS_PILOT = 3     # a 21-day pilot, so three sessions: one per week of trial
WEEKS_FULL = 99     # a paid plan: everything


def weeks_allowed(user):
    """Returns how many weeks of any course this user may see in full.

    Reads the live subscription every time rather than caching anything, so a
    pilot that converts to paid unlocks the rest immediately, with no extra
    step for anyone to remember."""
    if not user:
        return WEEKS_VISITOR
    # current_user() returns a sqlite3.Row and require() returns a dict. Both
    # support ["key"]; only the dict supports .get(), so index, never .get().
    if user["role"] == "phil_staff":
        return WEEKS_FULL
    if not user["establishment_id"]:
        return WEEKS_VISITOR
    conn = db.get_conn()
    try:
        sub = conn.execute(
            """SELECT plan_type, status FROM subscriptions
               WHERE establishment_id=? ORDER BY id DESC LIMIT 1""",
            (user["establishment_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not sub:
        return WEEKS_VISITOR
    if sub["plan_type"] == "pilot":
        return WEEKS_PILOT
    return WEEKS_FULL if sub["status"] == "active" else WEEKS_PILOT


def weeks_for_pack(conn, course_id, limit):
    """Returns the set of resource names a user at this limit may download.

    Pack items carry no session tag of their own, but every week lists the
    resources it uses, so the week's own list is what assigns an item to a
    session. An item no week claims is treated as beyond the limit: withholding
    one sheet is a smaller error than handing over a paid resource."""
    if limit >= WEEKS_FULL:
        return None  # None means "no filtering"
    rows = conn.execute(
        "SELECT week_number, resources FROM weeks WHERE course_id=? ORDER BY week_number",
        (course_id,),
    ).fetchall()
    allowed = set()
    for r in rows:
        if r["week_number"] <= limit:
            for name in json.loads(r["resources"] or "[]"):
                allowed.add(_norm_resource(name))
    return allowed


def _norm_resource(name):
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def require_active_subscription(user):
    """Returns None when this user's establishment may use the product, or a
    redirect to the billing page when it may not.

    Individuals are blocked until they subscribe: they self-serve by card, so
    an unpaid individual is simply someone who hasn't paid yet.

    Schools are deliberately NOT blocked here. A school on the invoice path or
    a pilot is legitimately unpaid as far as Stripe is concerned, and locking a
    mentor out mid-session because a finance office is slow would cost more
    goodwill than the revenue it protects. Establishment access is handled by
    Phil staff suspending the establishment instead."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT s.status AS sub_status, e.type AS estab_type
               FROM subscriptions s
               JOIN establishments e ON e.id = s.establishment_id
               WHERE s.establishment_id = ?
               ORDER BY s.id DESC LIMIT 1""",
            (user["establishment_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    # Anything other than 'active' means unpaid. New individual signups start
    # as 'expired' rather than a clearer word like 'pending' because the
    # subscriptions table has a CHECK constraint allowing only
    # active/expired/cancelled, and altering a CHECK in SQLite means rebuilding
    # the table. Not worth a migration against live data for a label.
    if row["estab_type"] == "individual" and row["sub_status"] != "active":
        return redirect("/account/billing")
    return None


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


@router.get("/home")
def marketing_home(request):
    """The public homepage, always, even when signed in.

    "/" redirects a signed-in user to their dashboard, which is right for
    someone typing the address but wrong for the logo in the app shell: that
    should take you to the public site, not bounce you back where you came
    from. This route is what the logo points at."""
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
                (establishment_id, "individual", 1, None, "expired", "card", now),
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


@router.get("/account/password")
def account_password_form(request):
    user, err = require(request)
    if err:
        return err
    return render("account_password.html", user=user, flash=flash_from_query(request))


@router.post("/account/password")
def account_password_submit(request):
    user, err = require(request)
    if err:
        return err

    current_password = request.field("current_password", "")
    new_password = request.field("new_password", "")
    confirm_password = request.field("confirm_password", "")

    if len(new_password) < 8:
        return with_flash("/account/password", "New password needs at least 8 characters.", "error")
    if new_password != confirm_password:
        return with_flash("/account/password", "The two new passwords do not match.", "error")
    if new_password == current_password:
        return with_flash("/account/password",
                          "That is the password you already have. Choose a different one.", "error")

    conn = db.get_conn()
    try:
        # Re-authenticate rather than trusting the session alone: without this,
        # anyone holding a live session token could lock the real owner out of
        # their own account.
        if not authlib.authenticate(conn, user["email"], current_password):
            return with_flash("/account/password", "Current password is not correct.", "error")
        authlib.set_password(conn, user["id"], new_password)
        authlib.destroy_other_sessions(conn, user["id"], request.cookie(authlib.SESSION_COOKIE))
        conn.commit()
    finally:
        conn.close()

    home = {"admin": "/admin", "mentor": "/mentor",
            "parent_carer": "/parent", "phil_staff": "/staff"}.get(user["role"], "/")
    return with_flash(home, "Password changed. Any other device signed in as you has been signed out.", "ok")


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


@router.get("/courses/module/<module_number>")
def course_by_module(request):
    """Finds a course by its module number (01-20) rather than its database id.

    The marketing homepage lists courses by module number, which is the stable,
    human-facing identifier. Database ids happen to match today but nothing
    guarantees that after a reseed, and a homepage full of links to the wrong
    courses would be a quiet, embarrassing failure."""
    try:
        num = int(request.params["module_number"])
    except (KeyError, ValueError):
        return redirect("/courses")
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM courses WHERE module_number=? AND status='published'", (num,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return redirect("/courses")
    return redirect(f"/courses/{row['id']}")


def related_courses(conn, course):
    """The other courses this one points at, as records rather than text.

    The stored line is free text naming module numbers ("Anger management
    (Module 11) or Emotional regulation (Module 3)"). Only the numbers are
    read: the titles come from the database, so renaming a course can't leave
    a stale copy of its old name sitting in another course's page. A number
    with no published course behind it is dropped rather than shown as a dead
    link.
    """
    text = (course["related_module"] if "related_module" in course.keys() else "") or ""
    out, seen = [], set()
    for num in re.findall(r"Module (\d+)", text):
        num = int(num)
        if num in seen or num == course["module_number"]:
            continue
        seen.add(num)
        row = conn.execute(
            """SELECT id, module_number, title FROM courses
               WHERE module_number=? AND status='published'""", (num,)).fetchone()
        if row:
            out.append(row)
    return out


@router.get("/courses/<course_id>")
def course_detail(request):
    user = current_user(request)
    conn = db.get_conn()
    try:
        course = conn.execute("SELECT * FROM courses WHERE id=?", (request.params["course_id"],)).fetchone()
        weeks = conn.execute(
            "SELECT * FROM weeks WHERE course_id=? ORDER BY week_number", (request.params["course_id"],)
        ).fetchall()
        related = related_courses(conn, course) if course else []
    finally:
        conn.close()
    if not course:
        return Response("Course not found", status="404 Not Found")
    weeks = [dict(w, resources=json.loads(w["resources"] or "[]")) for w in weeks]

    # The course content is the product. A signed-out visitor sees week 1 in
    # full, which is enough for a school to judge quality, and the rest is
    # held back. Anyone signed in has paid or is on a pilot, which is the
    # right bar: evaluating properly is the whole point of a pilot.
    limit = weeks_allowed(user)
    outline_weeks = []
    locked_weeks = 0
    if limit < len(weeks):
        rest = weeks[limit:]
        weeks = weeks[:limit]
        if user:
            # A pilot sees where the course goes, in title and objective only.
            # Hiding the ending entirely reads as an incomplete product rather
            # than a gated one, and a school is judging the whole arc.
            # staff_only travels with the outline too, or the staff write-up
            # gets counted as another session with the pupil.
            outline_weeks = [{"week_number": w["week_number"], "title": w["title"],
                              "objective": w["objective"],
                              "staff_only": w["staff_only"] if "staff_only" in w.keys() else 0}
                             for w in rest]
        else:
            locked_weeks = len(rest)
    return render("course_detail.html", user=user, course=course, weeks=weeks,
                  outline_weeks=outline_weeks, locked_weeks=locked_weeks,
                  related=related,
                  weeks_limit=limit, flash=flash_from_query(request))

@router.get("/courses/<course_id>/resources/pdf")
def course_resources_pdf(request):
    # The resource packs are the deliverable a school actually pays for, so
    # they are never public. A pilot is fine — evaluating properly is the point
    # of a pilot — but a parent has no reason to hold twenty packs of mentoring
    # material, so this is limited to the roles that deliver sessions.
    user, err = require(request, roles=["mentor", "admin", "phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        course = conn.execute("SELECT * FROM courses WHERE id=?", (request.params["course_id"],)).fetchone()
    finally:
        conn.close()
    if not course:
        return Response("Course not found", status="404 Not Found")
    packs = _load_resource_packs()
    entry = None
    course_num = None
    for k, v in packs.items():
        if v.get("title") == course["title"]:
            entry = v
            course_num = k
            break
    if not entry:
        return Response("Resource pack not available for this course yet", status="404 Not Found")

    items = entry.get("items", [])

    # ?week=N narrows the pack to that session's own resources. A mentor mid
    # session wants the two sheets for today, not all eleven for the course.
    week_param = (request.query.get("week") or [None])[0]
    if week_param and week_param.isdigit():
        wk = conn0 = db.get_conn()
        try:
            row = conn0.execute(
                "SELECT resources FROM weeks WHERE course_id=? AND week_number=?",
                (course["id"], int(week_param)),
            ).fetchone()
        finally:
            conn0.close()
        if row:
            wanted = {_norm_resource(n) for n in json.loads(row["resources"] or "[]")}
            # Match on aliases too, exactly as the session page does.
            scoped = []
            for it in items:
                names = {_norm_resource(it.get("name"))}
                names |= {_norm_resource(a) for a in it.get("aliases", [])}
                if names & wanted:
                    scoped.append(it)
            if scoped:
                items = scoped

    limit = weeks_allowed(user)
    conn = db.get_conn()
    try:
        allowed = weeks_for_pack(conn, course["id"], limit)
    finally:
        conn.close()
    if allowed is not None:
        items = [it for it in items if _norm_resource(it.get("name")) in allowed]
        if not items:
            return with_flash("/courses/" + str(course["id"]),
                              "The resource pack for these sessions unlocks on a paid plan.", "error")
    path = pdfgen.resource_pack_pdf(course_num, course["title"], items)
    return pdf_response(path, f"resource-pack-{course_num}.pdf")


# ------------------------------------------------------------------- mentor --

def schedule_for(conn, user, today=None):
    """The mentor's week: who has been seen, who is waiting, what is overdue.

    Mentoring runs to a weekly rhythm, so the question this page answers is not
    "what did I put in the diary" — most courses never get planned dates — but
    "who have I seen this week, and who have I not". Every active course is
    therefore treated as due a session each week unless the mentor has
    deliberately planned it for later.

    Returns (summary, buckets). Buckets are attention / this_week / seen /
    coming, and each holds display-ready rows.
    """
    today = today or datetime.date.today()
    today_iso = today.isoformat()
    monday = today - datetime.timedelta(days=today.weekday())
    monday_iso = monday.isoformat()
    end_of_week = (monday + datetime.timedelta(days=6)).isoformat()

    def name_of(row):
        return ((row["forename"] or "") + " " + (row["surname"] or "")).strip()

    def days_between(iso):
        try:
            return (today - datetime.date.fromisoformat(iso)).days
        except (TypeError, ValueError):
            return None

    def ahead(iso):
        d = days_between(iso)
        if d is None:
            return ""
        d = -d
        if d <= 0:
            return "today"
        if d == 1:
            return "tomorrow"
        if d < 14:
            return "in %d days" % d
        return "in %d weeks" % (d // 7)

    def ago(iso):
        d = days_between(iso)
        if d is None:
            return ""
        if d == 0:
            return "today"
        if d == 1:
            return "yesterday"
        if d < 14:
            return "%d days ago" % d
        return "%d weeks ago" % (d // 7)

    attention, this_week, seen, coming = [], [], [], []

    courses = conn.execute(
        """SELECT e.id AS enrolment_id, e.pupil_id, e.current_week,
                  p.forename, p.surname, c.title AS course_title,
                  (SELECT max(r.date) FROM session_records r
                    WHERE r.enrolment_id = e.id) AS last_session,
                  (SELECT min(s.planned_date) FROM session_schedule s
                    WHERE s.enrolment_id = e.id AND s.week_number > e.current_week
                      AND s.planned_date IS NOT NULL) AS next_planned
           FROM enrolments e
           JOIN pupils p ON p.id = e.pupil_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.mentor_id = ? AND e.status = 'active' AND p.status = 'active'
           ORDER BY p.surname, p.forename, c.title""",
        (user["id"],)).fetchall()

    total_courses = len(courses)
    for row in courses:
        last = row["last_session"]
        planned = row["next_planned"]
        gap = days_between(last) if last else None
        item = {
            "kind": "session",
            "pupil_id": row["pupil_id"],
            "pupil_name": name_of(row),
            "course_title": row["course_title"],
            "last_session": last,
            "last_label": ("last seen %s" % ago(last)) if last else "not started",
            "action_url": "/mentor/session/%s" % row["enrolment_id"],
            "plan_url": "/mentor/schedule/%s" % row["enrolment_id"],
            "planned": planned,
        }

        # The staff-only write-up is the one piece of work with no pupil in it,
        # so nothing in the week prompts it. It is named rather than counted as
        # just another session.
        if row["current_week"] >= SESSIONS_PER_COURSE - 1:
            item.update({
                "kind": "summary",
                "title": "Course summary and next steps",
                "subtitle": "The staff write-up that closes the course.",
                "action_label": "Write summary",
                "chip": "",
                "light": "amber",
            })
            if gap is not None and gap >= 7:
                item["chip"] = "waiting %s" % ago(last).replace(" ago", "")
                item["chip_kind"] = "late"
                item["light"] = "red"
                attention.append(item)
            else:
                this_week.append(item)
            continue

        item["title"] = "Session %d of %d" % (row["current_week"] + 1, SESSIONS_PER_COURSE)
        item["action_label"] = "Record session"

        # A chip is only worth showing when it tells the mentor something they
        # can't see from the row itself. "No date set" on every row is noise, so
        # no date means no chip.
        if last and last >= monday_iso:
            # The row's title is normally the session coming next. On a done row
            # that's the wrong one: name the session that was actually run.
            item["title"] = "Session %d of %d" % (row["current_week"], SESSIONS_PER_COURSE)
            item["chip"] = "done " + ago(last)
            item["chip_kind"] = "done"
            item["light"] = "green"
            item["action_label"] = "Open record"
            item["action_url"] = "/mentor/pupils/%s" % row["pupil_id"]
            seen.append(item)
            continue

        if planned and planned < today_iso:
            item["chip"] = "missed " + pretty_date(planned)
            item["chip_kind"] = "late"
            item["light"] = "red"
            attention.append(item)
        elif gap is not None and gap >= 14:
            item["chip"] = "not seen for %s" % ago(last).replace(" ago", "")
            item["chip_kind"] = "late"
            item["light"] = "red"
            attention.append(item)
        elif planned and planned <= end_of_week:
            item["chip"] = pretty_date(planned)
            item["chip_kind"] = "due"
            item["light"] = "amber"
            this_week.append(item)
        elif planned:
            item["chip"] = pretty_date(planned)
            item["chip_kind"] = "due"
            item["ahead"] = ahead(planned)
            item["light"] = "grey"
            coming.append(item)
        else:
            item["light"] = "amber"
            this_week.append(item)

    # Reviews follow the pupil, not the enrolment — the same rule as
    # may_handle_review — so a reassigned pupil's review appears for whoever
    # mentors them now.
    reviews = conn.execute(
        """SELECT e.id, e.review_date, e.review_note, e.pupil_id,
                  p.forename, p.surname, c.title AS course_title
           FROM enrolments e
           JOIN pupils p ON p.id = e.pupil_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.review_date IS NOT NULL
             AND e.review_done = 0 AND p.status = 'active'
             AND (EXISTS (SELECT 1 FROM enrolments a
                          WHERE a.pupil_id = e.pupil_id AND a.status = 'active'
                            AND a.mentor_id = ?)
                  OR (NOT EXISTS (SELECT 1 FROM enrolments a
                                  WHERE a.pupil_id = e.pupil_id
                                    AND a.status = 'active')
                      AND (e.mentor_id = ?
                           -- Or the mentor who ran it has left: the chat falls
                           -- to whoever is still here rather than to nobody.
                           OR EXISTS (SELECT 1 FROM users u
                                      WHERE u.id = e.mentor_id
                                        AND u.status != 'active'))))
           ORDER BY e.review_date""",
        (user["id"], user["id"])).fetchall()
    for row in reviews:
        overdue_after = review_overdue_from(row["review_date"])
        week_of = review_week_of(row["review_date"])
        item = {
            "kind": "review",
            "pupil_id": row["pupil_id"],
            "pupil_name": name_of(row),
            "course_title": row["course_title"],
            "title": "Follow-up chat",
            "subtitle": "Sit down with them: has the course helped, and is the behaviour still showing?",
            "last_label": row["review_note"] or "",
            "action_label": "Record chat",
            "action_url": "/mentor/enrolment/%s/follow-up" % row["id"],
        }
        # Missed once the week it was due in has passed.
        if overdue_after and today_iso > overdue_after:
            item["chip"] = "missed " + pretty_week(week_of)
            item["chip_kind"] = "late"
            item["light"] = "red"
            attention.append(item)
        elif row["review_date"] <= end_of_week:
            item["chip"] = pretty_week(week_of)
            item["chip_kind"] = "due"
            item["light"] = "amber"
            this_week.append(item)
        else:
            item["chip"] = pretty_week(week_of)
            item["chip_kind"] = "due"
            item["ahead"] = ahead(row["review_date"])
            item["light"] = "grey"
            coming.append(item)

    for group in (attention, this_week, coming, seen):
        for item in group:
            # The chip and the last-seen line often say the same thing ("not seen
            # for 2 weeks" beside "last seen 2 weeks ago"). Keep the chip.
            chip = (item.get("chip") or "").replace("not seen for ", "").replace("done ", "")
            last = (item.get("last_label") or "").replace("last seen ", "").replace(" ago", "")
            chip = chip.replace(" ago", "")
            if chip and last and chip.strip() == last.strip():
                item["last_label"] = ""

    coming.sort(key=lambda i: i.get("planned") or "9999")

    # Every session date set for a future week, whatever state the course is in.
    # Dates inside this week are deliberately left out: they are already sitting
    # in "This week" or "Behind", and listing them twice makes the page lie about
    # how much there is to do.
    booked_sessions = []
    for row in conn.execute(
        """SELECT s.planned_date, s.week_number, e.id AS enrolment_id, e.pupil_id,
                  p.forename, p.surname, c.title AS course_title
           FROM session_schedule s
           JOIN enrolments e ON e.id = s.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.mentor_id = ? AND e.status = 'active' AND p.status = 'active'
             AND s.planned_date IS NOT NULL AND s.planned_date > ?
             AND s.week_number > e.current_week
           ORDER BY s.planned_date, p.surname""",
        (user["id"], end_of_week)).fetchall():
        booked_sessions.append({
            "kind": "session",
            "light": "grey",
            "pupil_id": row["pupil_id"],
            "pupil_name": name_of(row),
            "course_title": row["course_title"],
            "title": "Session %d of %d" % (row["week_number"], SESSIONS_PER_COURSE),
            "chip": pretty_date(row["planned_date"]),
            "chip_kind": "due",
            "ahead": ahead(row["planned_date"]),
            "last_label": "",
            "planned": row["planned_date"],
            "action_label": "Open record",
            "action_url": "/mentor/pupils/%s" % row["pupil_id"],
            "plan_url": "/mentor/schedule/%s" % row["enrolment_id"],
        })

    # A mentor counts in pupils, not enrolments: one child on five courses is
    # one person to find time for, so "0 of 5" read as five children.
    pupils = {}
    for row in courses:
        p = pupils.setdefault(row["pupil_id"], {
            "pupil_id": row["pupil_id"],
            "name": name_of(row),
            "courses": 0,
            "seen_courses": 0,
            "last_session": None,
        })
        p["courses"] += 1
        last = row["last_session"]
        if last and (p["last_session"] is None or last > p["last_session"]):
            p["last_session"] = last
        if last and last >= monday_iso:
            p["seen_courses"] += 1
    pupil_rows = sorted(pupils.values(), key=lambda p: (p["seen_courses"] > 0, p["name"]))
    for p in pupil_rows:
        p["seen"] = p["seen_courses"] > 0
        gap = days_between(p["last_session"]) if p["last_session"] else None
        # Three states, not two. "Not this week" and "not since June" are very
        # different problems, and a single amber made them look identical. The
        # 14-day threshold is the one the course groups already use, so the whole
        # page means the same thing by "slipping".
        if p["seen"]:
            p["light"] = "green"
            p["status"] = "seen " + ago(p["last_session"])
        elif gap is not None and gap >= 14:
            p["light"] = "red"
            p["status"] = "last seen " + ago(p["last_session"])
        elif p["last_session"]:
            p["light"] = "amber"
            p["status"] = "last seen " + ago(p["last_session"])
        else:
            p["light"] = "red"
            p["status"] = "no sessions yet"

    summary = {
        "total_courses": total_courses,
        "pupils": len(pupil_rows),
        "pupils_seen": sum(1 for p in pupil_rows if p["seen"]),
        # Both counts, side by side. One pupil on four courses is one person to
        # find time for and four sessions to run, and the page was only ever
        # showing one of those two numbers at a time.
        "pupils_not_seen": sum(1 for p in pupil_rows if not p["seen"]),
        "courses_seen": sum(1 for i in seen if i["kind"] == "session"),
        "seen": len(seen),
        "attention": len(attention),
        "this_week": len(this_week),
        # This week only. Anything behind is already counted in "attention", and
        # listing it twice made the breakdown add up to more than the work.
        "sessions_due": sum(1 for i in this_week if i["kind"] == "session"),
        "writeups_due": sum(1 for i in this_week if i["kind"] == "summary"),
        "reviews_due": sum(1 for i in this_week if i["kind"] == "review"),
    }
    # "rows", not "items": in a template dict.items is the built-in method, so a
    # bucket keyed that way is always truthy and every group renders as full.
    buckets = [
        {"key": "attention", "title": "Behind", "rows": attention,
         "blurb": "Do these first."},
        {"key": "this_week", "title": "This week", "rows": this_week,
         "blurb": "Not seen yet this week."},
        # Booked work, a group each. These answer "what's in the diary", not
        # "what's outstanding", so they are built from the dates themselves
        # rather than from what's left over above — a course seen this week
        # still has next week's session booked, and a mentor wants to see it.
        {"key": "coming_sessions", "title": "Scheduled mentoring sessions",
         "rows": booked_sessions,
         "blurb": "Sessions you've set a date for, beyond this week.",
         # Shown even when empty: a mentor who has never opened the planner has
         # no other way to learn it exists, and an empty diary is itself worth
         # seeing.
         "always": True,
         "empty": "No sessions booked yet. Open a pupil's course and use "
                  "\u201cSet session dates\u201d to plan ahead."},
        {"key": "coming_reviews", "title": "Follow-up chats",
         "rows": [r for r in coming if r["kind"] == "review"],
         "blurb": "Booked when a course finished.",
         "always": True,
         "empty": "No follow-ups booked. One is agreed each time a course is "
                  "closed."},
        {"key": "seen", "title": "Done this week", "rows": seen,
         "blurb": ""},
    ]

    # Within a group, split by kind. Three different jobs were sitting in one
    # run of rows — a session with a pupil, a write-up for staff, and a chat
    # weeks after the course — and they read as interchangeable.
    kind_labels = [
        ("session", "Mentoring session", "Mentoring sessions"),
        ("summary", "Course summary", "Course summaries"),
        ("review", "Follow-up chat", "Follow-up chats"),
    ]
    for bucket in buckets:
        sections = []
        for kind, one, many in kind_labels:
            rows = [r for r in bucket["rows"] if r["kind"] == kind]
            if rows:
                sections.append({
                    "kind": kind,
                    "label": one if len(rows) == 1 else many,
                    "count": len(rows),
                    "rows": rows,
                })
        # A label above a single kind is just the group heading again, so it
        # only earns its place when there is more than one kind to tell apart.
        bucket["sections"] = sections
        bucket["show_labels"] = len(sections) > 1
    return summary, buckets, pupil_rows


@router.get("/mentor/schedule")
def mentor_schedule(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        summary, buckets, pupil_rows = schedule_for(conn, user)
    finally:
        conn.close()
    return render("schedule.html", user=user, summary=summary, buckets=buckets,
                  pupils=pupil_rows, flash=flash_from_query(request))


@router.get("/mentor")
def mentor_home(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        pupils = conn.execute(
            """SELECT pupils.*,
                      (SELECT count(*) FROM enrolments WHERE enrolments.pupil_id = pupils.id AND enrolments.mentor_id = ? AND enrolments.status='active') as active_enrolments
               FROM pupils
               WHERE establishment_id=? AND status='active'
               AND id IN (SELECT pupil_id FROM enrolments WHERE mentor_id=? AND status='active')
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
        # Counts the same items the Schedule page puts under "This week", so the
        # number and the page can never disagree. It used to count active courses
        # with no session recorded in seven days, which is a different thing
        # entirely: a course planned for next Tuesday looked identical to one
        # nobody had touched since September.
        sched_summary, _, _ = schedule_for(conn, user)
        due_this_week = sched_summary["this_week"] + sched_summary["attention"]
    finally:
        conn.close()
    # The list is about pupils, not enrolments. A pupil on three courses was
    # appearing as three rows with the same name, which reads as three children.
    by_pupil = {}
    for e in enrolments:
        entry = by_pupil.setdefault(e["pupil_id"], {
            "pupil_id": e["pupil_id"],
            "forename": e["forename"],
            "surname": e["surname"],
            "courses": [],
        })
        entry["courses"].append(e)
    mentoring_list = sorted(by_pupil.values(), key=lambda p: (p["surname"], p["forename"]))
    for entry in mentoring_list:
        entry["active"] = sum(1 for c in entry["courses"] if c["status"] == "active")
        entry["completed"] = sum(1 for c in entry["courses"] if c["status"] == "completed")
    # A pupil whose courses with this mentor have all finished is no longer
    # someone they are mentoring, so they drop off this list. The completed
    # courses stay attributed to whoever ran them and stay visible on the
    # pupil's own record. A pupil who still has active work keeps their
    # finished courses shown alongside it.
    mentoring_list = [entry for entry in mentoring_list if entry["active"] > 0]

    # Reviews the mentor agreed at the end of a course. Only ones that have come
    # round: a review three weeks away isn't work yet, and listing it would
    # teach them to ignore the list.
    today = datetime.date.today().isoformat()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT e.id, e.review_date, e.review_note, e.pupil_id,
                      p.forename, p.surname, c.title AS course_title
               FROM enrolments e
               JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id
               WHERE e.review_date IS NOT NULL
                 AND e.review_done = 0 AND p.status = 'active'
                 AND (EXISTS (SELECT 1 FROM enrolments a
                              WHERE a.pupil_id = e.pupil_id AND a.status = 'active'
                                AND a.mentor_id = ?)
                      OR (e.mentor_id = ?
                          AND NOT EXISTS (SELECT 1 FROM enrolments a
                                          WHERE a.pupil_id = e.pupil_id
                                            AND a.status = 'active')))
               ORDER BY e.review_date""",
            (user["id"], user["id"])).fetchall()
    finally:
        conn.close()
    reviews_due = []
    for row in rows:
        if row["review_date"] > today:
            continue
        overdue_after = review_overdue_from(row["review_date"])
        reviews_due.append(dict(row,
                                week_of=review_week_of(row["review_date"]),
                                overdue=bool(overdue_after and today > overdue_after)))

    return render("mentor_home.html", user=user, pupils=pupils, enrolments=enrolments,
                  mentoring_list=mentoring_list,
                  due_this_week=due_this_week, reviews_due=reviews_due,
                  flash=flash_from_query(request))


@router.get("/mentor/pupils/new")
def new_pupil_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    return render("pupil_new.html", user=user, flash=flash_from_query(request))


@router.post("/mentor/pupils/new")
def new_pupil_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        if not may_access_pupil(conn, request.params["pupil_id"], user):
            return Response("Pupil not found", status="404 Not Found")
        pupil = conn.execute("SELECT * FROM pupils WHERE id=?",
                              (request.params["pupil_id"],)).fetchone()
        enrolments = conn.execute(
            """SELECT enrolments.*, courses.id as course_id, courses.title as course_title, courses.id as course_id,
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
            follow_up = follow_up_for(conn, e["id"])
            enrolment_data.append({"enrolment": e, "records": records, "certificate": cert,
                                    "reflection": reflection,
                                    "follow_up": follow_up,
                                    "follow_up_earliest": follow_up_earliest(conn, e["id"]),
                                    "next_planned": next_planned["planned_date"] if next_planned else None})
    finally:
        conn.close()
    # today is used to mark a review overdue; the default is the same three-week
    # gap the completion screen suggests, so both routes agree.
    return render("pupil_profile.html", user=user, pupil=pupil, enrolment_data=enrolment_data,
                  helped_labels=HELPED_LABELS, behaviour_labels=BEHAVIOUR_LABELS,
                  next_step_labels=NEXT_STEP_LABELS,
                  today=datetime.date.today().isoformat(),
                  review_week_of=review_week_of,
                  review_overdue_from=review_overdue_from,
                  default_review_date=(datetime.date.today() + datetime.timedelta(days=21)).isoformat(),
                  flash=flash_from_query(request))


@router.post("/mentor/pupils/<pupil_id>/archive")
def archive_pupil(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        conn.execute("UPDATE pupils SET status='active' WHERE id=? AND establishment_id=?",
                      (request.params["pupil_id"], user["establishment_id"]))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Pupil reactivated", "They're active again and back on their mentor's list.", f"/mentor/pupils/{request.params['pupil_id']}", back_label="View pupil")


@router.get("/mentor/pupils")
def mentor_pupils(request):
    """A mentor's own pupils. Same page as the admin list, scoped to them."""
    return _pupils_list(request, roles=["mentor", "admin"], own_only=True)


@router.get("/admin/pupils")
def admin_pupils(request):
    return _pupils_list(request, roles=["admin"], own_only=False)


def _pupils_list(request, roles, own_only):
    user, err = require(request, roles=roles)
    if err:
        return err
    status_filter = request.query.get("status", ["active"])[0]
    conn = db.get_conn()
    try:
        if own_only:
            # A mentor's own list of active pupils means the ones they are
            # currently mentoring, so a pupil whose courses with them have all
            # finished drops off, matching the mentoring list on their home
            # page. The archived view keeps the looser rule: an archived pupil
            # rarely has an active enrolment, and a mentor looking back through
            # archived pupils still needs to find the ones they worked with.
            if status_filter == "active":
                pupils = conn.execute(
                    """SELECT * FROM pupils WHERE establishment_id=? AND status=?
                         AND id IN (SELECT pupil_id FROM enrolments
                                    WHERE mentor_id=? AND status='active')
                       ORDER BY surname, forename""",
                    (user["establishment_id"], status_filter, user["id"]),
                ).fetchall()
            else:
                pupils = conn.execute(
                    """SELECT * FROM pupils WHERE establishment_id=? AND status=?
                         AND id IN (SELECT pupil_id FROM enrolments WHERE mentor_id=?)
                       ORDER BY surname, forename""",
                    (user["establishment_id"], status_filter, user["id"]),
                ).fetchall()
        else:
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
    return render("admin_pupils.html", user=user, pupil_data=pupil_data,
                  status_filter=status_filter, own_only=own_only,
                  base_path="/mentor/pupils" if own_only else "/admin/pupils",
                  flash=flash_from_query(request))


@router.get("/admin/reassign-mentor")
def admin_reassign_mentor_list(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT enrolments.id as enrolment_id, pupils.id as pupil_id, pupils.forename, pupils.surname,
                      courses.title as course_title, users.name as mentor_name
               FROM enrolments
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
               JOIN users ON users.id = enrolments.mentor_id
               WHERE pupils.establishment_id=? AND pupils.status='active' AND enrolments.status='active'
               ORDER BY pupils.surname, pupils.forename, pupils.id, courses.title""",
            (user["establishment_id"],),
        ).fetchall()
    finally:
        conn.close()

    pupils = []
    by_pupil = {}
    for row in rows:
        group = by_pupil.get(row["pupil_id"])
        if group is None:
            name = ((row["forename"] or "") + " " + (row["surname"] or "")).strip()
            group = {
                "pupil_id": row["pupil_id"],
                "name": name,
                "courses": [],
                "mentors": [],
            }
            by_pupil[row["pupil_id"]] = group
            pupils.append(group)
        group["courses"].append({
            "enrolment_id": row["enrolment_id"],
            "course_title": row["course_title"],
            "mentor_name": row["mentor_name"],
        })
        # Reassigning moves every active course a pupil holds with that mentor,
        # so the pupil-level button only needs one enrolment to act on.
        if not group.get("reassign_enrolment_id"):
            group["reassign_enrolment_id"] = row["enrolment_id"]
        if row["mentor_name"] not in group["mentors"]:
            group["mentors"].append(row["mentor_name"])

    for group in pupils:
        count = len(group["courses"])
        group["course_label"] = "1 course" if count == 1 else "%d courses" % count
        if len(group["mentors"]) == 1:
            group["mentor_label"] = group["mentors"][0]
        else:
            group["mentor_label"] = "%d mentors" % len(group["mentors"])

    return render("reassign_mentor_list.html", user=user, pupils=pupils, flash=flash_from_query(request))


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
        # How many other active courses this pupil has with the same mentor, so
        # the form can offer to move them together rather than leaving an admin
        # to repeat the job once per course.
        other_active = conn.execute(
            """SELECT COUNT(*) AS n FROM enrolments
               WHERE pupil_id=? AND mentor_id=? AND status='active' AND id != ?""",
            (enrolment["pupil_id"], enrolment["mentor_id"], enrolment["id"])).fetchone()["n"]
    finally:
        conn.close()
    return render("enrolment_reassign.html", user=user, enrolment=enrolment, mentors=mentors,
                  other_active=other_active, flash=flash_from_query(request))


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
            """SELECT enrolments.*, pupils.forename, pupils.surname, pupils.establishment_id,
                      courses.title AS course_title
               FROM enrolments
               JOIN pupils ON pupils.id = enrolments.pupil_id
               JOIN courses ON courses.id = enrolments.course_id
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

        # Reassigning a pupil moves all of their active mentoring. Splitting a
        # pupil between two mentors is not something a school asks for, and a
        # part-moved pupil is worse than either: the new mentor sees an
        # incomplete picture and nobody notices the gap.
        #
        # Completed and withdrawn courses stay with the original mentor, because
        # they are a record of who actually did that work.
        moved = conn.execute(
            """SELECT id FROM enrolments
               WHERE pupil_id=? AND mentor_id=? AND status='active'""",
            (enrolment["pupil_id"], enrolment["mentor_id"])).fetchall()
        ids = [r["id"] for r in moved] or [enrolment["id"]]
        conn.executemany("UPDATE enrolments SET mentor_id=? WHERE id=?",
                         [(new_mentor_id, i) for i in ids])
        db.log_action(conn, user["id"], "enrolment_reassigned", "enrolment", enrolment["id"],
                      f"{enrolment['forename']} {enrolment['surname']}: {len(ids)} active course(s) "
                      f"moved to {new_mentor['name']}")
        conn.commit()
    finally:
        conn.close()
    name = f"{enrolment['forename']} {enrolment['surname']}"
    if len(ids) == 1:
        detail = f"{name}'s course is now with {new_mentor['name']}."
    else:
        detail = (f"All {len(ids)} of {name}'s active courses are now with "
                  f"{new_mentor['name']}.")
    return render_done(user, "Pupil reassigned", detail,
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
                                   "Choose who should take over their active mentoring list.", "error")
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
                      f"{mentor['name']} removed" + (f", mentoring list moved to {new_mentor['name']}" if active_count > 0 else ""))
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Mentor removed", f"{mentor['name']} has lost access immediately. Every pupil record and past session they wrote stays exactly as it is.", "/admin", back_label="Continue")


@router.get("/mentor/pupils/<pupil_id>/link-parent")
def link_parent_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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


@router.get("/admin/parent-requests")
def admin_parent_requests(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pending_requests = conn.execute(
            """SELECT parent_access_requests.*, users.name as requested_by_name,
                      pupils.forename, pupils.surname
               FROM parent_access_requests
               JOIN users ON users.id = parent_access_requests.requested_by
               JOIN pupils ON pupils.id = parent_access_requests.pupil_id
               WHERE parent_access_requests.establishment_id=? AND parent_access_requests.status='pending'
               ORDER BY parent_access_requests.created_at""",
            (user["establishment_id"],),
        ).fetchall()
    finally:
        conn.close()
    return render("parent_requests.html", user=user, pending_requests=pending_requests,
                  flash=flash_from_query(request))


@router.get("/admin/reassign-admin")
def admin_reassign_admin_form(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        mentors = conn.execute(
            "SELECT id, name, email FROM users WHERE establishment_id=? AND role='mentor' AND status='active' ORDER BY name",
            (user["establishment_id"],),
        ).fetchall()
    finally:
        conn.close()
    return render("reassign_admin.html", user=user, mentors=mentors, flash=flash_from_query(request))


@router.post("/admin/reassign-admin")
def admin_reassign_admin_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    new_admin_id = request.field("mentor_id")
    if not new_admin_id:
        return with_flash("/admin/reassign-admin", "Choose a mentor to become the new admin.", "error")
    conn = db.get_conn()
    try:
        new_admin = conn.execute(
            "SELECT * FROM users WHERE id=? AND establishment_id=? AND role='mentor' AND status='active'",
            (new_admin_id, user["establishment_id"]),
        ).fetchone()
        if not new_admin:
            return with_flash("/admin/reassign-admin", "That mentor could not be found.", "error")
        conn.execute("UPDATE users SET role='mentor' WHERE id=?", (user["id"],))
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (new_admin["id"],))
        db.log_action(conn, user["id"], "admin_role_reassigned", "user", new_admin["id"],
                      f"{user['name']} handed the admin role to {new_admin['name']}")
        conn.commit()
    finally:
        conn.close()
    return render_done(user, "Admin role reassigned",
                        f"{new_admin['name']} is now the admin for your establishment. You're now a mentor.",
                        "/mentor", back_label="Go to Mentor home")


@router.get("/mentor/enrol/<pupil_id>")
def enrol_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn_chk = db.get_conn()
    try:
        # A mentor at another school could otherwise open, autosave into and
        # submit sessions for this pupil just by changing the id in the URL.
        if not may_access_enrolment(conn_chk, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn_chk.close()
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
        # A pilot sees three sessions in the course library, so it should see
        # three here too. Without this a pilot mentor could enrol a pupil and
        # read every session plan by working through the course — the paid
        # content, reached by a different door.
        if next_week_number > weeks_allowed(user):
            return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}",
                              f"Session {next_week_number} is included on a paid plan. "
                              "Your pilot covers the first "
                              f"{weeks_allowed(user)} sessions.", "error")
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
        # Attach the actual content of this week's resources. Until now the
        # session screen showed only their names, so a mentor had to print the
        # pack to use anything. The pack is still there for what the pupil
        # writes on; this makes the mentor-facing material usable in the room.
        week["resource_items"] = resource_items_for(
            enrolment["course_module_number"], week["resources"])
        attach_figures(week["resource_items"])
        week["resource_steps"] = assign_resources_to_steps(week, week["resource_items"])
        for step, group in week["resource_steps"].items():
            for item in group:
                item["_step"] = step
        week["resource_lines"] = assign_resources_to_lines(week, week["resource_items"])
    prev_record = completed_records[-1] if completed_records else None
    # What the pupil took away last week. Several courses open by reviewing it,
    # so the mentor should not have to go and find it.
    prev_week_items = []
    prev_week = next((w for w in all_weeks if w["week_number"] == next_week_number - 1), None)
    if prev_week is not None:
        prev_week_items = resource_items_for(
            enrolment["course_module_number"], json.loads(prev_week["resources"] or "[]"))
    # range(1, 6) stopped at session 5, so the staff-only session never appeared
    # on the rail. Labels come from here too, rather than being derived in the
    # template, so a done session reads "S3 done" instead of a bare number.
    progress = [
        {
            "number": n,
            "label": f"S{n}" if n < SESSIONS_PER_COURSE else "Plan",
            "status": ("done" if n < next_week_number
                       else "current" if n == next_week_number else "locked"),
        }
        for n in range(1, SESSIONS_PER_COURSE + 1)
    ]
    upcoming_weeks = [w for w in all_weeks if w["week_number"] > next_week_number]
    # No-store, so the browser's own Back button re-fetches instead of showing a
    # cached copy of a form that has already been submitted. Combined with the
    # for_week check on POST, a stale form can neither be shown nor accepted.
    conn2 = db.get_conn()
    try:
        entries = resource_entries_for(conn2, enrolment["id"], week["id"])
    finally:
        conn2.close()

    response = render("session_form.html", user=user, enrolment=enrolment, week=week,
                  entries=entries,
                  next_week_number=next_week_number, completed_records=completed_records,
                  prev_record=prev_record, prev_week_items=prev_week_items,
                  draft=draft, progress=progress,
                  upcoming_weeks=upcoming_weeks, flash=flash_from_query(request))
    response.headers.append(("Cache-Control", "no-store, must-revalidate"))
    return response

@router.post("/mentor/session/<enrolment_id>/autosave")
def session_autosave(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn_chk = db.get_conn()
    try:
        # A mentor at another school could otherwise open, autosave into and
        # submit sessions for this pupil just by changing the id in the URL.
        if not may_access_enrolment(conn_chk, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn_chk.close()
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn_chk = db.get_conn()
    try:
        # A mentor at another school could otherwise open, autosave into and
        # submit sessions for this pupil just by changing the id in the URL.
        if not may_access_enrolment(conn_chk, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn_chk.close()
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

    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT enrolments.*, pupils.forename, pupils.surname, courses.title as course_title
            FROM enrolments JOIN pupils ON pupils.id=enrolments.pupil_id
            JOIN courses ON courses.id=enrolments.course_id WHERE enrolments.id=?""",
            (enrolment_id,),
        ).fetchone()
        if enrolment is None:
            return with_flash("/mentor", "That enrolment no longer exists.", "error")
        next_week_number = enrolment["current_week"] + 1
        week = conn.execute("SELECT * FROM weeks WHERE course_id=? AND week_number=?",
                             (enrolment["course_id"], next_week_number)).fetchone()
        submitted_for = request.field("for_week", "").strip()
        if submitted_for.isdigit() and int(submitted_for) != next_week_number:
            return with_flash(
                f"/mentor/pupils/{enrolment['pupil_id']}",
                f"Session {submitted_for} is already recorded. Nothing was saved twice.",
                "error")

        if week is None:
            # Every session is already recorded. Reached by a double submit, a
            # refreshed form, or a second tab, so say so plainly rather than
            # crashing on week["id"].
            return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}",
                              "All five sessions are already recorded for this course.", "ok")

        # On the staff session the boxes aren't notes about a session — they are
        # the sections of the support plan. Labelling them as such means the plan
        # reaches the reports already structured, instead of as one long block
        # the next teacher has to unpick.
        staff_session = bool(week["staff_only"]) if "staff_only" in week.keys() else False
        if staff_session:
            sections = [
                ("Where they started", checkin_note),
                ("Triggers and early signs", input_note),
                ("What works", activity_note),
                ("If it escalates", reflect_note),
                ("Plan moving forward", next_session_note),
            ]
        else:
            sections = [
                ("Check-in", checkin_note),
                ("Input", input_note),
                ("Activity", activity_note),
            ]
        what_happened = "\n\n".join(f"{label}: {text}" for label, text in sections if text)

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
        resource_work = resource_work_for(conn, enrolment_id, week["id"])
        pdf_path = pdfgen.session_record_pdf(record, enrolment, pupil_name, enrolment["course_title"],
                                              week["title"], mentor_name,
                                              resource_work=resource_work)
        conn.execute("UPDATE session_records SET pdf_path=? WHERE id=?", (pdf_path, record_id))

        new_current_week = next_week_number
        new_status = "completed" if new_current_week >= SESSIONS_PER_COURSE else "active"
        conn.execute("UPDATE enrolments SET current_week=?, status=? WHERE id=?",
            (new_current_week, new_status, enrolment_id))

        conn.execute("DELETE FROM session_drafts WHERE enrolment_id=? AND week_number=?",
                     (enrolment_id, next_week_number))

        save_resource_entries(conn, enrolment_id, week["id"], request, user["id"])
        message = f"Week {next_week_number} session recorded."
        completed_now = new_status == "completed"
        if completed_now:
            # The certificate is issued by the wrap-up, not by the fifth session:
            # booking the follow-up chat is part of finishing a course, not an
            # optional extra. It takes a moment, so the pupil isn't waiting on
            # anything.
            message = "Course complete."

        conn.commit()
    finally:
        conn.close()

    # Finishing a five-week course with a pupil is worth marking properly. The
    # other four sessions keep the quiet flash message: a celebration every week
    # would be noise by week three.
    if completed_now:
        # Three weeks is the default because it's long enough for a strategy to
        # be tested in real life and short enough that the pupil still connects
        # it to the course.
        suggested = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()
        return render("course_complete.html", user=user,
                      pupil_name=pupil_name, course_title=enrolment["course_title"],
                      enrolment_id=enrolment_id, pupil_id=enrolment["pupil_id"],
                      suggested_review_date=suggested, reflection=None, flash=None)
    return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}", message, "ok")

@router.get("/mentor/schedule/<enrolment_id>")
def schedule_form(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn_chk = db.get_conn()
    try:
        # A mentor at another school could otherwise open, autosave into and
        # submit sessions for this pupil just by changing the id in the URL.
        if not may_access_enrolment(conn_chk, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn_chk.close()
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn_chk = db.get_conn()
    try:
        # A mentor at another school could otherwise open, autosave into and
        # submit sessions for this pupil just by changing the id in the URL.
        if not may_access_enrolment(conn_chk, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn_chk.close()
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


# The completion reflection is gone. Session 6's course summary and next steps
# asks the same questions of the same person at the same moment, so the two
# forms collected the same answer twice or left one of them blank. The
# completion_reflections table is left in place: what mentors wrote before the
# change is still there, it is simply no longer written to or displayed.


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


def looks_like_email(value):
    """Enough of a check to stop an account nobody can sign in to.

    Deliberately loose — real addresses are stranger than most patterns allow —
    but it does require an @ with something either side and a dot in the domain."""
    value = (value or "").strip()
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") \
        and not domain.endswith(".") and " " not in value


@router.post("/admin/mentors/new")
def new_mentor_submit(request):
    user, err = require(request, roles=["admin"])
    if err:
        return err
    # Collected as two fields, to match how pupils are added — a single "Name"
    # box invites someone to put a surname in the next field along. Stored joined,
    # because user.name is the display name in 79 places and splitting the column
    # would be a migration for no gain.
    forename = request.field("forename", "").strip()
    surname = request.field("surname", "").strip()
    name = " ".join(part for part in (forename, surname) if part) or request.field("name", "").strip()
    email = request.field("email", "").strip().lower()
    password = request.field("password", "")

    if not name or not email or len(password) < 8:
        return with_flash("/admin/mentors/new",
                          "Fill in every field. The password needs at least 8 characters.", "error")

    if not looks_like_email(email):
        return with_flash("/admin/mentors/new",
                          f"\u201c{email}\u201d isn't an email address. The mentor signs in with their "
                          "email, so it has to be one they can receive at.", "error")

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
    return render_done(user, "Mentor added", f"{name} can now sign in and start mentoring.", "/admin", back_label="Continue")


@router.get("/admin/session/<record_id>")
def admin_view_session(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        record = conn.execute(
            """SELECT session_records.*, pupils.forename, pupils.surname, courses.id as course_id, courses.title as course_title,
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
    """Saves the five pupil sessions the builder edits.

    Only those five are deleted and rewritten. The staff-only session 6 is not
    on this form, and a blanket DELETE would have wiped it every time a course
    was saved — silently, since nothing on the page mentions it."""
    conn.execute("DELETE FROM weeks WHERE course_id=? AND week_number <= ?",
                 (course_id, PUPIL_SESSIONS))
    for i in range(1, PUPIL_SESSIONS + 1):
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
        # Only the pupil sessions are editable here; session 6 is fixed content.
        weeks = conn.execute(
            "SELECT * FROM weeks WHERE course_id=? AND week_number <= ? ORDER BY week_number",
            (request.params["course_id"], PUPIL_SESSIONS)).fetchall()
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
                # A parent sees their child, the course, and what to do at home.
                # Nothing else. The week row carries mentor-facing guidance
                # ("Watch for") and the full session plan, so only the two
                # fields a family needs are selected — a template can't leak
                # what was never fetched. staff_only is excluded explicitly
                # rather than relying on a week-number cut-off.
                week = None
                next_number = e["current_week"] + 1
                if 1 <= next_number <= PUPIL_SESSIONS:
                    week = conn.execute(
                        """SELECT week_number, title, home_activity
                           FROM weeks
                           WHERE course_id=? AND week_number=? AND staff_only=0""",
                        (e["course_id"], next_number)).fetchone()
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

_ICON_CHART = ('<svg viewBox="0 0 24 24" fill="none" width="20" height="20" '
               'style="stroke:currentColor" stroke-width="2" stroke-linecap="round" '
               'stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg>')
_ICON_LIST = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></svg>'
_ICON_DOC = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/></svg>'
_ICON_USERS = '<svg viewBox="0 0 24 24" fill="none" width="20" height="20" style="stroke:currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'


def academic_year_bounds(today=None):
    """The English academic year containing a date, as (start, end).

    Runs 1 September to 31 August, which is what a school means by "this year"
    and what a pupil premium statement covers."""
    today = today or datetime.date.today()
    start_year = today.year if today.month >= 9 else today.year - 1
    return (datetime.date(start_year, 9, 1).isoformat(),
            datetime.date(start_year + 1, 8, 31).isoformat())


def recorded_academic_years(conn, establishment_id):
    """Academic years in which this school actually recorded a session.

    Derived from the data rather than counted back from today, so the list never
    offers a year with nothing in it, and never runs out for a school that has
    been going a decade. Newest first, because that is what gets asked for."""
    rows = conn.execute(
        """SELECT MIN(r.date) AS first, MAX(r.date) AS last
           FROM session_records r
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND r.date IS NOT NULL AND r.date != ''""",
        (establishment_id,)).fetchone()
    if not row_has_dates(rows):
        return []
    first = datetime.date.fromisoformat(rows["first"][:10])
    last = datetime.date.fromisoformat(rows["last"][:10])
    start = first.year if first.month >= 9 else first.year - 1
    end = last.year if last.month >= 9 else last.year - 1
    years = []
    for y in range(end, start - 1, -1):
        years.append((f"{y}/{str(y + 1)[-2:]}",
                      datetime.date(y, 9, 1).isoformat(),
                      datetime.date(y + 1, 8, 31).isoformat()))
    return years


def row_has_dates(row):
    return bool(row and row["first"] and row["last"])


def school_terms(conn, establishment_id, limit=None):
    """A school's own term dates, most recent first."""
    sql = """SELECT * FROM terms WHERE establishment_id=?
             ORDER BY date_from DESC"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, (establishment_id,)).fetchall()


def term_containing(conn, establishment_id, today=None):
    """The school's own term covering a date, if they have entered one."""
    today = (today or datetime.date.today()).isoformat()
    return conn.execute(
        """SELECT * FROM terms WHERE establishment_id=?
             AND date_from <= ? AND date_to >= ?
           ORDER BY date_from DESC LIMIT 1""",
        (establishment_id, today, today)).fetchone()


@router.get("/admin/terms")
def admin_terms(request):
    """Where a school tells Phil when its terms actually run."""
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        terms = school_terms(conn, user["establishment_id"])
        guess_from, guess_to = current_term_bounds()
    finally:
        conn.close()
    today = datetime.date.today()
    return render("terms.html", user=user, terms=terms,
                  guess_from=guess_from, guess_to=guess_to,
                  suggested_year=f"{today.year}/{str(today.year + 1)[2:]}"
                                 if today.month >= 9 else
                                 f"{today.year - 1}/{str(today.year)[2:]}",
                  flash=flash_from_query(request))


@router.post("/admin/terms")
def admin_terms_add(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    name = request.field("name", "").strip()
    date_from = request.field("date_from", "").strip()
    date_to = request.field("date_to", "").strip()
    back = "/admin/terms"

    if not (name and date_from and date_to):
        return with_flash(back, "A term needs a name and both dates.", "error")
    try:
        d_from = datetime.date.fromisoformat(date_from)
        d_to = datetime.date.fromisoformat(date_to)
    except ValueError:
        return with_flash(back, "Those dates couldn't be read.", "error")
    # The two mistakes a school will actually make: dates the wrong way round,
    # and a term that runs into one already entered.
    if d_to < d_from:
        return with_flash(back, "The end date is before the start date.", "error")
    if (d_to - d_from).days > 200:
        return with_flash(back, "That's longer than a school year — check the dates.", "error")

    conn = db.get_conn()
    try:
        clash = conn.execute(
            """SELECT name, date_from, date_to FROM terms
               WHERE establishment_id=? AND date_from <= ? AND date_to >= ?
               LIMIT 1""",
            (user["establishment_id"], date_to, date_from)).fetchone()
        if clash:
            return with_flash(back,
                f"Those dates overlap {clash['name']} "
                f"({uk_date(clash['date_from'])} to {uk_date(clash['date_to'])}).", "error")
        conn.execute(
            """INSERT INTO terms (establishment_id, name, date_from, date_to,
                                  created_by, created_at)
               VALUES (?,?,?,?,?,?)""",
            (user["establishment_id"], name, date_from, date_to, user["id"], db.now()))
        db.log_action(conn, user["id"], "term_added", "establishment",
                      user["establishment_id"], f"{name} {date_from} to {date_to}")
        conn.commit()
    finally:
        conn.close()
    return with_flash(back, f"{name} saved.", "success")


@router.post("/admin/terms/<term_id>/delete")
def admin_terms_delete(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    conn = db.get_conn()
    try:
        term = conn.execute("SELECT * FROM terms WHERE id=?",
                            (request.params["term_id"],)).fetchone()
        if not term or term["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        conn.execute("DELETE FROM terms WHERE id=?", (term["id"],))
        db.log_action(conn, user["id"], "term_removed", "establishment",
                      user["establishment_id"], term["name"])
        conn.commit()
        name = term["name"]
    finally:
        conn.close()
    # Nothing else references a term: reports read the dates at the moment they
    # run, so removing one only changes which buttons are offered from now on.
    return with_flash("/admin/terms", f"{name} removed.", "success")


def current_term_bounds(today=None):
    """Rough bounds for the English school term containing a date.

    Term dates vary by school and are set locally, so these are deliberately
    generous: better to include a session at the edge of a term than to cut a
    term short and under-report. A school wanting exact dates can pass explicit
    from and to values."""
    today = today or datetime.date.today()
    y = today.year
    if today.month >= 9:                      # autumn
        return (datetime.date(y, 9, 1).isoformat(),
                datetime.date(y, 12, 31).isoformat())
    if today.month <= 3 or (today.month == 4 and today.day < 7):   # spring
        return (datetime.date(y, 1, 1).isoformat(),
                datetime.date(y, 4, 6).isoformat())
    return (datetime.date(y, 4, 7).isoformat(),   # summer
            datetime.date(y, 8, 31).isoformat())


def impact_figures(conn, establishment_id, date_from=None, date_to=None):
    """The numbers a school weighs at renewal, over a chosen period.

    Deliberately conservative: change is measured only where the same pupil was
    rated at the start and again later, so a course with one rating contributes
    nothing rather than a flattering guess. A number a head of pastoral can't
    trust is worse than no number.

    The period matters as much as the numbers. Schools report by term and by
    academic year, so an all-time total that only ever grows answers none of the
    questions actually asked in a governors' meeting. Counting is by session
    date, not enrolment date: a course that started in July and ran through
    September belongs to the term its sessions happened in."""
    figures = {"date_from": date_from, "date_to": date_to}

    # Applied to session_records.date. Kept as fragments so each query can drop
    # them in without repeating the logic.
    period_sql = ""
    period_args = []
    if date_from:
        period_sql += " AND r.date >= ?"
        period_args.append(date_from)
    if date_to:
        period_sql += " AND r.date <= ?"
        period_args.append(date_to)

    # Enrolments counted as those with at least one session in the period, so
    # the figures describe activity rather than paperwork.
    enrol_filter = ""
    enrol_args = []
    if date_from or date_to:
        enrol_filter = (" AND e.id IN (SELECT r.enrolment_id FROM session_records r"
                        " WHERE 1=1" + period_sql + ")")
        enrol_args = list(period_args)

    row = conn.execute(
        """SELECT COUNT(*) AS enrolments,
                  SUM(CASE WHEN e.status='completed' THEN 1 ELSE 0 END) AS completed,
                  SUM(CASE WHEN e.status='active' THEN 1 ELSE 0 END) AS active,
                  SUM(CASE WHEN e.status='withdrawn' THEN 1 ELSE 0 END) AS withdrawn,
                  COUNT(DISTINCT e.pupil_id) AS pupils
           FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ?""" + enrol_filter,
        tuple([establishment_id] + enrol_args)).fetchone()
    figures.update(dict(row))
    figures["sessions"] = conn.execute(
        """SELECT COUNT(*) FROM session_records r
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id WHERE p.establishment_id = ?"""
        + period_sql, tuple([establishment_id] + period_args)).fetchone()[0]
    figures["safeguarding"] = conn.execute(
        """SELECT COUNT(*) FROM session_records r
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND r.safeguarding_flag = 1"""
        + period_sql, tuple([establishment_id] + period_args)).fetchone()[0]

    # First and last rating per enrolment, counted only where both exist.
    changes = {"mood": [], "engagement": []}
    rows = conn.execute(
        """SELECT r.enrolment_id, w.week_number, r.mood_rating, r.engagement_rating
           FROM session_records r
           JOIN weeks w ON w.id = r.week_id
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND w.staff_only = 0""" + period_sql + """
           ORDER BY r.enrolment_id, w.week_number""",
        tuple([establishment_id] + period_args)).fetchall()
    per = {}
    for r in rows:
        per.setdefault(r["enrolment_id"], []).append(r)
    for records in per.values():
        for key, field in (("mood", "mood_rating"), ("engagement", "engagement_rating")):
            rated = [x[field] for x in records if x[field]]
            if len(rated) >= 2:
                changes[key].append(rated[-1] - rated[0])
    for key in ("mood", "engagement"):
        vals = changes[key]
        figures[f"{key}_n"] = len(vals)
        figures[f"{key}_change"] = (sum(vals) / len(vals)) if vals else None
        figures[f"{key}_improved"] = sum(1 for v in vals if v > 0)

    figures["courses"] = conn.execute(
        """SELECT c.title, COUNT(*) AS n,
                  SUM(CASE WHEN e.status='completed' THEN 1 ELSE 0 END) AS completed
           FROM enrolments e
           JOIN courses c ON c.id = e.course_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ?""" + enrol_filter + """
           GROUP BY c.id ORDER BY n DESC, c.title""",
        tuple([establishment_id] + enrol_args)).fetchall()

    # Deliberately not filtered by period: this is a "right now" figure. A
    # review that was overdue last term and has since been done is not an
    # outstanding problem today.
    figures["reviews_overdue"] = conn.execute(
        """SELECT COUNT(*) FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND e.review_date IS NOT NULL
             AND e.review_done = 0 AND e.review_date < ?""",
        (establishment_id, datetime.date.today().isoformat())).fetchone()[0]

    # What the follow-up chats found. Counted over completed courses in the
    # period, so the denominator is visible and the reader can see how much the
    # proportion rests on.
    figures["followups_due"] = conn.execute(
        """SELECT COUNT(*) FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND e.review_date IS NOT NULL""" + enrol_filter,
        tuple([establishment_id] + enrol_args)).fetchone()[0]
    figures["followups_done"] = conn.execute(
        """SELECT COUNT(*) FROM follow_ups fu
           JOIN enrolments e ON e.id = fu.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ?""" + enrol_filter,
        tuple([establishment_id] + enrol_args)).fetchone()[0]
    figures["followups_helped"] = conn.execute(
        """SELECT COUNT(*) FROM follow_ups fu
           JOIN enrolments e ON e.id = fu.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND fu.helped IN ('better','some')""" + enrol_filter,
        tuple([establishment_id] + enrol_args)).fetchone()[0]
    figures["followups_sustained"] = conn.execute(
        """SELECT COUNT(*) FROM follow_ups fu
           JOIN enrolments e ON e.id = fu.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND fu.behaviour = 'no'""" + enrol_filter,
        tuple([establishment_id] + enrol_args)).fetchone()[0]

    figures["plans_written"] = conn.execute(
        """SELECT COUNT(DISTINCT r.enrolment_id) FROM session_records r
           JOIN weeks w ON w.id = r.week_id
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND w.staff_only = 1
             AND r.what_happened IS NOT NULL AND r.what_happened != ''""" + period_sql,
        tuple([establishment_id] + period_args)).fetchone()[0]
    return figures


@router.post("/internal/cron/retention")
def cron_retention_check(request):
    """Runs the daily checks on a schedule, called by the cron service.

    Railway volumes cannot be shared between services, so a separate cron
    service has no way to reach the database directly. It calls this instead and
    the app, which does hold the volume, does the work.

    Guarded by a shared secret rather than a login, because no person is
    involved. The secret is compared in constant time, and the response says
    only how many notices were raised — never anything about a school."""
    import hmac
    secret = os.environ.get("CRON_SECRET", "")
    supplied = request.header("X-Cron-Secret") or request.field("secret", "")
    if not secret:
        return Response("Cron secret not configured on this deployment.",
                        status="503 Service Unavailable")
    if not hmac.compare_digest(secret, supplied):
        return Response("Not authorised.", status="403 Forbidden")

    conn = db.get_conn()
    try:
        results = run_daily_checks(conn)
    finally:
        conn.close()
    summary = ", ".join(f"{k}: {v}" for k, v in results.items())
    return Response(f"daily checks ok \u2014 {summary}\n", content_type="text/plain")


@router.get("/admin/reports/impact")
def impact_report_form(request):
    """Lets a school choose the period before downloading.

    The quick options cover most asks, but a school's terms are set locally and
    vary, so the date fields are the point: a head writing an annual report or a
    pupil premium statement needs the dates their governors recognise, not an
    approximation of them."""
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked

    today = datetime.date.today()
    year_from, year_to = academic_year_bounds(today)
    term_from, term_to = current_term_bounds(today)

    conn = db.get_conn()
    try:
        years = recorded_academic_years(conn, user["establishment_id"])
        # Terms that have actually started, within this academic year. A term
        # still in the future would be a button returning an empty report, and
        # earlier years would pile up as a wall of buttons.
        today_iso = today.isoformat()
        terms = conn.execute(
            """SELECT * FROM terms WHERE establishment_id=?
                 AND date_from <= ? AND date_to >= ? AND date_from <= ?
               ORDER BY date_from""",
            (user["establishment_id"], today_iso, year_from, year_to)).fetchall()
        # Entered but not yet begun. Counted so the page can say so, rather than
        # leaving an admin who has just entered next year's terms wondering why
        # nothing appeared.
        upcoming = conn.execute(
            """SELECT count(*) FROM terms WHERE establishment_id=? AND date_from > ?""",
            (user["establishment_id"], today_iso)).fetchone()[0]
        # Whether they have entered any at all, which is what decides if the
        # guess is still offered — a school with only future terms entered has
        # still told us they don't want it.
        any_terms = conn.execute(
            "SELECT 1 FROM terms WHERE establishment_id=? LIMIT 1",
            (user["establishment_id"],)).fetchone() is not None
    finally:
        conn.close()

    # A school's own terms if they've entered them, and only those: a guessed
    # "This term" sitting next to real ones would be indistinguishable from
    # them, and it's the guess a head would quote to governors.
    presets = [("This academic year", year_from, year_to)]
    for t in terms:
        presets.append((t["name"], t["date_from"], t["date_to"]))
    if not any_terms:
        presets.append(("This term (approximate)", term_from, term_to))
    return render("impact_form.html", user=user, presets=presets, years=years,
                  current_year_from=year_from, has_terms=any_terms, upcoming_terms=upcoming,
                  default_from=year_from, default_to=year_to,
                  flash=flash_from_query(request))


@router.get("/admin/reports/impact/pdf")
def impact_report_download(request):
    """The report a school shows its governors, and weighs at renewal."""
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    # ?period=year (default) covers the current academic year, ?period=all the
    # whole history, and explicit from/to dates cover a term. Defaulting to the
    # academic year rather than all-time is deliberate: it matches how a school
    # reports, and an all-time total that only grows answers no real question.
    period = request.query.get("period", ["year"])[0]
    date_from = request.query.get("from", [None])[0]
    date_to = request.query.get("to", [None])[0]

    # The year dropdown sends one value so a select can carry both dates.
    chosen = request.query.get("range", [None])[0]
    if chosen and "|" in chosen:
        date_from, date_to = chosen.split("|", 1)

    # Dates arrive from a form and a URL, so validate rather than trust. A bad
    # date is a mistake, not an attack, so say so and let them try again.
    for value in (date_from, date_to):
        if value:
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                return with_flash("/admin/reports/impact",
                                  "Those dates weren't recognised. Please pick them again.",
                                  "error")
    if date_from and date_to and date_from > date_to:
        return with_flash("/admin/reports/impact",
                          "The start date is after the end date.", "error")

    if not (date_from or date_to):
        if period == "year":
            date_from, date_to = academic_year_bounds()
        elif period == "term":
            date_from, date_to = current_term_bounds()
        elif period == "all":
            date_from = date_to = None

    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT name FROM establishments WHERE id=?",
                             (user["establishment_id"],)).fetchone()
        figures = impact_figures(conn, user["establishment_id"], date_from, date_to)
    finally:
        conn.close()
    path = pdfgen.impact_report_pdf(user["establishment_id"],
                                    estab["name"] if estab else "Establishment", figures)
    return pdf_response(path, "impact-report.pdf")


@router.get("/admin/reports")
def admin_reports_chooser(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    cards = [
        {"title": "Impact report", "desc": "How mentoring is going across the school: pupils supported, completion, change in engagement, and follow-ups outstanding. For governors and SLT. Choose any period.",
         "href": "/admin/reports/impact", "icon": _ICON_CHART,
         "bg": "var(--amber-light)"},
        {"title": "Whole-establishment report", "desc": "Every pupil, who mentors them, course(s), sessions completed and progress.",
         "href": "/admin/reports/full", "icon": _ICON_LIST, "bg": "var(--teal-light)"},
        {"title": "Pupil report", "desc": "Everything on one pupil: every course, session by session, "
                                          "with their goals and the course summaries.",
         "href": "/admin/reports/pupils", "icon": _ICON_DOC, "bg": "var(--coral-light)"},
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
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    cards = [
        {"title": "Your mentoring list", "desc": "Every pupil you mentor and where each course is up to. "
                                                "Progress only, no session notes.",
         "href": "/mentor/reports/caseload", "icon": _ICON_USERS, "bg": "var(--teal-light)"},
        {"title": "Pupil report", "desc": "Everything on one pupil: every course, session by session, "
                                          "with their goals and the course summaries.",
         "href": "/mentor/reports/pupils", "icon": _ICON_DOC, "bg": "var(--coral-light)"},
    ]
    return render("reports_chooser.html", user=user, cards=cards,
                  intro="Download your mentoring list, or a full report for one of your pupils.",
                  note="Limited to pupils you mentor. For anyone else, ask an admin.",
                  flash=flash_from_query(request))


def _pupil_report_list(conn, mentor_id=None, establishment_id=None):
    """Pupils, with enough about each to choose whose report you want.

    Its own page rather than a button on the mentoring list: that page answers
    "where is everyone up to", this one answers "give me everything on one
    child". Two questions, two pages.
    """
    query = """
        SELECT pupils.id, pupils.forename, pupils.surname, pupils.year_group,
               pupils.form_class, pupils.status
        FROM pupils WHERE 1=1
    """
    params = []
    if establishment_id:
        query += " AND pupils.establishment_id=?"
        params.append(establishment_id)
    if mentor_id:
        query += " AND pupils.id IN (SELECT pupil_id FROM enrolments WHERE mentor_id=?)"
        params.append(mentor_id)
    query += " ORDER BY pupils.status, pupils.surname, pupils.forename"

    out = []
    for p in conn.execute(query, params).fetchall():
        # Every course, whoever mentored it. mentor_id decides which pupils a
        # mentor sees, not which of that pupil's courses are counted: the report
        # itself has always covered the lot, so counting only your own here made
        # the page say "2 courses" and the PDF hand over five.
        courses = conn.execute(
            """SELECT e.status, c.title, u.name AS mentor_name,
                      (SELECT max(r.date) FROM session_records r WHERE r.enrolment_id = e.id) AS last_session
               FROM enrolments e
               JOIN courses c ON c.id = e.course_id
               LEFT JOIN users u ON u.id = e.mentor_id
               WHERE e.pupil_id=?""",
            (p["id"],)).fetchall()
        if not courses:
            continue
        sessions = conn.execute(
            """SELECT count(*) FROM session_records r JOIN enrolments e ON e.id = r.enrolment_id
               WHERE e.pupil_id=?""", (p["id"],)).fetchone()[0]
        dates = [c["last_session"] for c in courses if c["last_session"]]
        out.append({
            "id": p["id"],
            "name": f"{p['forename']} {p['surname']}",
            "year_group": p["year_group"],
            "form_class": p["form_class"],
            "archived": p["status"] != "active",
            "total": len(courses),
            "active": sum(1 for c in courses if c["status"] == "active"),
            "completed": sum(1 for c in courses if c["status"] == "completed"),
            "sessions": sessions,
            "last_session": uk_date(max(dates)) if dates else None,
            "titles": [c["title"] for c in courses],
            # Named when more than one person has worked with this child, so it
            # is clear the report reaches beyond whoever is looking at it.
            "mentors": sorted({c["mentor_name"] for c in courses if c["mentor_name"]}),
        })
    return out


@router.get("/mentor/reports/pupils")
def mentor_pupil_reports(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        year, y_from, y_to, years = chosen_year(request, conn, user["establishment_id"])
        pupils = _pupil_report_list(conn, mentor_id=user["id"])
    finally:
        conn.close()
    return render("pupil_reports.html", user=user, pupils=pupils,
                  years=years, selected_year=year, year_action="/mentor/reports/pupils",
                  title="Pupil reports",
                  intro="Everything on one pupil in a single file: every course they have "
                        "done at this school, whoever mentored it, session by session, with "
                        "the goals they set and the course summaries written for staff.",
                  scope="Pupils you mentor, including courses run by other mentors.",
                  flash=flash_from_query(request))


@router.get("/admin/reports/pupils")
def admin_pupil_reports(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        year, y_from, y_to, years = chosen_year(request, conn, user["establishment_id"])
        pupils = _pupil_report_list(conn, establishment_id=user["establishment_id"])
    finally:
        conn.close()
    return render("pupil_reports.html", user=user, pupils=pupils,
                  years=years, selected_year=year, year_action="/admin/reports/pupils",
                  title="Pupil reports",
                  intro="Everything on one pupil in a single file: every course they have "
                        "done at this school, whoever mentored it, session by session, with "
                        "the goals they set and the course summaries written for staff.",
                  scope="Every pupil at your establishment, whoever mentors them.",
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
    conn2 = db.get_conn()
    try:
        # The support plan is written by the mentor for other staff. It names
        # triggers and strategies in professional terms and is not written to be
        # read by a family, so it stays out of a parent's copy of this report.
        plan = None
        if user["role"] != "parent_carer":
            plan = support_plan_for(conn2, enrolment["id"])
    finally:
        conn2.close()
    path = pdfgen.mentee_report_pdf(
        enrolment["id"], f"{enrolment['forename']} {enrolment['surname']}", enrolment["course_title"],
        enrolment["mentor_name"], enrolment["start_date"], enrolment["current_week"], enrolment["status"],
        weeks_list, reflection_dict, support_plan=plan,
    )
    return pdf_response(path, "course-report.pdf")


def period_label(year):
    """What a report says it covers. Printed in the header, so a PDF found in a
    drawer in three years still says which year it is about."""
    return "All time" if year == "all" else f"Academic year {year}"


def _year_filter(year_from, year_to):
    """SQL restricting to courses whose sessions ran inside an academic year.

    A course belongs to the year it was delivered in, not the year it was
    created or the year the pupil happens to be in now. That's what a school
    means by "we ran twelve courses last year", and it's the only definition
    that reads the same on all three reports.
    """
    if not (year_from and year_to):
        return "", []
    return (""" AND EXISTS (SELECT 1 FROM session_records sr
                            WHERE sr.enrolment_id = enrolments.id
                              AND sr.date BETWEEN ? AND ?)""",
            [year_from, year_to])


def _caseload_rows(conn, mentor_id=None, establishment_id=None, show_mentor=False,
                   year_from=None, year_to=None):
    query = """
        SELECT enrolments.id, enrolments.start_date, enrolments.current_week, enrolments.status,
               enrolments.review_date, enrolments.review_done,
               pupils.id as pupil_id, pupils.forename, pupils.surname,
               courses.title as course_title, users.name as mentor_name,
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
    year_sql, year_args = _year_filter(year_from, year_to)
    query += year_sql
    params += year_args
    query += " ORDER BY enrolments.status, pupils.surname"
    rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        start = datetime.date.fromisoformat(r["start_date"])
        scheduled_end = (start + datetime.timedelta(days=35)).isoformat()
        cert = conn.execute("SELECT id FROM certificates WHERE enrolment_id=?", (r["id"],)).fetchone()
        progress = ("Completed" if r["status"] == "completed"
                    else f"Week {r['current_week']} of {SESSIONS_PER_COURSE}")
        # The reflection column asked for something retired, so it read "Needed"
        # for ever on every finished course. Replaced with the follow-up, which
        # is the thing that actually is outstanding after a course ends.
        if r["status"] != "completed":
            follow_up = "-"
        elif r["review_done"]:
            follow_up = "Done"
        elif not r["review_date"]:
            follow_up = "Not booked"
        else:
            overdue_after = review_overdue_from(r["review_date"])
            today_iso = datetime.date.today().isoformat()
            follow_up = ("Overdue" if overdue_after and today_iso > overdue_after
                         else "Due " + uk_date(r["review_date"]))
        row = {
            "pupil": f"{r['forename']} {r['surname']}",
            "course": r["course_title"],
            "started": uk_date(r["start_date"]),
            "scheduled_end": uk_date(scheduled_end),
            "progress": progress,
            "certificate": "Issued" if cert else "Not yet",
            "follow_up": follow_up,
            "enrolment_id": r["enrolment_id"],
            "pupil_id": r["pupil_id"],
            "status": r["status"],
        }
        if show_mentor:
            row["mentor"] = r["mentor_name"]
        result.append(row)
    return result


def chosen_year(request, conn, establishment_id):
    """(label, from, to, years) for a report's academic-year picker.

    Years come from the data, so the list never offers one with nothing in it
    and never runs out. "All time" is the default and is always offered.
    """
    years = recorded_academic_years(conn, establishment_id)
    choice = request.query.get("year", ["all"])[0]
    for label, y_from, y_to in years:
        if choice == label:
            return label, y_from, y_to, years
    return "all", None, None, years


def _caseload_grouped(rows):
    """The same rows, one entry per pupil.

    A pupil on five courses filled five lines with the same name, which reads as
    five children — the same thing that was wrong with the reassign page and the
    mentoring list. The flat rows still go to the PDF and the spreadsheet, where
    a row per course is what you want for sorting and filtering.
    """
    pupils, by_id = [], {}
    for row in rows:
        group = by_id.get(row["pupil_id"])
        if group is None:
            group = {"pupil": row["pupil"], "pupil_id": row["pupil_id"], "courses": []}
            by_id[row["pupil_id"]] = group
            pupils.append(group)
        group["courses"].append(row)
    for group in pupils:
        group["total"] = len(group["courses"])
        group["active"] = sum(1 for c in group["courses"] if c["status"] == "active")
        group["completed"] = sum(1 for c in group["courses"] if c["status"] == "completed")
        group["needs_attention"] = sum(
            1 for c in group["courses"]
            if c["follow_up"] in ("Overdue", "Not booked"))
    return pupils


@router.get("/mentor/reports/caseload")
def mentor_caseload(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        year, y_from, y_to, years = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=user["id"], year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    suffix = f"?year={year}"
    return render("report_caseload.html", user=user, rows=rows,
                  pupils=_caseload_grouped(rows), show_mentor=False,
                  title="My mentoring list", pdf_url="/mentor/reports/caseload/pdf" + suffix,
                  xlsx_url="/mentor/reports/caseload/xlsx" + suffix,
                  years=years, selected_year=year, year_action="/mentor/reports/caseload",
                  filter_form=None, flash=flash_from_query(request))


@router.get("/mentor/reports/caseload/pdf")
def mentor_caseload_pdf(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        year, y_from, y_to, _ = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=user["id"], year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    path = pdfgen.caseload_report_pdf("Mentoring list", rows, False, f"caseload_{user['id']}",
                                      period=period_label(year))
    return pdf_response(path, "mentoring-list.pdf")


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
        year, y_from, y_to, years = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"),
                               year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    pdf_url = f"/admin/reports/caseload/pdf?mentor_id={mentor_filter}&year={year}"
    xlsx_url = f"/admin/reports/caseload/xlsx?mentor_id={mentor_filter}&year={year}"
    return render("report_caseload.html", user=user, rows=rows,
                  pupils=_caseload_grouped(rows), show_mentor=(mentor_filter == "all"),
                  title="Establishment mentoring list", pdf_url=pdf_url, xlsx_url=xlsx_url, mentors=mentors,
                  years=years, selected_year=year, year_action="/admin/reports/caseload",
                  selected_mentor=mentor_filter, flash=flash_from_query(request))


@router.get("/admin/reports/caseload/pdf")
def admin_caseload_pdf(request):
    user, err = require(request, roles=["admin", "phil_staff"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    mentor_filter = request.query.get("mentor_id", ["all"])[0]
    conn = db.get_conn()
    try:
        mid = int(mentor_filter) if mentor_filter != "all" else None
        year, y_from, y_to, _ = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"),
                               year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    path = pdfgen.caseload_report_pdf("Establishment mentoring list", rows, mentor_filter == "all",
                                       f"caseload_admin_{user['establishment_id']}",
                                       period=period_label(year))
    return pdf_response(path, "mentoring-list.pdf")


@router.get("/mentor/reports/caseload/xlsx")
def mentor_caseload_xlsx(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    blocked = require_active_subscription(user)
    if blocked:
        return blocked
    conn = db.get_conn()
    try:
        year, y_from, y_to, _ = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=user["id"], year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    path = pdfgen.caseload_report_xlsx(rows, False, f"caseload_{user['id']}",
                                       period=period_label(year))
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=[("Content-Disposition", 'attachment; filename="mentoring-list.xlsx"')],
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
        year, y_from, y_to, _ = chosen_year(request, conn, user["establishment_id"])
        rows = _caseload_rows(conn, mentor_id=mid, establishment_id=user["establishment_id"],
                               show_mentor=(mentor_filter == "all"),
                               year_from=y_from, year_to=y_to)
    finally:
        conn.close()
    path = pdfgen.caseload_report_xlsx(rows, mentor_filter == "all",
                                       f"caseload_admin_{user['establishment_id']}",
                                       period=period_label(year))
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=[("Content-Disposition", 'attachment; filename="mentoring-list.xlsx"')],
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
        # There is no scheduler on this host, so the retention check runs when
        # staff open the console. A cron job would be better; this at least means
        # nobody has to remember to look.
        check_retention_due(conn)
        rows = conn.execute("SELECT * FROM establishments WHERE type='school' ORDER BY name").fetchall()
        due = {e["id"]: e for e in establishments_due_deletion(conn)}
    finally:
        conn.close()
    return render("staff_establishments.html", user=user, establishments=rows,
                  due_deletion=due, retention_days=RETENTION_DAYS,
                  flash=flash_from_query(request))


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
    conn2 = db.get_conn()
    try:
        due = {e["id"]: e for e in establishments_due_deletion(conn2)}
    finally:
        conn2.close()
    return render("staff_establishment_detail.html", user=user, estab=estab, sub=sub, admin=admin, used=used,
                  limit=seat_limit(sub) if sub else 0, pupil_count=pupil_count,
                  due_deletion=due.get(estab["id"]), retention_days=RETENTION_DAYS,
                  flash=flash_from_query(request))


RETENTION_DAYS = 90


def establishments_due_deletion(conn):
    """Schools whose data is past the retention period promised in the DPA.

    Counted from the day the subscription ended or was cancelled. Returns the
    rows plus how many days overdue, so the notice can say how late it is rather
    than just that it is due."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=RETENTION_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT e.id, e.name, e.status, s.status AS sub_status,
                  s.renewal_date, s.pilot_ends_at,
                  (SELECT COUNT(*) FROM pupils WHERE establishment_id = e.id) AS pupils
           FROM establishments e
           LEFT JOIN subscriptions s ON s.id =
                (SELECT id FROM subscriptions WHERE establishment_id = e.id
                 ORDER BY id DESC LIMIT 1)
           WHERE e.status != 'deleted'""").fetchall()
    due = []
    for r in rows:
        # A live subscription is never due. Only expired or cancelled ones.
        if r["sub_status"] not in ("expired", "cancelled") and r["status"] != "closed":
            continue
        ended = r["renewal_date"] or r["pilot_ends_at"]
        if not ended or ended > cutoff:
            continue
        days = (datetime.date.today() - datetime.date.fromisoformat(ended)).days
        due.append(dict(r, ended=ended, days_since=days,
                        overdue_by=days - RETENTION_DAYS))
    return due


def _raise_once(conn, kind, estab_id, key, body):
    """Raises a notice unless an identical unread one already exists.

    Keyed on the notice type plus the thing it is about, so a daily check does
    not produce a daily copy of the same warning. Phil staff reading the same
    sentence seven mornings running stop reading it."""
    already = conn.execute(
        """SELECT 1 FROM notifications
           WHERE type=? AND status='unread' AND payload LIKE ?""",
        (kind, f"%[{key}]%")).fetchone()
    if already:
        return 0
    conn.execute(
        """INSERT INTO notifications (type, recipient, establishment_id, payload, status, sent_at)
           VALUES (?,?,?,?,?,?)""",
        (kind, "phil_staff", estab_id, f"[{key}] {body}", "unread", db.now()))
    return 1


def check_pilots_ending(conn, days=3):
    """Pilots about to expire.

    A pilot quietly running out is the moment a school either buys or drifts
    away, and it is the one date in the system nobody is watching."""
    today = datetime.date.today()
    horizon = (today + datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT e.id, e.name, s.pilot_ends_at,
                  (SELECT COUNT(*) FROM pupils WHERE establishment_id=e.id) AS pupils,
                  (SELECT COUNT(*) FROM users WHERE establishment_id=e.id AND role='mentor') AS mentors
           FROM establishments e
           JOIN subscriptions s ON s.id =
                (SELECT id FROM subscriptions WHERE establishment_id=e.id ORDER BY id DESC LIMIT 1)
           WHERE s.plan_type='pilot' AND s.status='active'
             AND s.pilot_ends_at IS NOT NULL
             AND s.pilot_ends_at <= ? AND s.pilot_ends_at >= ?""",
        (horizon, today.isoformat())).fetchall()
    raised = 0
    for r in rows:
        left = (datetime.date.fromisoformat(r["pilot_ends_at"][:10]) - today).days
        when = "today" if left == 0 else f"in {left} day{'' if left == 1 else 's'}"
        raised += _raise_once(
            conn, "pilot_ending", r["id"], f"pilot-{r['id']}-{r['pilot_ends_at'][:10]}",
            f"{r['name']}'s pilot ends {when} ({r['pilot_ends_at'][:10]}). "
            f"{r['mentors']} mentor(s), {r['pupils']} pupil(s) enrolled. "
            "Worth a conversation before it lapses.")
    return raised


def check_overdue_invoices(conn):
    """Invoices past their due date and not paid."""
    today = datetime.date.today().isoformat()
    rows = conn.execute(
        """SELECT i.id, i.amount, i.due_date, i.purchase_order_ref, e.id AS estab_id, e.name
           FROM invoices i
           JOIN subscriptions s ON s.id = i.subscription_id
           JOIN establishments e ON e.id = s.establishment_id
           WHERE i.status IN ('sent','overdue') AND i.due_date IS NOT NULL
             AND i.due_date < ?""", (today,)).fetchall()
    raised = 0
    for r in rows:
        days = (datetime.date.today() - datetime.date.fromisoformat(r["due_date"][:10])).days
        po = f" PO {r['purchase_order_ref']}." if r["purchase_order_ref"] else ""
        raised += _raise_once(
            conn, "invoice_overdue", r["estab_id"], f"invoice-{r['id']}",
            f"{r['name']}: invoice for \u00a3{r['amount']:.2f} was due {r['due_date'][:10]}, "
            f"{days} day(s) ago.{po}")
    return raised


def check_stale_support(conn, days=2):
    """Support requests nobody has answered.

    A school waiting on a reply is forming a view of whether Phil is worth
    renewing, and the clock starts the moment they write."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT r.id, r.subject, r.created_at, e.id AS estab_id, e.name
           FROM support_requests r
           LEFT JOIN establishments e ON e.id = r.establishment_id
           WHERE r.status='open' AND r.created_at < ?""", (cutoff,)).fetchall()
    raised = 0
    for r in rows:
        waited = (datetime.date.today()
                  - datetime.date.fromisoformat(r["created_at"][:10])).days
        raised += _raise_once(
            conn, "support_stale", r["estab_id"], f"support-{r['id']}",
            f"Support request from {r['name'] or 'an individual account'} has been open "
            f"{waited} day(s): \u201c{(r['subject'] or '')[:60]}\u201d")
    return raised


def check_pending_parent_access(conn, days=3):
    """Parent access requests left unresolved.

    The school approves these, not Phil, so this is a nudge to nudge them: a
    parent is waiting and has no way to chase it themselves."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT r.id, r.created_at, e.id AS estab_id, e.name
           FROM parent_access_requests r
           JOIN establishments e ON e.id = r.establishment_id
           WHERE r.status='pending' AND r.created_at < ?""", (cutoff,)).fetchall()
    raised = 0
    for r in rows:
        waited = (datetime.date.today()
                  - datetime.date.fromisoformat(r["created_at"][:10])).days
        raised += _raise_once(
            conn, "parent_access_pending", r["estab_id"], f"paccess-{r['id']}",
            f"{r['name']}: a parent access request has been pending {waited} day(s). "
            "The school approves these, so they may need reminding.")
    return raised


def check_stalled_courses(conn, days=30):
    """Courses that started and then stopped.

    This one is not really about churn. A pupil who began a bereavement or
    exploitation course and stopped halfway is worth someone asking about, and
    nobody currently would."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT en.id, en.current_week, p.forename, p.surname, c.title,
                  e.id AS estab_id, e.name AS estab, u.name AS mentor,
                  COALESCE(MAX(r.date), en.start_date) AS last_activity
           FROM enrolments en
           JOIN pupils p ON p.id = en.pupil_id
           JOIN establishments e ON e.id = p.establishment_id
           JOIN courses c ON c.id = en.course_id
           JOIN users u ON u.id = en.mentor_id
           LEFT JOIN session_records r ON r.enrolment_id = en.id
           WHERE en.status='active'
           GROUP BY en.id
           HAVING last_activity < ?""", (cutoff,)).fetchall()
    raised = 0
    for r in rows:
        since = (datetime.date.today()
                 - datetime.date.fromisoformat(r["last_activity"][:10])).days
        raised += _raise_once(
            conn, "course_stalled", r["estab_id"], f"stalled-{r['id']}-{r['last_activity'][:10]}",
            f"{r['estab']}: {r['forename']} {r['surname']} is {r['current_week']} session(s) into "
            f"{r['title']} with {r['mentor']}, and nothing has been recorded for {since} days.")
    return raised


def run_daily_checks(conn):
    """Every scheduled check, run in one pass.

    Each is wrapped so that one failing query cannot stop the others: a broken
    invoice check should not silence a stalled safeguarding course."""
    results = {}
    for name, fn in (("retention", check_retention_due),
                     ("pilots ending", check_pilots_ending),
                     ("overdue invoices", check_overdue_invoices),
                     ("stale support", check_stale_support),
                     ("parent access", check_pending_parent_access),
                     ("stalled courses", check_stalled_courses)):
        try:
            results[name] = fn(conn)
        except Exception as e:  # noqa: BLE001
            results[name] = f"failed: {type(e).__name__}"
    conn.commit()
    return results


def check_retention_due(conn):
    """Raises one notice per school whose data is due for deletion.

    Deliberately a notice and not an automatic deletion: a subscription can lapse
    over a summer holiday because an invoice sat unpaid, and pupil records should
    not be destroyed by a billing hiccup with nobody looking. The notice removes
    the excuse of forgetting; a person still decides."""
    raised = 0
    for e in establishments_due_deletion(conn):
        already = conn.execute(
            """SELECT 1 FROM notifications
               WHERE type='retention_due' AND establishment_id=? AND status='unread'""",
            (e["id"],)).fetchone()
        if already:
            continue
        conn.execute(
            """INSERT INTO notifications (type, recipient, establishment_id, payload, status, sent_at)
               VALUES (?,?,?,?,?,?)""",
            ("retention_due", "phil_staff", e["id"],
             f"{e['name']} ended {e['ended']} — {e['days_since']} days ago. "
             f"Its data is {e['overdue_by']} day(s) past the {RETENTION_DAYS}-day "
             f"retention period and should be deleted. {e['pupils']} pupil record(s) held.",
             "unread", db.now()))
        raised += 1
    if raised:
        conn.commit()
    return raised


@router.post("/staff/establishments/<establishment_id>/delete")
def staff_delete_establishment(request):
    """Deletes every record belonging to one establishment.

    Phil staff only, and the school's name must be typed to confirm — this
    removes pupil records permanently and there is no undo. Invoices are kept:
    HMRC requires six years and they hold billing details, not pupil data."""
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    eid = request.params["establishment_id"]
    conn = db.get_conn()
    try:
        estab = conn.execute("SELECT * FROM establishments WHERE id=?", (eid,)).fetchone()
        if not estab:
            return Response("Not found", status="404 Not Found")
        typed = request.field("confirm_name", "").strip()
        if typed != estab["name"]:
            return with_flash(f"/staff/establishments/{eid}",
                              "The name didn't match, so nothing was deleted.", "error")

        counts = delete_establishment_data(conn, eid)
        db.log_action(conn, user["id"], "establishment_deleted", "establishment", eid,
                      f"{estab['name']}: {counts} records")
        conn.commit()
    finally:
        conn.close()
    return with_flash("/staff/establishments",
                      f"{estab['name']} deleted. {counts} record(s) removed. "
                      "Confirm to the school in writing.", "ok")


def delete_establishment_data(conn, eid):
    """Removes an establishment and everything belonging to it.

    Children before parents. Mirrors delete_establishment.py in the repo root,
    which does the same job from the command line."""
    ENROL = """SELECT e.id FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
               WHERE p.establishment_id = ?"""
    total = 0

    def run(sql, params=(eid,)):
        nonlocal total
        cur = conn.execute(sql, params)
        total += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    for table in ("session_records", "resource_entries", "completion_reflections",
                  "certificates", "session_schedule", "session_drafts"):
        run(f"DELETE FROM {table} WHERE enrolment_id IN ({ENROL})")
    run(f"DELETE FROM enrolments WHERE id IN ({ENROL})")
    run("""DELETE FROM pupil_parent_links WHERE pupil_id IN
           (SELECT id FROM pupils WHERE establishment_id = ?)""")
    run("DELETE FROM parent_access_requests WHERE establishment_id = ?")
    run("DELETE FROM pupils WHERE establishment_id = ?")
    run("DELETE FROM support_requests WHERE establishment_id = ?")
    run("DELETE FROM course_requests WHERE establishment_id = ?")
    run("DELETE FROM notifications WHERE establishment_id = ?")
    run("DELETE FROM seat_alerts WHERE establishment_id = ?")
    run("""DELETE FROM sessions WHERE user_id IN
           (SELECT id FROM users WHERE establishment_id = ?)""")
    run("DELETE FROM users WHERE establishment_id = ?")
    run("DELETE FROM subscriptions WHERE establishment_id = ?")
    run("DELETE FROM establishments WHERE id = ?")
    return total


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
    return render_done(user, "Request sent", "The Phil team will review your course request.", "/admin", back_label="Continue")


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


@router.post("/staff/team/<member_id>/status")
def staff_team_set_status(request):
    """Suspends or reactivates a Phil staff account.

    Deliberately a status change rather than a delete: these accounts author
    courses, audit entries and seeded data, so removing the row would orphan
    records. Suspended accounts can't sign in, which is the security outcome
    that matters, and the change is reversible.

    You can't suspend yourself. Phil staff is the top of the tree, with no one
    above to undo it, so a misclick would otherwise mean database surgery to
    get back in."""
    user, err = require(request, roles=["phil_staff"])
    if err:
        return err
    try:
        member_id = int(request.params.get("member_id"))
    except (TypeError, ValueError):
        return with_flash("/staff/team", "Unknown team member.", "error")
    if member_id == user["id"]:
        return with_flash("/staff/team", "You can't suspend your own account.", "error")

    conn = db.get_conn()
    try:
        member = conn.execute(
            "SELECT * FROM users WHERE id=? AND role='phil_staff'", (member_id,)
        ).fetchone()
        if not member:
            return with_flash("/staff/team", "Unknown team member.", "error")
        new_status = "active" if member["status"] != "active" else "suspended"
        if new_status == "suspended":
            others = conn.execute(
                """SELECT COUNT(*) AS n FROM users
                   WHERE role='phil_staff' AND status='active' AND id != ?""",
                (member_id,),
            ).fetchone()["n"]
            if others == 0:
                return with_flash("/staff/team",
                                  "That's the last active Phil staff account, so it can't be suspended.",
                                  "error")
        conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, member_id))
        if new_status == "suspended":
            # End any sessions they already have, or suspending only stops the
            # next sign-in and leaves an open browser working.
            conn.execute("DELETE FROM sessions WHERE user_id=?", (member_id,))
        db.log_action(conn, user["id"], f"phil_staff_{new_status}", "user", member_id, member["email"])
        conn.commit()
    finally:
        conn.close()
    word = "reactivated" if new_status == "active" else "suspended"
    return with_flash("/staff/team", f"{member['name']} {word}.", "ok")


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


@router.get("/notifications")
def notifications_page(request):
    user, err = require(request)
    if err:
        return err
    conn = db.get_conn()
    try:
        establishment = None
        if user["establishment_id"]:
            establishment = conn.execute(
                "SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)
            ).fetchone()
        if user["role"] == "phil_staff":
            unread = conn.execute(
                "SELECT * FROM notifications WHERE recipient='phil_staff' AND status='unread' ORDER BY sent_at DESC"
            ).fetchall()
            read = conn.execute(
                "SELECT * FROM notifications WHERE recipient='phil_staff' AND status='read' ORDER BY sent_at DESC LIMIT 20"
            ).fetchall()
        else:
            unread = conn.execute(
                "SELECT * FROM notifications WHERE recipient=? AND establishment_id=? AND status='unread' ORDER BY sent_at DESC",
                (user["role"], user["establishment_id"]),
            ).fetchall()
            read = conn.execute(
                "SELECT * FROM notifications WHERE recipient=? AND establishment_id=? AND status='read' ORDER BY sent_at DESC LIMIT 20",
                (user["role"], user["establishment_id"]),
            ).fetchall()
    finally:
        conn.close()
    return render("notifications.html", user=user, establishment=establishment, unread=unread, read=read)


@router.post("/notifications/<notification_id>/read")
def mark_notification_read_own(request):
    user, err = require(request)
    if err:
        return err
    conn = db.get_conn()
    try:
        # Scoped by establishment as well as role: recipient alone would let an
        # admin clear another school's notification.
        conn.execute(
            """UPDATE notifications SET status='read'
               WHERE id=? AND recipient=? AND (establishment_id IS ? OR establishment_id=?)""",
            (request.params["notification_id"], user["role"],
             user["establishment_id"], user["establishment_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return redirect("/notifications")


@router.post("/notifications/read-all")
def mark_all_notifications_read(request):
    user, err = require(request)
    if err:
        return err
    conn = db.get_conn()
    try:
        if user["role"] == "phil_staff":
            conn.execute("UPDATE notifications SET status='read' WHERE recipient='phil_staff' AND status='unread'")
        else:
            conn.execute(
                "UPDATE notifications SET status='read' WHERE recipient=? AND establishment_id=? AND status='unread'",
                (user["role"], user["establishment_id"]),
            )
        conn.commit()
    finally:
        conn.close()
    return redirect("/notifications")


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


@router.get("/account/billing")
def account_billing(request):
    """Billing home for an independent mentor: what they're on, what state it
    is in, and the one button that changes it.

    Establishment mentors are sent to their own home instead. Their school
    pays, so there is nothing here for them to act on and showing a price
    would only confuse."""
    user, err = require(request, roles=["mentor"])
    if err:
        return err
    conn = db.get_conn()
    try:
        estab = conn.execute(
            "SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)
        ).fetchone()
        sub = conn.execute(
            """SELECT * FROM subscriptions WHERE establishment_id=?
               ORDER BY id DESC LIMIT 1""",
            (user["establishment_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not estab or estab["type"] != "individual":
        return with_flash("/mentor", "Your establishment handles billing.", "ok")
    return render(
        "account_billing.html",
        user=user,
        subscription=sub,
        card_ready=billing.is_configured(),
        flash=flash_from_query(request),
    )


@router.get("/account/billing/checkout")
def individual_billing_checkout(request):
    """Starts Stripe Checkout for an independent mentor's own seat.

    Separate from /admin/billing/checkout because that one is admin-only and
    buys a school's plan. Both land in the same webhook, which resolves
    client_reference_id to an establishment either way, so an individual is
    simply an establishment of one."""
    user, err = require(request, roles=["mentor"])
    if err:
        return err
    conn = db.get_conn()
    try:
        estab = conn.execute(
            "SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)
        ).fetchone()
    finally:
        conn.close()
    if not estab or estab["type"] != "individual":
        return with_flash("/mentor", "Your establishment handles billing.", "error")
    if not billing.is_configured():
        return with_flash("/account/billing",
                          "Card payments aren't set up yet. Please try again shortly.", "error")
    # Monthly unless the annual button was used. Anything unrecognised falls
    # back to monthly rather than erroring: a mangled link should not stop
    # someone paying, and monthly is the cheaper commitment of the two.
    plan = "individual_annual" if request.field("plan", "") == "annual" else "individual"
    try:
        checkout_url = billing.create_checkout_session(
            estab["id"], estab["name"], user["email"], plan)
    except RuntimeError as exc:
        return with_flash("/account/billing", str(exc), "error")
    return redirect(checkout_url)


@router.get("/account/billing/portal")
def individual_billing_portal(request):
    """Sends an independent mentor to Stripe's hosted billing portal, where
    they can cancel, change card and download invoices.

    Deliberately not rebuilt inside Phil: cancellation alone means handling
    proration and end-of-period access, and card updates mean handling failed
    payments and retries. Stripe already does all of it."""
    user, err = require(request, roles=["mentor"])
    if err:
        return err
    conn = db.get_conn()
    try:
        estab = conn.execute(
            "SELECT * FROM establishments WHERE id=?", (user["establishment_id"],)
        ).fetchone()
        sub = conn.execute(
            """SELECT * FROM subscriptions WHERE establishment_id=?
               ORDER BY id DESC LIMIT 1""",
            (user["establishment_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not estab or estab["type"] != "individual":
        return with_flash("/mentor", "Your establishment handles billing.", "error")
    if not sub or not sub["stripe_customer_id"]:
        return with_flash("/account/billing",
                          "There's no card subscription on this account yet.", "error")
    try:
        portal_url = billing.create_portal_session(sub["stripe_customer_id"])
    except RuntimeError as exc:
        return with_flash("/account/billing", str(exc), "error")
    return redirect(portal_url)


@router.get("/admin/billing/portal")
def admin_billing_portal(request):
    """Sends an establishment admin to Stripe's hosted billing portal to cancel,
    change card or download invoices. Same reasoning as the individual portal:
    cancellation, proration and dunning are Stripe's job, not Phil's.

    Only useful for a card-paying establishment. Invoice-billed schools have no
    Stripe customer, so they are told to email instead of hitting an error."""
    user, err = require(request, roles=["admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        sub = conn.execute(
            """SELECT * FROM subscriptions WHERE establishment_id=?
               ORDER BY id DESC LIMIT 1""",
            (user["establishment_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not sub or not sub["stripe_customer_id"]:
        return with_flash("/admin",
                          "This establishment is billed by invoice. Email hello@phileducation.co.uk to change or cancel.",
                          "error")
    try:
        portal_url = billing.create_portal_session(sub["stripe_customer_id"])
    except RuntimeError as exc:
        return with_flash("/admin", str(exc), "error")
    return redirect(portal_url)


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
            metadata = stripe_field(session_obj, "metadata", {})
            estab_id = (stripe_field(session_obj, "client_reference_id")
                        or stripe_field(metadata, "establishment_id"))
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
                        (plan_type, included_seats, pupil_cap,
                         stripe_field(session_obj, "customer"),
                         stripe_field(session_obj, "subscription"), sub["id"]),
                    )
                    db.log_action(conn, None, "card_payment_completed", "subscription", sub["id"],
                                  f"Stripe checkout completed for {estab['name']}")

        elif event["type"] in ("customer.subscription.deleted", "customer.subscription.paused"):
            stripe_sub_id = stripe_field(event["data"]["object"], "id")
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
        # Signed in is not the same as entitled: without this, an enrolment id in
        # the URL is all it takes to read another school's certificate.
        if not may_access_enrolment(conn, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        cert = conn.execute("SELECT * FROM certificates WHERE enrolment_id=?",
                             (request.params["enrolment_id"],)).fetchone()
    finally:
        conn.close()
    if not cert:
        # Not an error: the course simply hasn't been closed yet. Say which step
        # is outstanding rather than showing a dead end.
        conn2 = db.get_conn()
        try:
            row = conn2.execute("SELECT pupil_id, status FROM enrolments WHERE id=?",
                                (request.params["enrolment_id"],)).fetchone()
        finally:
            conn2.close()
        if row and row["status"] == "completed":
            return with_flash(f"/mentor/enrolment/{request.params['enrolment_id']}/wrap-up",
                              "The certificate is issued once the course is closed.", "error")
        return Response("Certificate not found", status="404 Not Found")
    # Always rebuilt, never served from disk. A stored PDF freezes whatever was
    # true the day it was made: the mentor's name, the school's name, the date
    # format. Reassign a pupil or change the wording and the file quietly
    # disagrees with the record it came from. Everything needed is in the
    # database, and a certificate is one page, so regenerating each time is
    # cheaper than a class of bug that only shows up on paper.
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT p.forename, p.surname, c.title AS course_title,
                      c.module_number AS module_number,
                      est.name AS establishment_name,
                      u.name AS mentor_name
               FROM enrolments e JOIN pupils p ON p.id=e.pupil_id
               JOIN courses c ON c.id=e.course_id
               LEFT JOIN establishments est ON est.id = p.establishment_id
               LEFT JOIN users u ON u.id = e.mentor_id
               WHERE e.id=?""",
            (request.params["enrolment_id"],),
        ).fetchone()
        if not row:
            return Response("Certificate not found", status="404 Not Found")
        path = pdfgen.certificate_pdf(
            f"{row['forename']} {row['surname']}", row["course_title"],
            cert["issued_date"], request.params["enrolment_id"],
            establishment_name=row["establishment_name"],
            mentor_name=row["mentor_name"],
            module_number=row["module_number"])
        conn.execute("UPDATE certificates SET pdf_path=? WHERE enrolment_id=?",
                     (path, request.params["enrolment_id"]))
        conn.commit()
    finally:
        conn.close()
    return pdf_response(path, "certificate.pdf")


@router.get("/mentor/session/record/<record_id>/edit")
def session_record_edit(request):
    """Reopens a recorded session as the full session page, notes in place.

    The mentor sees exactly what they saw when recording it — the course text,
    the steps, the resource cards — rather than a stripped-down form. Editing
    does not move the course: current_week and status are untouched."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        record = conn.execute("SELECT * FROM session_records WHERE id=?",
                              (request.params["record_id"],)).fetchone()
        if not record:
            return Response("Session record not found", status="404 Not Found")
        enrolment = conn.execute(
            """SELECT e.*, p.forename, p.surname, p.establishment_id,
                      c.title AS course_title, c.module_number AS course_module_number
               FROM enrolments e JOIN pupils p ON p.id=e.pupil_id
               JOIN courses c ON c.id=e.course_id WHERE e.id=?""",
            (record["enrolment_id"],)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")

        week = conn.execute("SELECT * FROM weeks WHERE id=?", (record["week_id"],)).fetchone()
        completed_records = conn.execute(
            """SELECT r.*, w.week_number AS wn, w.title AS week_title
               FROM session_records r JOIN weeks w ON w.id=r.week_id
               WHERE r.enrolment_id=? ORDER BY w.week_number""",
            (record["enrolment_id"],)).fetchall()
    finally:
        conn.close()

    week = dict(week, resources=json.loads(week["resources"] or "[]"))
    week["resource_items"] = resource_items_for(
        enrolment["course_module_number"], week["resources"])
    attach_figures(week["resource_items"])
    week["resource_steps"] = assign_resources_to_steps(week, week["resource_items"])
    for step, group in week["resource_steps"].items():
        for item in group:
            item["_step"] = step
    week["resource_lines"] = assign_resources_to_lines(week, week["resource_items"])

    # what_happened was written as "Check-in: ... / Input: ... / Activity: ...",
    # a format this app controls, so it can be split back into the three fields
    # the mentor originally typed into.
    draft = _split_what_happened(record["what_happened"])
    draft["reflect_note"] = record["reflection_goal"] or ""
    draft["next_session_note"] = record["mentor_notes"] or ""

    conn3 = db.get_conn()
    try:
        entries = resource_entries_for(conn3, record["enrolment_id"], record["week_id"])
    finally:
        conn3.close()

    response = render("session_form.html", user=user, enrolment=enrolment, week=week,
                      entries=entries,
                      next_week_number=week["week_number"], completed_records=completed_records,
                      prev_record=None, prev_week_items=[], draft=draft, progress=[],
                      upcoming_weeks=[], editing_record=record,
                      flash=flash_from_query(request))
    response.headers.append(("Cache-Control", "no-store, must-revalidate"))
    return response


def _split_what_happened(text):
    """Turns the stored summary back into the three note fields it came from."""
    out = {"checkin_note": "", "input_note": "", "activity_note": ""}
    labels = [("Check-in:", "checkin_note"), ("Input:", "input_note"), ("Activity:", "activity_note")]
    if not text:
        return out
    positions = []
    for label, key in labels:
        idx = text.find(label)
        if idx >= 0:
            positions.append((idx, len(label), key))
    positions.sort()
    for i, (idx, label_len, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[key] = text[idx + label_len:end].strip()
    if not positions:
        # Written before this format, or edited by hand: keep it rather than lose it.
        out["checkin_note"] = text.strip()
    return out


@router.post("/mentor/session/record/<record_id>/edit")
def session_record_edit_submit(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    safeguarding_note = request.field("safeguarding_note", "").strip()
    if not safeguarding_note:
        return with_flash(f"/mentor/session/record/{request.params['record_id']}/edit",
                          "The safeguarding note is mandatory, even to record 'no concerns'.",
                          "error")
    conn = db.get_conn()
    try:
        record = conn.execute("SELECT * FROM session_records WHERE id=?",
                              (request.params["record_id"],)).fetchone()
        if not record:
            return Response("Session record not found", status="404 Not Found")
        estab = conn.execute(
            "SELECT establishment_id FROM pupils WHERE id=(SELECT pupil_id FROM enrolments WHERE id=?)",
            (record["enrolment_id"],)).fetchone()
        if not estab or estab["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")

        # The edit form is the full session page, so it posts the same five note
        # fields as recording does. Rebuild what_happened the same way, or the
        # two paths would store the record in different shapes.
        parts = []
        for label, field in (("Check-in", "checkin_note"), ("Input", "input_note"),
                             ("Activity", "activity_note")):
            value = request.field(field, "").strip()
            if value:
                parts.append(f"{label}: {value}")
        save_resource_entries(conn, record["enrolment_id"], record["week_id"],
                              request, user["id"])
        conn.execute(
            """UPDATE session_records
               SET what_happened=?, reflection_goal=?, mentor_notes=?,
                   mood_rating=?, engagement_rating=?,
                   safeguarding_flag=?, safeguarding_note=?, pdf_path=NULL
               WHERE id=?""",
            ("\n\n".join(parts),
             request.field("reflect_note", "").strip(),
             request.field("next_session_note", "").strip(),
             request.field("mood_rating") or None,
             request.field("engagement_rating") or None,
             1 if request.field("safeguarding_flag") == "yes" else 0,
             safeguarding_note,
             request.params["record_id"]))
        # pdf_path is cleared rather than regenerated here: the download route
        # rebuilds it on demand, so the PDF can never disagree with the record.
        db.log_action(conn, user["id"], "session_record_edited", "session_record",
                      record["id"], f"week {record['week_id']}")
        conn.commit()
        enrolment_id = record["enrolment_id"]
        pupil_id = conn.execute("SELECT pupil_id FROM enrolments WHERE id=?",
                                (enrolment_id,)).fetchone()["pupil_id"]
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", "Session record updated.", "ok")


# A follow-up is agreed as a week, not a day, so it isn't late until that week
# is out. It then turns red rather than waiting: with the push-back button gone
# there is nothing to defer to, and a soft amber on work already a fortnight old
# reads as "no rush" on the one thing that shows whether a course held.


def pretty_date(iso):
    """A date a mentor can read at a glance: "Tue 8 Sep", not "2026-09-08"."""
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return "%s %d %s" % (d.strftime("%a"), d.day, d.strftime("%b"))


def pretty_week(iso):
    """A week as "w/c 27 Jul". No day name: a week commencing is always a Monday."""
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return "w/c %d %s" % (d.day, d.strftime("%b"))


def uk_date_short(iso):
    """Kept for anywhere a bare numeric date is wanted: 07/09/2026."""
    return uk_date(iso)


def review_week_of(date_string):
    """The Monday of the week a review falls in. Schools plan in weeks, not days."""
    try:
        d = datetime.date.fromisoformat(date_string)
    except (TypeError, ValueError):
        return None
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def review_overdue_from(date_string):
    """The date after which a follow-up counts as missed.

    The end of the week it was due in. A follow-up is agreed as a week rather
    than a day, so it isn't late until that week is out — but once it is, it is
    late, and the page says so. There used to be a fortnight's grace on top of
    this, from when a mentor could push the date back; with that gone the grace
    only delayed the prompt on work nobody was going to do sooner.
    """
    try:
        d = datetime.date.fromisoformat(date_string)
    except (TypeError, ValueError):
        return None
    # From the Monday of that week to the Sunday at its end.
    monday = d - datetime.timedelta(days=d.weekday())
    return (monday + datetime.timedelta(days=6)).isoformat()


@router.post("/mentor/enrolment/<enrolment_id>/wrap-up")
def course_wrap_up(request):
    """Closes a course: the review date, then the certificate.

    Gating the certificate on this is deliberate. Left optional, the follow-up is
    the thing that never gets done — and it is part of what a school is buying.
    It is asked for while the mentor is still on the completion screen, so
    nothing is delayed for the pupil."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]

    # How the course went is captured in session 6's support plan now, so the
    # wrap-up asks only for the follow-up. Asking twice got the same answer twice,
    # or an empty one.
    review_date = request.field("review_date", "").strip()
    review_note = request.field("review_note", "").strip()

    if not review_date:
        return with_flash(f"/mentor/enrolment/{enrolment_id}/wrap-up",
                          "A date for the follow-up chat is needed before the course "
                          "can be closed.", "error")

    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.forename, p.surname, p.establishment_id,
                      c.title AS course_title, c.module_number
               FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id WHERE e.id=?""",
            (enrolment_id,)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")

        conn.execute("UPDATE enrolments SET review_date=?, review_note=?, review_done=0 WHERE id=?",
                     (review_date, review_note or None, enrolment_id))

        # Issue the certificate now the review point is set.
        pupil_name = f"{enrolment['forename']} {enrolment['surname']}"
        already = conn.execute("SELECT id FROM certificates WHERE enrolment_id=?",
                               (enrolment_id,)).fetchone()
        if not already:
            issued = datetime.date.today().isoformat()
            estab = conn.execute("SELECT name FROM establishments WHERE id=?",
                                 (enrolment["establishment_id"],)).fetchone()
            cert_path = pdfgen.certificate_pdf(
                pupil_name, enrolment["course_title"], issued, enrolment_id,
                establishment_name=estab["name"] if estab else None,
                mentor_name=user["name"],
                module_number=enrolment["module_number"])
            conn.execute(
                "INSERT INTO certificates (enrolment_id, issued_date, pdf_path) VALUES (?,?,?)",
                (enrolment_id, issued, cert_path))
        db.log_action(conn, user["id"], "course_wrapped_up", "enrolment", enrolment_id, review_date)
        conn.commit()
        pupil_id = enrolment["pupil_id"]
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}",
                      f"Course closed and {pupil_name}'s certificate issued.", "ok")


@router.get("/mentor/enrolment/<enrolment_id>/wrap-up")
def course_wrap_up_form(request):
    """The wrap-up screen, reachable again if it wasn't finished first time."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.forename, p.surname, p.establishment_id, p.id AS pupil_id,
                      c.title AS course_title
               FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id WHERE e.id=?""",
            (request.params["enrolment_id"],)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        reflection = conn.execute("SELECT * FROM completion_reflections WHERE enrolment_id=?",
                                  (request.params["enrolment_id"],)).fetchone()
    finally:
        conn.close()
    suggested = enrolment["review_date"] or (
        datetime.date.today() + datetime.timedelta(days=21)).isoformat()
    # The follow-up can't be recorded until a fortnight after the last session,
    # so the wrap-up mustn't let a mentor book one before then — otherwise the
    # date arrives and the form refuses it.
    conn2 = db.get_conn()
    try:
        earliest = follow_up_earliest(conn2, enrolment["id"])
    finally:
        conn2.close()
    if earliest and suggested < earliest:
        suggested = earliest
    return render("course_complete.html", user=user, earliest_review=earliest,
                  pupil_name=f"{enrolment['forename']} {enrolment['surname']}",
                  course_title=enrolment["course_title"],
                  enrolment_id=enrolment["id"], pupil_id=enrolment["pupil_id"],
                  suggested_review_date=suggested, reflection=reflection,
                  flash=flash_from_query(request))


@router.post("/mentor/enrolment/<enrolment_id>/review")
def set_review_point(request):
    """Agrees a date to check back in after a course ends.

    Support stopping dead at session five is the thing schools notice. A date
    and a note is the smallest thing that fixes it: the mentor sees it coming,
    and the pupil is told it's coming."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    review_date = request.field("review_date", "").strip()
    review_note = request.field("review_note", "").strip()
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.establishment_id FROM enrolments e
               JOIN pupils p ON p.id = e.pupil_id WHERE e.id=?""",
            (request.params["enrolment_id"],)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        if not may_handle_review(conn, enrolment, user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        conn.execute(
            "UPDATE enrolments SET review_date=?, review_note=?, review_done=0 WHERE id=?",
            (review_date or None, review_note or None, request.params["enrolment_id"]))
        db.log_action(conn, user["id"], "review_point_set", "enrolment",
                      enrolment["id"], review_date)
        conn.commit()
        pupil_id = enrolment["pupil_id"]
    finally:
        conn.close()
    message = (f"Follow-up chat booked for {uk_date(review_date)}." if review_date
               else "Follow-up chat date cleared.")
    return with_flash(f"/mentor/pupils/{pupil_id}", message, "ok")


# The push-back route is gone with the button. Moving the date only deferred
# the problem, and an overdue chat can still be recorded whenever it actually
# happens, so nothing is lost by letting it run late and show as late.

FOLLOW_UP_MIN_DAYS = 14

HELPED_LABELS = {
    "better": "Clearly better",
    "some": "Some change",
    "none": "No change",
    "worse": "Worse",
}
BEHAVIOUR_LABELS = {
    "no": "Not showing",
    "sometimes": "Sometimes",
    "yes": "Still showing",
}
NEXT_STEP_LABELS = {
    "none": "Nothing further needed",
    "monitor": "Keep an eye on it",
    "another_course": "Recommend another course",
    "refer": "Refer on to someone else",
}


def follow_up_for(conn, enrolment_id):
    """The follow-up chat recorded against a course, if one has been."""
    return conn.execute("SELECT * FROM follow_ups WHERE enrolment_id=?",
                        (enrolment_id,)).fetchone()


def follow_up_earliest(conn, enrolment_id):
    """The date from which a follow-up starts to mean something.

    A fortnight after the last session. A chat three days after a course ends
    can't tell anyone whether change held. This is shown as advice rather than
    enforced: a pupil moving school on Friday is exactly the case where an early
    chat beats no chat, and the mentor is the one who can see that.
    """
    last = conn.execute(
        "SELECT max(date) FROM session_records WHERE enrolment_id=?",
        (enrolment_id,)).fetchone()[0]
    if not last:
        return None
    try:
        return (datetime.date.fromisoformat(last)
                + datetime.timedelta(days=FOLLOW_UP_MIN_DAYS)).isoformat()
    except (TypeError, ValueError):
        return None


@router.get("/mentor/enrolment/<enrolment_id>/follow-up")
def follow_up_form(request):
    """The follow-up chat: what the pupil said a few weeks on."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.forename, p.surname, p.establishment_id, p.id AS pupil_id,
                      c.title AS course_title
               FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id WHERE e.id=?""",
            (request.params["enrolment_id"],)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        if not may_handle_review(conn, enrolment, user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        existing = follow_up_for(conn, enrolment["id"])
        earliest = follow_up_earliest(conn, enrolment["id"])
    finally:
        conn.close()

    if existing:
        return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}",
                          "That follow-up is already recorded.", "error")

    today = datetime.date.today().isoformat()
    return render("follow_up.html", user=user, enrolment=enrolment,
                  pupil_name=f"{enrolment['forename']} {enrolment['surname']}",
                  forename=enrolment["forename"],
                  course_title=enrolment["course_title"],
                  earliest=earliest, today=today,
                  min_days=FOLLOW_UP_MIN_DAYS,
                  flash=flash_from_query(request))


@router.post("/mentor/enrolment/<enrolment_id>/follow-up")
def follow_up_save(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    enrolment_id = request.params["enrolment_id"]
    back = f"/mentor/enrolment/{enrolment_id}/follow-up"

    date = request.field("date", "").strip()
    helped = request.field("helped", "").strip()
    behaviour = request.field("behaviour", "").strip()
    pupil_voice = request.field("pupil_voice", "").strip()
    next_step = request.field("next_step", "").strip()
    next_step_note = request.field("next_step_note", "").strip()
    safeguarding_flag = 1 if request.field("safeguarding_flag") == "yes" else 0
    safeguarding_note = request.field("safeguarding_note", "").strip()

    if helped not in HELPED_LABELS or behaviour not in BEHAVIOUR_LABELS \
            or next_step not in NEXT_STEP_LABELS:
        return with_flash(back, "Answer all three questions before saving.", "error")
    # Mandatory even to record "no concerns", exactly as on a session record: a
    # blank box can mean "nothing to report" or "never asked", and the two are
    # not the same thing to a designated safeguarding lead.
    if not safeguarding_note:
        return with_flash(back,
            "The safeguarding note is mandatory, even to record 'no concerns'.", "error")

    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.forename, p.surname, p.establishment_id, p.id AS pupil_id,
                      c.title AS course_title
               FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id WHERE e.id=?""",
            (enrolment_id,)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        if not may_handle_review(conn, enrolment, user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        if follow_up_for(conn, enrolment_id):
            return with_flash(f"/mentor/pupils/{enrolment['pupil_id']}",
                              "That follow-up is already recorded.", "error")

        if not date:
            date = datetime.date.today().isoformat()
        if date > datetime.date.today().isoformat():
            return with_flash(back, "A follow-up can't be dated in the future.", "error")

        conn.execute(
            """INSERT INTO follow_ups (enrolment_id, date, helped, behaviour, pupil_voice,
                                       next_step, next_step_note, safeguarding_flag,
                                       safeguarding_note, recorded_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (enrolment_id, date, helped, behaviour, pupil_voice or None,
             next_step, next_step_note or None, safeguarding_flag,
             safeguarding_note, user["id"], db.now()))
        # The follow-up being recorded is what closes it, so the mentor never
        # has to mark it done separately and the two can't disagree.
        conn.execute("UPDATE enrolments SET review_done=1 WHERE id=?", (enrolment_id,))
        db.log_action(conn, user["id"], "follow_up_recorded", "enrolment", enrolment_id,
                      "%s / %s" % (helped, behaviour))
        conn.commit()
        pupil_id = enrolment["pupil_id"]
        forename = enrolment["forename"]
    finally:
        conn.close()

    message = f"Follow-up recorded for {forename}."
    if next_step == "another_course":
        message += " You noted another course would help — enrol from here."
    return with_flash(f"/mentor/pupils/{pupil_id}", message, "success")


@router.post("/mentor/enrolment/<enrolment_id>/review/done")
def complete_review_point(request):
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.*, p.establishment_id FROM enrolments e
               JOIN pupils p ON p.id = e.pupil_id WHERE e.id=?""",
            (request.params["enrolment_id"],)).fetchone()
        if not enrolment or enrolment["establishment_id"] != user["establishment_id"]:
            return Response("Not authorised for this area.", status="403 Forbidden")
        if not may_handle_review(conn, enrolment, user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        conn.execute("UPDATE enrolments SET review_done=1 WHERE id=?",
                     (request.params["enrolment_id"],))
        db.log_action(conn, user["id"], "review_point_completed", "enrolment", enrolment["id"])
        conn.commit()
        pupil_id = enrolment["pupil_id"]
    finally:
        conn.close()
    return with_flash(f"/mentor/pupils/{pupil_id}", "Review marked as done.", "ok")


def may_access_pupil(conn, pupil_id, user):
    """Whether this user may see a pupil's record.

    Access follows involvement, not job title. A mentor sees the pupils they
    mentor; an admin sees the whole school. Mentoring notes are welfare records
    about a child, and a colleague who has nothing to do with that child has no
    reason to read them. Where cover is needed, an admin reassigns the pupil,
    which is one click and leaves a trail."""
    row = conn.execute("SELECT establishment_id FROM pupils WHERE id=?", (pupil_id,)).fetchone()
    if not row:
        return False
    if user["role"] == "phil_staff":
        return True
    # Parents are checked first: they belong to no establishment, so an
    # establishment comparison would reject them before their link is considered.
    if user["role"] == "parent_carer":
        link = conn.execute(
            "SELECT 1 FROM pupil_parent_links WHERE parent_user_id=? AND pupil_id=?",
            (user["id"], pupil_id)).fetchone()
        return bool(link)
    if row["establishment_id"] != user["establishment_id"]:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] == "mentor":
        own = conn.execute(
            "SELECT 1 FROM enrolments WHERE pupil_id=? AND mentor_id=? LIMIT 1",
            (pupil_id, user["id"])).fetchone()
        return bool(own)
    return False


def may_access_enrolment(conn, enrolment_id, user):
    """Whether this user may see anything belonging to this enrolment.

    Being signed in is not enough. Without this an enrolment id in a URL is the
    only thing standing between any account and another school's pupil records,
    and ids are sequential."""
    row = conn.execute(
        """SELECT e.mentor_id, e.pupil_id, p.establishment_id
           FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
           WHERE e.id = ?""", (enrolment_id,)).fetchone()
    if not row:
        return False
    role = user["role"]
    if role == "phil_staff":
        return True
    if role in ("admin", "mentor") and row["establishment_id"] == user["establishment_id"]:
        # A mentor sees their own pupils; an admin sees the whole establishment.
        if role == "admin" or row["mentor_id"] == user["id"]:
            return True
        # Also the pupil's current mentor, even on a course someone else ran.
        # Reassignment moves the active courses and leaves the finished ones
        # attributed to whoever delivered them, so without this the new mentor
        # sees a certificate button on the pupil's record and is refused when
        # they press it — may_access_pupil grants on any involvement while this
        # demanded ownership of the enrolment itself.
        return bool(conn.execute(
            """SELECT 1 FROM enrolments WHERE pupil_id=? AND mentor_id=?
                 AND status='active' LIMIT 1""",
            (row["pupil_id"], user["id"])).fetchone())
    if role == "parent_carer":
        link = conn.execute(
            "SELECT 1 FROM pupil_parent_links WHERE parent_user_id = ? AND pupil_id = ?",
            (user["id"], row["pupil_id"])).fetchone()
        return bool(link)
    return False


def may_handle_review(conn, enrolment, user):
    """Whether this user may set or clear this enrolment's follow-up chat.

    A follow-up outlives the course it belongs to: the enrolment is already
    completed by the time a date is agreed. Ownership therefore follows the
    pupil rather than the enrolment. When a pupil is reassigned their active
    courses move but the completed one does not, so a review left keyed to the
    enrolment would sit with a mentor who no longer works with that child, and
    a mentor who has left the school cannot clear it at all.

    Where a pupil has no active mentoring left, the review stays with whoever
    ran the course. The caller checks the establishment first.
    """
    role = user["role"]
    if role in ("phil_staff", "admin"):
        return True
    if role != "mentor":
        return False
    mine = conn.execute(
        "SELECT 1 FROM enrolments WHERE pupil_id=? AND mentor_id=? AND status='active' LIMIT 1",
        (enrolment["pupil_id"], user["id"])).fetchone()
    if mine:
        return True
    held_by_someone = conn.execute(
        "SELECT 1 FROM enrolments WHERE pupil_id=? AND status='active' LIMIT 1",
        (enrolment["pupil_id"],)).fetchone()
    if held_by_someone:
        return False
    if enrolment["mentor_id"] == user["id"]:
        return True
    # Nobody currently mentors this pupil and the mentor who ran the course has
    # left, so the follow-up would sit with an account that cannot sign in. It
    # falls to an active mentor at the school rather than to nobody; admins are
    # already covered above.
    owner = conn.execute("SELECT status FROM users WHERE id=?",
                         (enrolment["mentor_id"],)).fetchone()
    return bool(owner and owner["status"] != "active")


def support_plan_for(conn, enrolment_id):
    """The mentor's support plan: what they wrote in the staff-only session.

    Stored as an ordinary session record, so it needs no separate table — but it
    is the one piece of a course that other staff actually read, so it is pulled
    out by name wherever it is needed."""
    row = conn.execute(
        """SELECT r.what_happened FROM session_records r
           JOIN weeks w ON w.id = r.week_id
           WHERE r.enrolment_id = ? AND w.staff_only = 1
           ORDER BY w.week_number DESC LIMIT 1""",
        (enrolment_id,)).fetchone()
    if not row or not row["what_happened"]:
        return None
    # The section labels are kept: on a staff session they are the plan's
    # structure, not form scaffolding.
    return "\n".join(line.strip() for line in row["what_happened"].splitlines() if line.strip())


@router.get("/report/pupil/<pupil_id>/pdf")
def pupil_report_download(request):
    """Every course a pupil has done, with each course summary.

    The per-course report answers "how did that course go". This answers "what
    do I need to know about this child", which is what a new form tutor asks."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        pupil = conn.execute(
            """SELECT p.*, e.name AS establishment_name
               FROM pupils p LEFT JOIN establishments e ON e.id = p.establishment_id
               WHERE p.id=?""", (request.params["pupil_id"],)).fetchone()
        if not pupil or not may_access_pupil(conn, request.params["pupil_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        # Whole history by default — a child's record is cumulative and that is
        # usually what's wanted. A year can be asked for when the question is
        # "what did we do with her in Year 8".
        year, y_from, y_to, _ = chosen_year(request, conn, pupil["establishment_id"])
        rows = conn.execute(
            """SELECT en.id, en.start_date, en.status, en.current_week,
                      c.title, u.name AS mentor_name,
                      (SELECT COUNT(*) FROM session_records WHERE enrolment_id = en.id)
                        AS sessions_recorded,
                      (SELECT COUNT(*) FROM session_records
                        WHERE enrolment_id = en.id AND safeguarding_flag = 1)
                        AS safeguarding_count
               FROM enrolments en
               JOIN courses c ON c.id = en.course_id
               LEFT JOIN users u ON u.id = en.mentor_id
               WHERE en.pupil_id = ?"""
            + ("""  AND EXISTS (SELECT 1 FROM session_records sr
                                WHERE sr.enrolment_id = en.id
                                  AND sr.date BETWEEN ? AND ?)""" if y_from else "")
            + " ORDER BY en.start_date, en.id",
            ([request.params["pupil_id"]] + ([y_from, y_to] if y_from else []))).fetchall()
        courses = []
        for r in rows:
            fu = follow_up_for(conn, r["id"])
            fu_dict = None
            if fu:
                fu_dict = dict(fu)
                fu_dict["helped_label"] = HELPED_LABELS.get(fu["helped"], fu["helped"])
                fu_dict["behaviour_label"] = BEHAVIOUR_LABELS.get(fu["behaviour"], fu["behaviour"])
                fu_dict["next_step_label"] = NEXT_STEP_LABELS.get(fu["next_step"], fu["next_step"])
            courses.append(dict(r, mentor_name=r["mentor_name"] or "Mentor",
                                support_plan=support_plan_for(conn, r["id"]),
                                follow_up=fu_dict))
    finally:
        conn.close()
    path = pdfgen.pupil_report_pdf(
        pupil["id"], f"{pupil['forename']} {pupil['surname']}",
        pupil["establishment_name"], courses, period=period_label(year))
    return pdf_response(path, "pupil-report.pdf")


@router.get("/mentor/enrolment/<enrolment_id>/summaries/pdf")
def session_summaries_download(request):
    """The five session summaries on one sheet, for writing the support plan."""
    user, err = require(request, roles=["mentor", "admin"])
    if err:
        return err
    conn = db.get_conn()
    try:
        enrolment = conn.execute(
            """SELECT e.id, p.forename, p.surname, p.establishment_id,
                      c.title AS course_title, u.name AS mentor_name
               FROM enrolments e
               JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id
               LEFT JOIN users u ON u.id = e.mentor_id
               WHERE e.id=?""",
            (request.params["enrolment_id"],)).fetchone()
        if not enrolment or not may_access_enrolment(
                conn, request.params["enrolment_id"], user):
            return Response("Not authorised for this area.", status="403 Forbidden")
        rows = conn.execute(
            """SELECT r.date, r.mentor_notes, r.reflection_goal, r.mood_rating,
                      r.engagement_rating, r.safeguarding_flag,
                      w.week_number, w.title AS week_title
               FROM session_records r JOIN weeks w ON w.id = r.week_id
               WHERE r.enrolment_id=? AND w.week_number <= ?
               ORDER BY w.week_number""",
            (request.params["enrolment_id"], PUPIL_SESSIONS)).fetchall()
    finally:
        conn.close()
    path = pdfgen.session_summaries_pdf(
        enrolment["id"], f"{enrolment['forename']} {enrolment['surname']}",
        enrolment["course_title"], enrolment["mentor_name"] or "Mentor", rows)
    return pdf_response(path, "session-summaries.pdf")


@router.get("/session/<record_id>/pdf")
def session_pdf_download(request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    conn = db.get_conn()
    try:
        record = conn.execute("SELECT * FROM session_records WHERE id=?",
                               (request.params["record_id"],)).fetchone()
        # This document carries the mentor's notes and the safeguarding note, so
        # entitlement matters more here than anywhere else in the app.
        #
        # A linked parent passes may_access_enrolment — correct for a certificate,
        # wrong for this. A parent is entitled to know their child is being
        # mentored and what to do at home; the mentor's professional record of
        # each session is not written for them, and a school decides what to
        # share from it and when.
        if record and (user["role"] == "parent_carer"
                       or not may_access_enrolment(conn, record["enrolment_id"], user)):
            return Response("Not authorised for this area.", status="403 Forbidden")
    finally:
        conn.close()
    if not record:
        return Response("Session record not found", status="404 Not Found")
    # Rebuilt on every download, like the certificate. A stored file freezes
    # the week title, the mentor's name and the pupil's own work as they were
    # the day it was written — a session PDF made before the session 6 rename
    # still calls it a support plan. Editing a record already clears the path;
    # this covers everything that changes around the record instead.
    conn = db.get_conn()
    try:
        ctx = conn.execute(
            """SELECT e.id AS enrolment_id, p.forename, p.surname,
                      c.title AS course_title, w.title AS week_title,
                      u.name AS mentor_name
               FROM session_records r
               JOIN enrolments e ON e.id=r.enrolment_id
               JOIN pupils p ON p.id=e.pupil_id
               JOIN courses c ON c.id=e.course_id
               JOIN weeks w ON w.id=r.week_id
               LEFT JOIN users u ON u.id=r.recorded_by
               WHERE r.id=?""",
            (request.params["record_id"],),
        ).fetchone()
        if not ctx:
            return Response("Session record not found", status="404 Not Found")
        enrolment = conn.execute("SELECT * FROM enrolments WHERE id=?",
                                  (ctx["enrolment_id"],)).fetchone()
        resource_work = resource_work_for(conn, ctx["enrolment_id"], record["week_id"])
        path = pdfgen.session_record_pdf(
            record, enrolment, f"{ctx['forename']} {ctx['surname']}",
            ctx["course_title"], ctx["week_title"], ctx["mentor_name"] or "Mentor",
            resource_work=resource_work)
        conn.execute("UPDATE session_records SET pdf_path=? WHERE id=?",
                     (path, request.params["record_id"]))
        conn.commit()
    finally:
        conn.close()
    return pdf_response(path, "session-record.pdf")


_LEGAL_DOC_ROUTES = {
    "white-paper": ("white_paper", "phil-white-paper.pdf"),
    "privacy-policy": ("privacy_policy", "phil-privacy-policy.pdf"),
    "terms-of-service": ("terms_of_service", "phil-terms-of-service.pdf"),
    "safeguarding-policy": ("safeguarding_policy", "phil-safeguarding-policy-template.pdf"),
}


@router.get("/legal/<doc_slug>")
def legal_doc_pdf(request):
    slug = request.params["doc_slug"]
    entry = _LEGAL_DOC_ROUTES.get(slug)
    if not entry:
        return Response("Document not found", status="404 Not Found")
    key, filename = entry
    docs = _load_legal_docs()
    paras = docs.get(key)
    if not paras:
        return Response("Document not found", status="404 Not Found")
    path = pdfgen.legal_doc_pdf(key, paras)
    return pdf_response(path, filename)


# --------------------------------------------------------------------- wsgi --

wsgi_app = make_wsgi_app(router, static_dir=STATIC_DIR)


# ---------------------------------------------------------- password reset --
# Routes register on import, so their position in this file does not matter.
# Everything below is self-contained: no new imports at the top of the file,
# no new modules.


def _send_reset_email(to_email, link):
    """Emails one reset link. Returns True only if a provider accepted it.

    Phil has no email delivery anywhere else: invites create accounts directly
    and alerts are in-app. Set RESEND_API_KEY or POSTMARK_SERVER_TOKEN, plus
    MAIL_FROM, to turn real sending on. With neither set the link is written to
    the server log instead, so the flow still completes and can be tested
    before an email provider exists.

    Never raises: a provider outage must not take down the page that triggered
    it, and the caller shows the same message either way so a wrong email
    address cannot be told apart from a right one."""
    import urllib.request

    subject = "Reset your Phil password"
    body = ("Someone asked to reset the password on your Phil account.\n\n"
            f"Set a new one here, within the next hour:\n{link}\n\n"
            "If this wasn't you, ignore this email. Your password has not changed.")

    resend_key = os.environ.get("RESEND_API_KEY")
    postmark_token = os.environ.get("POSTMARK_SERVER_TOKEN")
    mail_from = os.environ.get("MAIL_FROM", "Phil <no-reply@phileducation.co.uk>")

    if not (resend_key or postmark_token):
        print(f"[reset] No email provider configured. Link for {to_email}: {link}")
        return False

    try:
        if resend_key:
            url = "https://api.resend.com/emails"
            payload = {"from": mail_from, "to": [to_email], "subject": subject, "text": body}
            headers = {"Authorization": f"Bearer {resend_key}",
                       "Content-Type": "application/json",
                       "User-Agent": "Phil/1.0"}
        else:
            url = "https://api.postmarkapp.com/email"
            payload = {"From": mail_from, "To": to_email, "Subject": subject, "TextBody": body}
            headers = {"X-Postmark-Server-Token": postmark_token,
                       "Content-Type": "application/json",
                       "Accept": "application/json",
                       "User-Agent": "Phil/1.0"}
        request_obj = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(request_obj, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"[reset] Send to {to_email} failed: {exc}")
        return False


@router.get("/forgot-password")
def forgot_password_form(request):
    return render("forgot_password.html", user=None, flash=flash_from_query(request))


@router.post("/forgot-password")
def forgot_password_submit(request):
    email = request.field("email", "").strip().lower()
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND status = 'active'", (email,)
        ).fetchone()
        if row:
            token = authlib.create_reset_token(conn, row["id"])
            conn.commit()
            base = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
            _send_reset_email(row["email"], f"{base}/reset-password/{token}")
    finally:
        conn.close()
    # The same answer either way. Anything else turns this form into a way of
    # testing which staff emails are registered with which school.
    return with_flash("/login", "If that email has a Phil account, a reset link is on its way.", "ok")


@router.get("/reset-password/<token>")
def reset_password_form(request):
    token = request.params["token"]
    conn = db.get_conn()
    try:
        row = authlib.user_for_reset_token(conn, token)
    finally:
        conn.close()
    if not row:
        return with_flash("/forgot-password",
                          "That link has expired or has already been used. Request a new one.", "error")
    return render("reset_password.html", user=None, email=row["email"], token=token,
                  flash=flash_from_query(request))


@router.post("/reset-password/<token>")
def reset_password_submit(request):
    token = request.params["token"]
    new_password = request.field("new_password", "")
    confirm_password = request.field("confirm_password", "")
    conn = db.get_conn()
    try:
        row = authlib.user_for_reset_token(conn, token)
        if not row:
            return with_flash("/forgot-password",
                              "That link has expired or has already been used. Request a new one.", "error")
        if len(new_password) < 8:
            return with_flash(f"/reset-password/{token}",
                              "New password needs at least 8 characters.", "error")
        if new_password != confirm_password:
            return with_flash(f"/reset-password/{token}",
                              "The two passwords do not match.", "error")
        authlib.set_password(conn, row["id"], new_password)
        authlib.consume_reset_token(conn, token)
        authlib.destroy_other_sessions(conn, row["id"])
        conn.commit()
    finally:
        conn.close()
    return with_flash("/login", "Password updated. Sign in with your new password.", "ok")


@router.post("/admin/mentors/<mentor_id>/reset-password")
def admin_mentor_reset_password(request):
    """Issues a new temporary password for one of this establishment's own
    mentors, shown once for the admin to pass on in person.

    Email is the wrong channel in a school: staff inboxes are filtered, shared,
    or only checked on site, and a mentor locked out ten minutes before a
    session cannot wait for one. Scoped hard to the admin's own establishment
    and to role='mentor', so this can never become a way to take over the
    account that could remove you."""
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
        temporary = authlib.generate_temporary_password()
        authlib.set_password(conn, mentor["id"], temporary)
        authlib.destroy_other_sessions(conn, mentor["id"])
        db.log_action(conn, user["id"], "password_reset_by_admin", "user", mentor["id"],
                      f"Temporary password issued for {mentor['name']}")
        conn.commit()
    finally:
        conn.close()
    return render_done(
        user,
        "Temporary password issued",
        f"{mentor['name']}'s password is now {temporary}. Write it down before you leave this "
        f"page, it is not shown again and nobody, including you, can look it up later. Give it to "
        f"them directly and ask them to set their own from Change password once they are in. Any "
        f"device they were signed in on has been signed out.",
        "/admin",
        back_label="Back to admin home",
    )
