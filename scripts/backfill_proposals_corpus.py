#!/usr/bin/env python3
"""
Backfill proposals corpus from historical applications.

Finds all non-draft applications that have a cover letter and ensures each one
has a corresponding proposals corpus entry. This seeds the self-improvement
pipeline for accounts that had applications before the feedback loop was added.

Usage:
    python scripts/backfill_proposals_corpus.py \\
        --email you@example.com \\
        --password yourpassword \\
        [--api https://upapply-api.onrender.com]

Safe to run multiple times — idempotent. Never downgrades a won (was_hired=True)
entry to a lower tier.
"""
import argparse
import sys

import requests


def main(args=None):
    parser = argparse.ArgumentParser(description="Backfill proposals corpus from historical applications")
    parser.add_argument("--email", required=True, help="UpApply account email")
    parser.add_argument("--password", required=True, help="UpApply account password")
    parser.add_argument("--api", default="https://upapply-api.onrender.com", help="API base URL")
    parsed = parser.parse_args(args)

    api = parsed.api.rstrip("/")

    print(f"Connecting to {api}...")
    resp = requests.post(
        f"{api}/api/v1/auth/login",
        json={"email": parsed.email, "password": parsed.password},
        timeout=30,
    )
    if not resp.ok:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Logged in successfully.")

    print("Running backfill (this may take a moment for large histories)...")
    resp = requests.post(
        f"{api}/api/v1/applications/backfill-proposals",
        headers=headers,
        timeout=120,
    )
    if not resp.ok:
        print(f"Backfill failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    result = resp.json()
    total = result["total"]
    created = result["created"]
    updated = result["updated"]
    skipped = result["skipped"]

    print()
    print("Backfill complete:")
    print(f"  Applications scanned : {total}")
    print(f"  Proposals created    : {created}  (new corpus entries)")
    print(f"  Proposals upgraded   : {updated}  (was_hired promoted to True)")
    print(f"  Skipped              : {skipped}  (already current)")
    if created == 0 and updated == 0:
        print()
        print("Nothing to do — corpus is already up to date.")
    else:
        print()
        print("Corpus updated. Cover letter generation will now draw on this history.")


if __name__ == "__main__":
    main()
