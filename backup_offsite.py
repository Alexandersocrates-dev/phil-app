"""Copy the database somewhere Railway isn't.

Railway's own volume backups are good, and they cover the ordinary disasters:
a bad deploy, a row deleted by mistake, needing last Tuesday back. What they
do not cover is stated plainly in Railway's docs — "wiping a volume deletes
all of its backups". The snapshots live beside the thing they photograph. This
puts one copy outside that blast radius.

Only the database. The PDFs are large and regenerable from the records; the
records are not regenerable from anything.

Uses urllib and hashlib from the standard library, in keeping with the rest of
Phil. Backblaze B2's native API is used rather than the S3 one because it
authenticates with a token instead of AWS request signing — a hundred lines of
signing code is a hundred lines that can be subtly wrong, and this runs
unattended.

Set these on the service that runs it:

    B2_KEY_ID           application key id
    B2_APPLICATION_KEY  application key
    B2_BUCKET_ID        the bucket to write to
    PHIL_DB_PATH        /data/phil.db, as the app already has

Run it from the repo root:

    python3 backup_offsite.py            # take a backup
    python3 backup_offsite.py --check    # verify the settings, upload nothing
"""

import base64
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DB_PATH = os.environ.get("PHIL_DB_PATH", "/data/phil.db")
API_URL = "https://api.backblazeb2.com/b2api/v3/b2_authorize_account"


def snapshot(db_path, out_path):
    """A consistent copy of a live database.

    Not a file copy. With write-ahead logging on, recent commits live in a
    separate -wal file, so copying phil.db alone yields a database that opens
    but has none of the data in it — verified, and it fails silently, which is
    the worst way for a backup to be wrong. VACUUM INTO asks SQLite itself for
    a complete copy, safe to run while the app is serving.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (out_path,))
    finally:
        conn.close()
    # Prove the copy opens and has the tables in it before it is sent anywhere.
    check = sqlite3.connect(out_path)
    try:
        tables = [r[0] for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        if "users" not in tables or "session_records" not in tables:
            raise RuntimeError("snapshot is missing core tables: %s" % tables)
        rows = check.execute("SELECT count(*) FROM session_records").fetchone()[0]
    finally:
        check.close()
    return tables, rows


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def authorize(key_id, app_key):
    token = base64.b64encode(f"{key_id}:{app_key}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(API_URL, headers={"Authorization": "Basic " + token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload(auth, bucket_id, name, payload):
    api = auth["apiInfo"]["storageApi"]["apiUrl"]
    got = _post(api + "/b2api/v3/b2_get_upload_url",
                json.dumps({"bucketId": bucket_id}).encode("utf-8"),
                {"Authorization": auth["authorizationToken"],
                 "Content-Type": "application/json"})
    # B2 checks the SHA-1 it is given against what arrives, so a truncated or
    # corrupted upload is rejected at their end rather than sitting in the
    # bucket looking like a backup.
    return _post(got["uploadUrl"], payload, {
        "Authorization": got["authorizationToken"],
        "X-Bz-File-Name": urllib.parse.quote(name),
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(payload)),
        "X-Bz-Content-Sha1": hashlib.sha1(payload).hexdigest(),
    })


def main():
    check_only = "--check" in sys.argv
    missing = [k for k in ("B2_KEY_ID", "B2_APPLICATION_KEY", "B2_BUCKET_ID")
               if not os.environ.get(k)]
    if missing:
        sys.exit("Not configured. Missing: %s" % ", ".join(missing))
    if not os.path.exists(DB_PATH):
        sys.exit("No database at %s" % DB_PATH)

    # timezone-aware: utcnow() is deprecated and goes away in a later Python,
    # and this runs unattended, so a warning today is a crash later.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = "phil-db/phil-%s.db" % stamp
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, "snapshot.db")
        tables, rows = snapshot(DB_PATH, local)
        size = os.path.getsize(local)
        print("snapshot: %d tables, %d session records, %.1f KB" % (len(tables), rows, size / 1024))
        if check_only:
            authorize(os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"])
            print("credentials accepted; nothing uploaded (--check)")
            return
        with open(local, "rb") as fh:
            payload = fh.read()

    auth = authorize(os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"])
    result = upload(auth, os.environ["B2_BUCKET_ID"], name, payload)
    print("uploaded %s (%d bytes, id %s)" % (name, result["contentLength"], result["fileId"]))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        # Loud, because this runs unattended and a silent failure is a backup
        # that is not happening.
        sys.exit("Upload failed: HTTP %s %s" % (exc.code, exc.read()[:300]))
