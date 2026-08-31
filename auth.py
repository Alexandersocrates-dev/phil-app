"""
Phil - authentication.

Password hashing via PBKDF2-HMAC-SHA256 (stdlib hashlib, no bcrypt dependency
needed). Sessions are opaque random tokens (stdlib secrets) stored server-side
in the sessions table and set as an HttpOnly cookie. This is deliberately
simple: for production, swap this module for Supabase Auth or Clerk per the
Technical Build Spec (section 2.1) without touching the rest of the app, since
every route only ever calls current_user(request).
"""

import hashlib
import secrets
import datetime
import db

SESSION_COOKIE = "phil_session"
# Two limits, not one. The absolute cap is how long a session can live at all;
# the idle limit is how long it survives untouched.
#
# A fortnight-long session with no idle limit meant a staffroom machine left
# signed in was an open door for two weeks, which is the likelier risk in a
# school than a stolen password — and the thing two-factor does nothing about.
# Eight hours kills that overnight while a mentor working a normal week never
# meets it; a week of use between codes keeps the friction low enough that
# nobody is tempted to work around it.
SESSION_LIFETIME_DAYS = 7
SESSION_IDLE_HOURS = 8
PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    check, _ = hash_password(password, salt)
    return secrets.compare_digest(check, stored_hash)


def create_user(conn, establishment_id, role, name, email, password):
    password_hash, salt = hash_password(password)
    cur = conn.execute(
        """INSERT INTO users (establishment_id, role, name, email, password_hash,
           password_salt, status, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (establishment_id, role, name, email.lower().strip(), password_hash, salt,
         "active", db.now()),
    )
    return cur.lastrowid


def authenticate(conn, email, password):
    row = conn.execute(
        "SELECT * FROM users WHERE email = ? AND status = 'active'", (email.lower().strip(),)
    ).fetchone()
    if not row:
        return None
    if not verify_password(password, row["password_hash"], row["password_salt"]):
        return None
    return row


def create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow() + datetime.timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    init_session_activity(conn)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at, last_seen_at) VALUES (?,?,?,?,?)",
        (token, user_id, db.now(), expires, db.now()),
    )
    return token


def destroy_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def init_session_activity(conn):
    """Adds last_seen_at to an existing sessions table.

    On demand rather than as a migration, matching how the reset and two-factor
    tables are created. ALTER TABLE ADD COLUMN is the one schema change SQLite
    does cheaply, and it runs once."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "last_seen_at" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN last_seen_at TEXT")
        conn.execute("UPDATE sessions SET last_seen_at = created_at WHERE last_seen_at IS NULL")


def user_from_token(conn, token):
    """The signed-in user, if the session is neither expired nor gone stale.

    Touches last_seen_at as it goes, so the idle clock resets on every page.
    The write is skipped unless a minute has passed, so a page with several
    requests behind it doesn't write several times.
    """
    if not token:
        return None
    init_session_activity(conn)
    idle_cutoff = (datetime.datetime.utcnow()
                   - datetime.timedelta(hours=SESSION_IDLE_HOURS)).isoformat()
    row = conn.execute(
        """SELECT users.*, sessions.last_seen_at AS _seen FROM sessions
           JOIN users ON users.id = sessions.user_id
           WHERE sessions.token = ? AND sessions.expires_at > ?
             AND COALESCE(sessions.last_seen_at, sessions.created_at) > ?
             AND users.status = 'active'""",
        (token, db.now(), idle_cutoff),
    ).fetchone()
    if not row:
        return None
    seen = row["_seen"]
    if not seen or seen < (datetime.datetime.utcnow()
                           - datetime.timedelta(minutes=1)).isoformat():
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?", (db.now(), token))
        conn.commit()
    return row


def purge_expired_sessions(conn):
    """Rows for sessions that have expired or gone stale. Nothing depends on
    them being gone — the query above already ignores them — but a table that
    only ever grows is a table that eventually matters."""
    init_session_activity(conn)
    idle_cutoff = (datetime.datetime.utcnow()
                   - datetime.timedelta(hours=SESSION_IDLE_HOURS)).isoformat()
    conn.execute(
        """DELETE FROM sessions WHERE expires_at <= ?
           OR COALESCE(last_seen_at, created_at) <= ?""",
        (db.now(), idle_cutoff))


def set_password(conn, user_id, new_password):
    """Rehashes and stores a new password for one user, with a new salt."""
    password_hash, salt = hash_password(new_password)
    conn.execute(
        "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
        (password_hash, salt, user_id),
    )


