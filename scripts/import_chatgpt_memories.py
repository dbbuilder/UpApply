#!/usr/bin/env python3
"""
Import ChatGPT exported memories into UpApply.

Usage:
    python import_chatgpt_memories.py \
        --file /path/to/memory.json \
        --email you@example.com \
        --password yourpassword \
        [--api https://upapply-api.onrender.com]

ChatGPT memory export format (from Settings → Data Controls → Export):
    A JSON file containing either:
    - A list of strings: ["memory text", "memory text", ...]
    - A list of objects: [{"memory": "text"}, ...]
    - A dict with a "memories" key containing either of the above
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests


API_BASE = "https://upapply-api.onrender.com"

CATEGORY_RULES = [
    # (regex pattern, category)
    (r'\b(built|developed|created|designed|architected|launched|shipped|deployed)\b', 'project'),
    (r'\b(hired|client responded|won|landed|closed|got the job)\b', 'achievement'),
    (r'\b(feedback|client said|they mentioned|review|rating)\b', 'feedback'),
    (r'\b(learned|lesson|mistake|next time|should have|realized)\b', 'lesson'),
    (r'\b(expert|proficient|years? experience|skilled in|specialist)\b', 'skill_demo'),
]


def guess_category(text: str) -> str:
    text_lower = text.lower()
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, text_lower):
            return category
    return 'project'  # default


def make_title(text: str) -> str:
    """Generate a short title from the first sentence or first ~60 chars."""
    # Try first sentence
    match = re.match(r'^([^.!?]{10,80}[.!?])', text.strip())
    if match:
        title = match.group(1).strip()
        return title[:80]
    # Fall back to first 60 chars
    title = text.strip()[:60]
    if len(text) > 60:
        title = title.rsplit(' ', 1)[0] + '...'
    return title


def load_memories(path: Path) -> list[str]:
    """Load memory strings from a ChatGPT export file."""
    data = json.loads(path.read_text())

    # Handle various export shapes
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common keys
        for key in ('memories', 'memory', 'items', 'data'):
            if key in data:
                items = data[key]
                break
        else:
            print(f"Unknown dict structure. Keys: {list(data.keys())}")
            sys.exit(1)
    else:
        print(f"Unexpected top-level type: {type(data)}")
        sys.exit(1)

    texts = []
    for item in items:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            text = item.get('memory') or item.get('content') or item.get('text') or item.get('value')
            if text:
                texts.append(str(text))
            else:
                print(f"  Skipping unrecognised object shape: {list(item.keys())}")
        else:
            print(f"  Skipping unknown item type: {type(item)}")

    return [t.strip() for t in texts if t.strip()]


def login(api: str, email: str, password: str) -> str:
    resp = requests.post(f"{api}/api/v1/auth/login", json={"email": email, "password": password})
    if not resp.ok:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print("Logged in successfully.")
    return token


def import_batch(api: str, token: str, batch: list[dict]) -> int:
    resp = requests.post(
        f"{api}/api/v1/memories/bulk-import",
        json={"memories": batch},
        headers={"Authorization": f"Bearer {token}"},
    )
    if not resp.ok:
        print(f"  Batch failed: {resp.status_code} {resp.text[:200]}")
        return 0
    return len(resp.json())


def main():
    parser = argparse.ArgumentParser(description="Import ChatGPT memories into UpApply")
    parser.add_argument("--file", required=True, help="Path to ChatGPT memory.json export")
    parser.add_argument("--email", required=True, help="UpApply account email")
    parser.add_argument("--password", required=True, help="UpApply account password")
    parser.add_argument("--api", default=API_BASE, help="UpApply API base URL")
    parser.add_argument("--batch-size", type=int, default=20, help="Memories per batch (default 20)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without importing")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Loading memories from {path}...")
    texts = load_memories(path)
    print(f"Found {len(texts)} memories.")

    # Build UpApply memory objects
    memories = []
    for text in texts:
        memories.append({
            "title": make_title(text),
            "content": text,
            "category": guess_category(text),
        })

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW (first 5) ---")
        for m in memories[:5]:
            print(f"\n  category: {m['category']}")
            print(f"  title:    {m['title']}")
            print(f"  content:  {m['content'][:120]}...")
        print(f"\nWould import {len(memories)} memories. Run without --dry-run to import.")
        return

    # Login
    token = login(args.api, args.email, args.password)

    # Import in batches
    total_imported = 0
    batch_size = args.batch_size
    batches = [memories[i:i+batch_size] for i in range(0, len(memories), batch_size)]

    print(f"\nImporting {len(memories)} memories in {len(batches)} batches...")
    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} memories)...", end=" ")
        count = import_batch(args.api, token, batch)
        total_imported += count
        print(f"OK ({count} imported)")
        if i < len(batches):
            time.sleep(0.5)  # be gentle with the API

    print(f"\nDone. {total_imported}/{len(memories)} memories imported into UpApply.")


if __name__ == "__main__":
    main()
