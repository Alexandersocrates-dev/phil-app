#!/usr/bin/env python3
"""
Triggers Phil's daily jobs on a schedule.

This runs as a separate Railway service with a cron schedule set in its
settings. It does its work and exits.

Why it calls the app over HTTP rather than reading the database directly:
Railway volumes cannot be attached to more than one service, so this service has
no way to reach /data/phil.db. The app holds the volume, so the app does the
work and this only wakes it up.

Environment variables (set on the cron service, not the app):
    PHIL_BASE_URL   the app's address, e.g. https://phileducation.co.uk
    CRON_SECRET     must match the value set on the app

Railway requires a cron service to exit when it is finished. If it stays
running, every later scheduled run is skipped, so this exits in all cases,
including failure.
"""
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("PHIL_BASE_URL", "").rstrip("/")
SECRET = os.environ.get("CRON_SECRET", "")
TIMEOUT = 30
# The backup takes a snapshot and uploads it, so it needs longer than a set of
# database checks. Still well under the app's own five-minute cap.
BACKUP_TIMEOUT = 240

# Each job is (path, label, timeout). Adding one here is the whole change.
JOBS = [
    ("/internal/cron/retention", "daily checks", TIMEOUT),
    ("/internal/cron/backup", "offsite backup", BACKUP_TIMEOUT),
]


def run(path, label, timeout):
    """Calls one endpoint. Returns True if it succeeded.

    Every failure is caught and reported rather than raised: one job failing
    must not stop the next from running, and a cron service that crashes takes
    the rest of the schedule with it.
    """
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("X-Cron-Secret", SECRET)
    req.add_header("User-Agent", "phil-cron/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
            print(f"{label}: {resp.status} {body}")
            return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()[:300]
        print(f"{label} refused: {e.code} {detail}")
    except urllib.error.URLError as e:
        print(f"{label}: could not reach {url}: {e.reason}")
    except Exception as e:  # noqa: BLE001 - a cron job must always exit cleanly
        print(f"{label} failed: {type(e).__name__}: {e}")
    return False


def main():
    if not BASE or not SECRET:
        # Exit 0 rather than 1: Railway retries a failed cron service up to ten
        # times, and ten identical failures for a missing setting is noise, not
        # information. The message is the useful part.
        print("PHIL_BASE_URL and CRON_SECRET must both be set on this service.")
        return 0

    failed = [label for path, label, t in JOBS if not run(path, label, t)]
    if failed:
        # Named in the last line, so the cron run history shows which job broke
        # without anyone opening the logs. Still exit 0: a retry would repeat a
        # backup that may well have already uploaded.
        print("FAILED: " + ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