def destroy_other_sessions(conn, user_id, keep_token=None):
    """Signs a user out everywhere except the session they are using now.

    Changing the stored hash does not touch rows already in the sessions table,
    so without this anyone already signed in as that user stays signed in for
    the full SESSION_LIFETIME_DAYS."""
    if keep_token:
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token != ?", (user_id, keep_token)
        )
    else:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


RESET_TOKEN_LIFETIME_MINUTES = 60


def generate_temporary_password():
    """A short random password for an admin to read out or write down.

    Deliberately not memorable or patterned: it is meant to be used once and
    replaced by the person it belongs to."""
    return secrets.token_urlsafe(9)


def init_reset_table(conn):
    """Created on demand rather than in db.init_db() so an existing deployment
    picks it up on the next request with no migration step."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS password_resets (
               token TEXT PRIMARY KEY,
               user_id INTEGER NOT NULL,
               created_at TEXT NOT NULL,
               expires_at TEXT NOT NULL,
               used_at TEXT
           )"""
    )


def create_reset_token(conn, user_id):
    """Issues a single-use, time-limited token and kills any earlier unused one
    for the same user, so requesting a second link makes the first dead rather
    than leaving several live at once."""
    init_reset_table(conn)
    conn.execute(
        "UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
        (db.now(), user_id),
    )
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(minutes=RESET_TOKEN_LIFETIME_MINUTES)).isoformat()
    conn.execute(
        "INSERT INTO password_resets (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, db.now(), expires),
    )
    return token


def user_for_reset_token(conn, token):
    """The user row for a token that exists, is unused and is unexpired. None
    otherwise, without revealing which of those it was."""
    if not token:
        return None
    init_reset_table(conn)
    return conn.execute(
        """SELECT users.* FROM password_resets
           JOIN users ON users.id = password_resets.user_id
           WHERE password_resets.token = ?
             AND password_resets.used_at IS NULL
             AND password_resets.expires_at > ?
             AND users.status = 'active'""",
        (token, db.now()),
    ).fetchone()


def consume_reset_token(conn, token):
    conn.execute("UPDATE password_resets SET used_at = ? WHERE token = ?", (db.now(), token))


# ------------------------------------------------------------ two-factor --
# Time-based one-time passwords (RFC 6238), the same thing Google
# Authenticator, Authy and 1Password generate. Built on hashlib and hmac
# rather than a library, for the same reason the password hashing above is:
# no dependency to keep current, and nothing to break on a redeploy.
#
# An emailed code was the alternative and was rejected: it is only ever as
# strong as the mailbox, and a school inbox is often shared or forwarded. This
# app holds safeguarding notes.

import base64
import hmac
import struct
import time

TOTP_PERIOD = 30          # seconds per code, the universal default
TOTP_DIGITS = 6
TOTP_WINDOW = 1           # how many periods either side to accept
RECOVERY_CODE_COUNT = 8


