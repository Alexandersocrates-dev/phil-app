#!/usr/bin/env python3
"""
Forces every certificate to be redrawn in the current design.

A certificate PDF is written once and then served from disk, so any certificate
issued before a design change keeps the old look for ever. This clears the
stored path — the certificate route rebuilds from the database on next download,
so nothing is lost and no certificate is revoked.

    python3 rebuild_certificates.py            # show what would change
    python3 rebuild_certificates.py --confirm  # apply

Run this after any change to certificate_pdf() in pdf/generate.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def main():
    dry = "--confirm" not in sys.argv
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT c.id, c.enrolment_id, c.pdf_path, c.issued_date,
                  p.forename, p.surname, co.title AS course_title
           FROM certificates c
           JOIN enrolments e ON e.id = c.enrolment_id
           JOIN pupils p ON p.id = e.pupil_id
           JOIN courses co ON co.id = e.course_id
           ORDER BY c.id""").fetchall()

    print(("DRY RUN — nothing written\n" if dry else "")
          + f"{len(rows)} certificate(s) on file\n")
    for r in rows:
        on_disk = bool(r["pdf_path"]) and os.path.exists(r["pdf_path"])
        print(f"  #{r['id']}  {r['forename']} {r['surname']} \u2014 {r['course_title']}"
              f"  (issued {r['issued_date']})")
        print(f"      file {'present' if on_disk else 'already missing'}"
              f" -> will be redrawn on next download")

    if dry:
        print("\nRe-run with --confirm to apply.")
    elif rows:
        try:
            # Only the stored path is cleared. The certificate record, its issue
            # date and its reference all stay exactly as they were.
            for r in rows:
                if r["pdf_path"] and os.path.exists(r["pdf_path"]):
                    try:
                        os.remove(r["pdf_path"])
                    except OSError:
                        pass
            conn.execute("UPDATE certificates SET pdf_path=''")
            conn.commit()
            print(f"\nCleared {len(rows)} stored file(s). "
                  "Each rebuilds in the current design when next downloaded.")
        except Exception:
            conn.rollback()
            print("\nFailed — nothing was changed.")
            raise
    conn.close()


if __name__ == "__main__":
    main()
