#!/usr/bin/env python3
"""
Checks that a database file is complete and usable.

Phil's retention policy says backups run daily and weekly. Until one has been
restored and inspected, that is a hope rather than a fact, and it is the kind of
claim a school's data protection officer will ask you to stand behind.

This is the inspection half. Railway does the restoring: you restore a backup
into a scratch environment, or download it, then point this at the resulting
file. It never touches the live database and never writes anything.

    python3 verify_backup.py /path/to/restored/phil.db

It answers three questions:
  1. Is the file a valid SQLite database that opens without error?
  2. Does it pass SQLite's own integrity check?
  3. Is the data actually there, or is it an empty database that happens to
     have the right shape? An empty backup restores perfectly and is worthless.
"""
import os
import sqlite3
import sys

# Tables that should never be empty in a real backup. An empty database passes
# every structural check ever devised, so counting rows is the only test that
# distinguishes a good backup from a well-formed nothing.
EXPECT_ROWS = ["courses", "weeks", "establishments", "users"]

# Everything a full backup should contain, so a missing table is noticed.
EXPECT_TABLES = [
    "establishments", "subscriptions", "invoices", "users", "sessions",
    "pupils", "pupil_parent_links", "parent_access_requests", "courses",
    "weeks", "enrolments", "session_schedule", "session_records",
    "session_drafts", "certificates", "resource_entries",
    "completion_reflections", "notifications", "course_requests",
    "support_requests", "audit_log",
]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]

    if not os.path.exists(path):
        print(f"No file at {path}")
        return 1
    size = os.path.getsize(path)
    print(f"File: {path}")
    print(f"Size: {size:,} bytes\n")
    if size == 0:
        print("FAIL: the file is empty.")
        return 1

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"FAIL: could not open as a database: {e}")
        return 1

    failures = []

    # 1. SQLite's own check. Catches truncation and corruption, which is the
    #    most likely way a backup goes wrong quietly.
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        ok = result == "ok"
        print(f"Integrity check: {'passed' if ok else 'FAILED - ' + result}")
        if not ok:
            failures.append("integrity check")
    except sqlite3.DatabaseError as e:
        # Truncated or not a database at all. Nothing else is worth trying.
        print(f"Integrity check: FAILED - {e}")
        print("\n" + "=" * 60)
        print("NOT USABLE: the file is corrupt or is not a database.")
        print("This is what a half-finished download or a truncated backup")
        print("looks like. Try the download again before assuming the backup")
        print("itself is bad.")
        print("=" * 60)
        conn.close()
        return 1

    # 2. Are the tables all present?
    try:
        present = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        print(f"Tables: unreadable - {e}")
        conn.close()
        return 1
    missing = [t for t in EXPECT_TABLES if t not in present]
    print(f"Tables: {len(present)} found, {len(missing)} missing")
    if missing:
        print(f"   missing: {', '.join(missing)}")
        failures.append("missing tables")

    # 3. Is there anything in it?
    print("\nRow counts:")
    counts = {}
    for table in sorted(present):
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[table] = None
    width = max(len(t) for t in counts) if counts else 10
    for table, n in counts.items():
        flag = ""
        if table in EXPECT_ROWS and not n:
            flag = "   <-- expected data here"
            failures.append(f"{table} is empty")
        print(f"   {table:<{width}}  {n if n is not None else 'unreadable':>7}{flag}")

    # 4. A real read, not just a count. If the file is subtly damaged this is
    #    where it shows: joining across tables exercises indexes and pages a
    #    count never touches.
    print("\nSample read across tables:")
    try:
        rows = conn.execute(
            """SELECT p.forename, p.surname, c.title, e.status,
                      (SELECT COUNT(*) FROM session_records WHERE enrolment_id = e.id) AS sessions
               FROM enrolments e
               JOIN pupils p ON p.id = e.pupil_id
               JOIN courses c ON c.id = e.course_id
               ORDER BY e.id LIMIT 5""").fetchall()
        if rows:
            for r in rows:
                print(f"   {r['forename']} {r['surname']} - {r['title']} "
                      f"({r['status']}, {r['sessions']} session(s) recorded)")
        else:
            print("   no enrolments in this backup (fine if it predates any)")
    except sqlite3.Error as e:
        print(f"   FAILED: {e}")
        failures.append("cross-table read")

    conn.close()

    print("\n" + "=" * 60)
    if failures:
        print(f"NOT USABLE: {len(failures)} problem(s) - {', '.join(failures)}")
        print("Do not rely on this backup. Check the next one and, if that also")
        print("fails, treat it as an incident: you currently have no recovery.")
    else:
        print("USABLE: opens cleanly, passes integrity, and contains real data.")
        print("Record the date you ran this. A restore test is only worth")
        print("anything if it is recent.")
    print("=" * 60)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