def init_twofa_tables(conn):
    """Created on demand, as the reset table is, so an existing deployment
    picks this up on the next request with no migration step."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_twofa (
               user_id INTEGER PRIMARY KEY,
               secret TEXT NOT NULL,
               confirmed_at TEXT,
               created_at TEXT NOT NULL
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS twofa_recovery_codes (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               code_hash TEXT NOT NULL,
               used_at TEXT
           )"""
    )
    # Where a password has been accepted but the second factor has not. Held
    # server-side and short-lived: a cookie carrying "this user is half way in"
    # is a cookie worth forging.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS twofa_pending (
               token TEXT PRIMARY KEY,
               user_id INTEGER NOT NULL,
               created_at TEXT NOT NULL,
               expires_at TEXT NOT NULL
           )"""
    )


def new_totp_secret():
    """A base32 secret, which is what authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_at(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret, code, at=None):
    """True if the code is valid now, or one period either side.

    The window covers a clock that is slightly out and a code typed as it
    rolls over. Compared with compare_digest so a wrong code takes the same
    time as a right one.
    """
    code = (code or "").strip().replace(" ", "")
    if not (secret and code.isdigit() and len(code) == TOTP_DIGITS):
        return False
    counter = int((at if at is not None else time.time()) // TOTP_PERIOD)
    for drift in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        if secrets.compare_digest(_totp_at(secret, counter + drift), code):
            return True
    return False


def otpauth_uri(secret, email, issuer="Phil"):
    """What a QR code would encode, so an app can be set up by scanning it or
    by typing the secret in by hand."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{email}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}")


def _hash_recovery_code(code):
    """Recovery codes are high-entropy random strings, not chosen by a person,
    so a plain SHA-256 is enough — there is no dictionary to run against them,
    and eight PBKDF2 checks per sign-in would be felt."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def issue_recovery_codes(conn, user_id):
    """A fresh set, replacing any that already exist. Returned in the clear
    once and never again: only the hashes are kept."""
    init_twofa_tables(conn)
    conn.execute("DELETE FROM twofa_recovery_codes WHERE user_id = ?", (user_id,))
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(5)                       # 10 hex characters
        code = f"{raw[:5]}-{raw[5:]}"
        codes.append(code)
        conn.execute(
            "INSERT INTO twofa_recovery_codes (user_id, code_hash) VALUES (?,?)",
            (user_id, _hash_recovery_code(code)),
        )
    return codes


def consume_recovery_code(conn, user_id, code):
    """Spends one code if it matches an unused one. Single use: a code that
    has been typed once is dead, whether or not the sign-in completed."""
    init_twofa_tables(conn)
    code = (code or "").strip().lower().replace(" ", "")
    if not code:
        return False
    row = conn.execute(
        """SELECT id FROM twofa_recovery_codes
           WHERE user_id = ? AND code_hash = ? AND used_at IS NULL""",
        (user_id, _hash_recovery_code(code)),
    ).fetchone()
    if not row:
        return False
    conn.execute("UPDATE twofa_recovery_codes SET used_at = ? WHERE id = ?",
                 (db.now(), row["id"]))
    return True


def twofa_record(conn, user_id):
    init_twofa_tables(conn)
    return conn.execute("SELECT * FROM user_twofa WHERE user_id = ?", (user_id,)).fetchone()


def twofa_enabled(conn, user_id):
    """Enabled means set up AND confirmed with a working code. A half-finished
    setup must not lock anyone out."""
    row = twofa_record(conn, user_id)
    return bool(row and row["confirmed_at"])


def begin_twofa_setup(conn, user_id):
    """A new unconfirmed secret, replacing any earlier unconfirmed one."""
    init_twofa_tables(conn)
    secret = new_totp_secret()
    conn.execute("DELETE FROM user_twofa WHERE user_id = ? AND confirmed_at IS NULL", (user_id,))
    conn.execute(
        "INSERT OR REPLACE INTO user_twofa (user_id, secret, confirmed_at, created_at) VALUES (?,?,NULL,?)",
        (user_id, secret, db.now()),
    )
    return secret


def confirm_twofa(conn, user_id, code):
    """Turns it on, but only against a code the user has actually generated."""
    row = twofa_record(conn, user_id)
    if not row or not verify_totp(row["secret"], code):
        return False
    conn.execute("UPDATE user_twofa SET confirmed_at = ? WHERE user_id = ?", (db.now(), user_id))
    return True


def disable_twofa(conn, user_id):
    init_twofa_tables(conn)
    conn.execute("DELETE FROM user_twofa WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM twofa_recovery_codes WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM twofa_pending WHERE user_id = ?", (user_id,))


def unused_recovery_code_count(conn, user_id):
    init_twofa_tables(conn)
    return conn.execute(
        "SELECT count(*) FROM twofa_recovery_codes WHERE user_id = ? AND used_at IS NULL",
        (user_id,),
    ).fetchone()[0]


PENDING_LIFETIME_MINUTES = 10


def create_pending(conn, user_id):
    """The password was right; the second factor has not been given yet."""
    init_twofa_tables(conn)
    conn.execute("DELETE FROM twofa_pending WHERE user_id = ? OR expires_at < ?",
                 (user_id, db.now()))
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(minutes=PENDING_LIFETIME_MINUTES)).isoformat()
    conn.execute(
        "INSERT INTO twofa_pending (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, db.now(), expires),
    )
    return token


def user_for_pending(conn, token):
    if not token:
        return None
    init_twofa_tables(conn)
    return conn.execute(
        """SELECT users.* FROM twofa_pending
           JOIN users ON users.id = twofa_pending.user_id
           WHERE twofa_pending.token = ? AND twofa_pending.expires_at > ?
             AND users.status = 'active'""",
        (token, db.now()),
    ).fetchone()


def consume_pending(conn, token):
    conn.execute("DELETE FROM twofa_pending WHERE token = ?", (token,))
