#!/usr/bin/env python3
"""
Triggers Phil's retention check on a schedule.

This runs as a separate Railway service with a cron schedule set in its
settings. It does one thing and exits.

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


def main():
    if not BASE or not SECRET:
        # Exit 0 rather than 1: Railway retries a failed cron service up to ten
        # times, and ten identical failures for a missing setting is noise, not
        # information. The message is the useful part.
        print("PHIL_BASE_URL and CRON_SECRET must both be set on this service.")
        return 0

    url = f"{BASE}/internal/cron/retention"
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("X-Cron-Secret", SECRET)
    req.add_header("User-Agent", "phil-cron/1.0")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
            print(f"{resp.status} {body}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()[:200]
        print(f"retention check refused: {e.code} {detail}")
    except urllib.error.URLError as e:
        print(f"could not reach {url}: {e.reason}")
    except Exception as e:  # noqa: BLE001 - a cron job must always exit cleanly
        print(f"retention check failed: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
