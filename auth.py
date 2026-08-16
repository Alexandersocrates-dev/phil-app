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
SESSION_LIFETIME_DAYS = 14
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
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, db.now(), expires),
    )
    return token


def destroy_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_token(conn, token):
    if not token:
        return None
    row = conn.execute(
        """SELECT users.* FROM sessions
           JOIN users ON users.id = sessions.user_id
           WHERE sessions.token = ? AND sessions.expires_at > ? AND users.status = 'active'""",
        (token, db.now()),
    ).fetchone()
    return row


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
