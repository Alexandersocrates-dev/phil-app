"""Add the table that records which pupils a mentor has taken off their list.

Before this, a pupil dropped off a mentor's list the moment their last course
finished. Nobody decided that, and a pupil the mentor was still keeping an eye
on simply disappeared. They now stay until the mentor removes them.

Safe to run more than once.
"""
import db


SQL = """
CREATE TABLE IF NOT EXISTS mentoring_list_removals (
    mentor_id INTEGER NOT NULL REFERENCES users(id),
    pupil_id INTEGER NOT NULL REFERENCES pupils(id),
    removed_at TEXT NOT NULL,
    PRIMARY KEY (mentor_id, pupil_id)
);
"""


def main():
    conn = db.get_conn()
    try:
        existed = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("mentoring_list_removals",)).fetchone()
        conn.executescript(SQL)
        conn.commit()
        count = conn.execute("SELECT count(*) c FROM mentoring_list_removals").fetchone()["c"]
        if existed:
            print(f"Table already present, {count} removal(s) on record. Nothing to do.")
        else:
            print("Created mentoring_list_removals.")
            print("Every pupil with a finished course now stays on their mentor's list "
                  "until the mentor removes them.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
