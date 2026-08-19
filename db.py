"""
Phil - database layer.

SQLite for local development. The schema below mirrors the data model in
Phil_Technical_Build_Spec.docx section 4 as closely as SQLite allows. For a
production deployment, this file is the thing that gets swapped for a
Postgres connection (e.g. via Supabase) per the spec's recommended stack;
the table shapes below were designed to translate directly.
"""

import sqlite3
import os
import datetime

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "phil.db")
# On Railway (or any host with a mounted persistent volume), set PHIL_DB_PATH
# to a path inside that volume, e.g. /data/phil.db, so the database survives
# redeploys. Falls back to the local default for development.
DB_PATH = os.environ.get("PHIL_DB_PATH", DEFAULT_DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS establishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('school','individual')),
    name TEXT NOT NULL,
    address TEXT,
    dfe_urn TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    plan_type TEXT NOT NULL CHECK(plan_type IN ('pilot','school','individual')),
    included_seats INTEGER NOT NULL,
    pupil_cap INTEGER,
    extra_seats INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','expired','cancelled')),
    payment_method TEXT CHECK(payment_method IN ('card','invoice','none')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    renewal_date TEXT,
    pilot_ends_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
    amount REAL NOT NULL,
    purchase_order_ref TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','sent','paid','overdue')),
    due_date TEXT,
    stripe_invoice_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seat_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    requested_by INTEGER NOT NULL,
    requested_extra_seats INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','contacted','resolved')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER REFERENCES establishments(id),
    role TEXT NOT NULL CHECK(role IN ('admin','mentor','parent_carer','phil_staff')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pupils (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    forename TEXT NOT NULL,
    surname TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    year_group TEXT NOT NULL,
    form_class TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pupil_parent_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pupil_id INTEGER NOT NULL REFERENCES pupils(id),
    parent_user_id INTEGER NOT NULL REFERENCES users(id),
    relationship TEXT,
    verified_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parent_access_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pupil_id INTEGER NOT NULL REFERENCES pupils(id),
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    requested_by INTEGER NOT NULL REFERENCES users(id),
    parent_name TEXT NOT NULL,
    parent_email TEXT NOT NULL,
    relationship TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','declined')),
    resolved_by INTEGER REFERENCES users(id),
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    focus_area TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('draft','published')),
    created_by INTEGER,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS weeks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    week_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    objective TEXT,
    checkin TEXT,
    input_content TEXT,
    activity TEXT,
    reflect TEXT,
    lookfor TEXT,
    resources TEXT,
    home_activity TEXT,
    -- Session 6 is the mentor writing up the support plan, with no pupil in the
    -- room. Flagged rather than inferred from the week number, so a course could
    -- have a different shape later without the meaning being lost.
    staff_only INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS enrolments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pupil_id INTEGER NOT NULL REFERENCES pupils(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    mentor_id INTEGER NOT NULL REFERENCES users(id),
    start_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','withdrawn')),
    current_week INTEGER NOT NULL DEFAULT 0,
    parent_access_enabled INTEGER NOT NULL DEFAULT 1,
    -- A review point agreed at the end of a course, so support doesn't stop
    -- dead at session five. Nullable: not every course gets one.
    review_date TEXT,
    review_note TEXT,
    review_done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL REFERENCES enrolments(id),
    week_number INTEGER NOT NULL,
    planned_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL REFERENCES enrolments(id),
    week_id INTEGER NOT NULL REFERENCES weeks(id),
    date TEXT NOT NULL,
    mood_rating INTEGER,
    engagement_rating INTEGER,
    safeguarding_flag INTEGER NOT NULL,
    safeguarding_note TEXT NOT NULL,
    what_happened TEXT,
    reflection_goal TEXT,
    mentor_notes TEXT,
    resources_used TEXT,
    recorded_by INTEGER NOT NULL REFERENCES users(id),
    pdf_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_drafts (
id INTEGER PRIMARY KEY AUTOINCREMENT,
enrolment_id INTEGER NOT NULL REFERENCES enrolments(id),
week_number INTEGER NOT NULL,
checkin_note TEXT,
input_note TEXT,
activity_note TEXT,
reflect_note TEXT,
next_session_note TEXT,
updated_at TEXT NOT NULL,
UNIQUE(enrolment_id, week_number)
);

CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL UNIQUE REFERENCES enrolments(id),
    issued_date TEXT NOT NULL,
    pdf_path TEXT
);

-- What a pupil actually wrote on a resource: the blank cells of a table, the
-- fields of a plan, the ticks on a checklist. Keyed by enrolment and week so it
-- follows the pupil through the course, and by field_key so a resource can
-- change shape without orphaning what was written.
CREATE TABLE IF NOT EXISTS resource_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL REFERENCES enrolments(id),
    week_id INTEGER NOT NULL REFERENCES weeks(id),
    resource_slug TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value TEXT,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(enrolment_id, week_id, resource_slug, field_key)
);
CREATE INDEX IF NOT EXISTS idx_resource_entries_enrolment
    ON resource_entries(enrolment_id, week_id);

CREATE TABLE IF NOT EXISTS completion_reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrolment_id INTEGER NOT NULL UNIQUE REFERENCES enrolments(id),
    pupil_engagement TEXT,
    course_effectiveness TEXT,
    recommended_next_steps TEXT,
    completed_by INTEGER REFERENCES users(id),
    completed_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    recipient TEXT NOT NULL,
    establishment_id INTEGER REFERENCES establishments(id),
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'unread' CHECK(status IN ('unread','read')),
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS course_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id),
    requested_by INTEGER NOT NULL REFERENCES users(id),
    topic TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','linked')),
    linked_course_id INTEGER REFERENCES courses(id),
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS support_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER REFERENCES establishments(id),
    requester_user_id INTEGER NOT NULL REFERENCES users(id),
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    pupil_id INTEGER REFERENCES pupils(id),
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
    response TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stripe_events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
"""


def log_action(conn, actor_user_id, action, target_type=None, target_id=None, detail=None):
    conn.execute(
        """INSERT INTO audit_log (actor_user_id, action, target_type, target_id, detail, created_at)
           VALUES (?,?,?,?,?,?)""",
        (actor_user_id, action, target_type, target_id, detail, now()),
    )


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now():
    return datetime.datetime.utcnow().isoformat()


if __name__ == "__main__":
    init_db()
    print("Database initialised at", DB_PATH)
