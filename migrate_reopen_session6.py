#!/usr/bin/env python3
"""
Reopens enrolments that were completed before session 6 existed.

Courses used to finish at session 5. They now finish at session 6, the staff-only
support plan. Any enrolment marked completed at session 5 was finished under the
old rule, so it shows "Session 5 of 6 — Completed" with no way to record the
last session. This puts those back to active so the mentor can finish them.

    python3 migrate_reopen_session6.py            # show what would change
    python3 migrate_reopen_session6.py --confirm  # apply

Certificates already issued are left alone: the pupil earned theirs by finishing
the five sessions with a mentor, and taking it back would be wrong.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

PUPIL_SESSIONS = 5


def main():
    dry = "--confirm" not in sys.argv
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT e.id, e.current_week, e.status, p.forename, p.surname,
                  c.title AS course_title,
                  (SELECT COUNT(*) FROM certificates WHERE enrolment_id = e.id) AS has_cert
           FROM enrolments e
           JOIN pupils p ON p.id = e.pupil_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.status = 'completed' AND e.current_week <= ?
           ORDER BY e.id""",
        (PUPIL_SESSIONS,)).fetchall()

    print(("DRY RUN — nothing written\n" if dry else "")
          + f"{len(rows)} enrolment(s) completed under the old five-session rule\n")
    for r in rows:
        cert = "certificate already issued" if r["has_cert"] else "no certificate yet"
        print(f"  #{r['id']}  {r['forename']} {r['surname']} \u2014 {r['course_title']}")
        print(f"      session {r['current_week']} of 6, {cert}")
        print(f"      -> reopened so session 6 can be recorded")

    if dry:
        print("\nRe-run with --confirm to apply.")
    elif rows:
        try:
            conn.execute(
                "UPDATE enrolments SET status='active' WHERE status='completed' AND current_week <= ?",
                (PUPIL_SESSIONS,))
            conn.commit()
            print(f"\nReopened {len(rows)} enrolment(s).")
        except Exception:
            conn.rollback()
            print("\nFailed — nothing was changed.")
            raise
    conn.close()


if __name__ == "__main__":
    main()
