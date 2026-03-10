"""Seed proposal_anchors for a user via the UpApply API.

Usage:
    python seed_proposal_anchors.py --api-url https://upapply-api.onrender.com \
        --email chris@servicevision.net --password <password> \
        --anchors-file chris_proposal_anchors.json

The anchors JSON file must contain the proposal_anchors dict to PATCH into the user profile.
"""
import argparse
import json
import sys
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="https://upapply-api.onrender.com")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--anchors-file", required=True, help="JSON file with proposal_anchors dict")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Load anchors
    with open(args.anchors_file) as f:
        anchors = json.load(f)

    print(f"Loaded anchors with keys: {list(anchors.keys())}")

    if args.dry_run:
        print("DRY RUN — would PATCH proposal_anchors:")
        print(json.dumps(anchors, indent=2))
        return

    # Login
    resp = requests.post(
        f"{args.api_url}/api/v1/auth/login",
        json={"email": args.email, "password": args.password},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Logged in as {args.email}")

    # First GET the existing profile so we don't clobber other fields
    get_resp = requests.get(f"{args.api_url}/api/v1/profile", headers=headers, timeout=30)
    get_resp.raise_for_status()
    existing = get_resp.json()

    # Merge anchors in and PUT back
    existing["proposal_anchors"] = anchors
    # Remove read-only response-only fields that PUT doesn't accept
    for key in ("id", "user_id", "updated_at"):
        existing.pop(key, None)

    resp = requests.put(
        f"{args.api_url}/api/v1/profile",
        json=existing,
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 204):
        print(f"ERROR {resp.status_code}: {resp.text}")
        sys.exit(1)

    print("proposal_anchors updated successfully.")
    try:
        print(json.dumps(resp.json().get("proposal_anchors"), indent=2))
    except Exception:
        pass


if __name__ == "__main__":
    main()
