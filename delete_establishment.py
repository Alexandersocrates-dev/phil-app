#!/usr/bin/env python3
"""
Deletes every record belonging to one establishment.

Phil's retention policy promises a school that its data is deleted 90 days after
its subscription ends. Doing that by hand across fifteen tables — some three
levels deep — is how something gets left behind, and "we run a script" is a
better answer to a data protection officer than "we delete it by hand".

    python3 delete_establishment.py --list
    python3 delete_establishment.py --id 3
    python3 delete_establishment.py --id 3 --confirm

The dry run is the default and prints exactly what would go. Nothing is deleted
without --confirm and typing the establishment's name when asked.

WHAT IS KEPT, deliberately:
  - invoices, because HMRC requires six years of billing records. They hold the
    billing contact, not pupil data.
  - the audit log entry recording this deletion.
Everything else belonging to the establishment is removed, including the
establishment row itself.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def counts(conn, eid):
    """What exists for this establishment, table by table.

    Written as explicit queries rather than a clever traversal: a reader needs
    to be able to check this against the schema by eye."""
    q = lambda sql: conn.execute(sql, (eid,)).fetchone()[0]  # noqa: E731
    ENROL = """SELECT COUNT(*) FROM %s WHERE enrolment_id IN
               (SELECT e.id FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
                WHERE p.establishment_id = ?)"""
    return [
        ("session records", q(ENROL % "session_records")),
        ("resource entries (pupils' own work)", q(ENROL % "resource_entries")),
        ("completion reflections", q(ENROL % "completion_reflections")),
        ("certificates", q(ENROL % "certificates")),
        ("scheduled sessions", q(ENROL % "session_schedule")),
        ("session drafts", q(ENROL % "session_drafts")),
        ("enrolments", q("""SELECT COUNT(*) FROM enrolments e
                            JOIN pupils p ON p.id = e.pupil_id
                            WHERE p.establishment_id = ?""")),
        ("parent links", q("""SELECT COUNT(*) FROM pupil_parent_links l
                              JOIN pupils p ON p.id = l.pupil_id
                              WHERE p.establishment_id = ?""")),
        ("parent access requests", q("SELECT COUNT(*) FROM parent_access_requests WHERE establishment_id = ?")),
        ("pupils", q("SELECT COUNT(*) FROM pupils WHERE establishment_id = ?")),
        ("support requests", q("SELECT COUNT(*) FROM support_requests WHERE establishment_id = ?")),
        ("course requests", q("SELECT COUNT(*) FROM course_requests WHERE establishment_id = ?")),
        ("notifications", q("SELECT COUNT(*) FROM notifications WHERE establishment_id = ?")),
        ("seat alerts", q("SELECT COUNT(*) FROM seat_alerts WHERE establishment_id = ?")),
        ("sign-in sessions", q("""SELECT COUNT(*) FROM sessions s JOIN users u ON u.id = s.user_id
                                  WHERE u.establishment_id = ?""")),
        ("staff accounts", q("SELECT COUNT(*) FROM users WHERE establishment_id = ?")),
        ("subscriptions", q("SELECT COUNT(*) FROM subscriptions WHERE establishment_id = ?")),
    ]


def pdf_paths(conn, eid):
    """Generated PDFs on the volume, which the database rows point at."""
    rows = conn.execute(
        """SELECT c.pdf_path FROM certificates c
           JOIN enrolments e ON e.id = c.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND c.pdf_path != ''""", (eid,)).fetchall()
    rows += conn.execute(
        """SELECT r.pdf_path FROM session_records r
           JOIN enrolments e ON e.id = r.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           WHERE p.establishment_id = ? AND r.pdf_path IS NOT NULL
             AND r.pdf_path != ''""", (eid,)).fetchall()
    return [r[0] for r in rows]


def delete(conn, eid):
    """Deletes in dependency order: children before parents."""
    ENROL_IDS = """SELECT e.id FROM enrolments e JOIN pupils p ON p.id = e.pupil_id
                   WHERE p.establishment_id = ?"""
    for table in ("session_records", "resource_entries", "completion_reflections",
                  "certificates", "session_schedule", "session_drafts"):
        conn.execute(f"DELETE FROM {table} WHERE enrolment_id IN ({ENROL_IDS})", (eid,))
    conn.execute(f"DELETE FROM enrolments WHERE id IN ({ENROL_IDS})", (eid,))
    conn.execute("""DELETE FROM pupil_parent_links WHERE pupil_id IN
                    (SELECT id FROM pupils WHERE establishment_id = ?)""", (eid,))
    conn.execute("DELETE FROM parent_access_requests WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM pupils WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM support_requests WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM course_requests WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM notifications WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM seat_alerts WHERE establishment_id = ?", (eid,))
    conn.execute("""DELETE FROM sessions WHERE user_id IN
                    (SELECT id FROM users WHERE establishment_id = ?)""", (eid,))
    conn.execute("DELETE FROM users WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM subscriptions WHERE establishment_id = ?", (eid,))
    conn.execute("DELETE FROM establishments WHERE id = ?", (eid,))


def main():
    args = sys.argv[1:]
    conn = db.get_conn()

    if "--list" in args or not args:
        rows = conn.execute(
            """SELECT e.id, e.name, e.status,
                      (SELECT COUNT(*) FROM pupils WHERE establishment_id = e.id) AS pupils,
                      (SELECT status FROM subscriptions WHERE establishment_id = e.id
                        ORDER BY id DESC LIMIT 1) AS sub
               FROM establishments e ORDER BY e.id""").fetchall()
        print("Establishments on file:\n")
        for r in rows:
            print(f"  id {r['id']:<4} {r['name']:<34} {r['status']:<10} "
                  f"{r['pupils']} pupil(s), subscription {r['sub'] or 'none'}")
        print("\nTo see what deleting one would remove:")
        print("  python3 delete_establishment.py --id <id>")
        conn.close()
        return 0

    if "--id" not in args:
        print("Which establishment? Use --list to see them, then --id <id>.")
        conn.close()
        return 1
    eid = int(args[args.index("--id") + 1])

    estab = conn.execute("SELECT * FROM establishments WHERE id = ?", (eid,)).fetchone()
    if not estab:
        print(f"No establishment with id {eid}.")
        conn.close()
        return 1

    rows = counts(conn, eid)
    pdfs = pdf_paths(conn, eid)
    total = sum(n for _, n in rows)
    dry = "--confirm" not in args

    print(("DRY RUN — nothing will be deleted\n" if dry else "")
          + f"Establishment: {estab['name']} (id {eid}, {estab['status']})\n")
    for label, n in rows:
        print(f"  {n:>6}  {label}")
    print(f"  {len(pdfs):>6}  generated PDF files on the volume")
    print(f"\n  {total} database record(s) in total, plus the establishment itself.")
    print("\n  Kept: invoices (HMRC requires six years) and the audit log.")

    if dry:
        print("\nTo delete, re-run with --confirm. You will be asked to type the name.")
        conn.close()
        return 0

    print(f"\nThis cannot be undone. Type the establishment's name to confirm:")
    try:
        typed = input("  > ").strip()
    except EOFError:
        typed = ""
    if typed != estab["name"]:
        print("Name did not match. Nothing was deleted.")
        conn.close()
        return 1

    try:
        # The audit entry is written before the users table goes, so the actor
        # reference is still valid, and it survives the deletion as the record
        # that it happened.
        db.log_action(conn, None, "establishment_deleted", "establishment", eid,
                      f"{estab['name']}: {total} records")
        delete(conn, eid)
        conn.commit()
    except Exception:
        conn.rollback()
        print("\nFailed — nothing was deleted.")
        raise
    finally:
        conn.close()

    removed = 0
    for p in pdfs:
        try:
            if p and os.path.exists(p):
                os.remove(p)
                removed += 1
        except OSError:
            pass

    print(f"\nDeleted {total} record(s) and {removed} PDF file(s).")
    print("Confirm to the school in writing that deletion is complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
