#!/usr/bin/env python3
"""
Extract fact candidates from a ChatGPT export and send them to UpApply's /facts/ingest.

Only the freelancer's own (user) turns are SOURCE TEXT. The last assistant message
(usually the final letter) travels as CONTEXT so the extractor can interpret what the
user was correcting — assistant text is never stored as voice and never a fact source.

Usage:
    UPAPPLY_PASSWORD='...' python scripts/ingest_chatgpt_facts.py \\
        /Users/admin/dev2/UpApply/working/chatgpt-export \\
        --email chris@servicevision.net \\
        [--api https://upapply-api.onrender.com] [--batch-size 5] [--limit N] [--dry-run]
        [--source signed|work|all]

--source signed (default): only the final message signed "Chris" / "Chris Therriault" in each
  conversation, sent as source_type chatgpt_signed_letter. Those letters were sent under the
  freelancer's name, so their claims are endorsed; the first user message (usually the job
  post) travels as CONTEXT only.
--source work: the freelancer's own turns from work conversations (cover letter in the title or
  any message, plus career titles). --source all: every conversation (--all is an alias).
Everything not selected never leaves the machine.

Re-runnable: conversations already ingested (by conversation id) are skipped server-side.
Candidates land in the Facts review page (status=candidate) unless they match an
already-approved fact at >= 0.92 similarity, in which case they merge and stay approved.
"""
import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

import requests

DEFAULT_EXPORT_DIR = "/Users/admin/dev2/UpApply/working/chatgpt-export"
API_BASE = "https://upapply-api.onrender.com"
SOURCE_TYPE = "chatgpt_user_turn"
SIGNED_SOURCE_TYPE = "chatgpt_signed_letter"
# A sign-off line ("Chris", "Chris Therriault", "- Chris,") within the last few lines of a message.
SIGNATURE = re.compile(r"^\s*(?:[-–—]\s*)?Chris(?:\s+Therriault)?\s*[,.]?\s*$", re.M)
SIGNATURE_TAIL_LINES = 6
MAX_SOURCE_CHARS = 12000
MAX_CONTEXT_CHARS = 4000
MIN_USER_CHARS = 40
COVER_LETTER = re.compile(r"cover[\s-]?letter", re.I)
CAREER_TITLE = re.compile(
    r"proposal|upwork|application|apply|resume|résumé|\bcv\b|\bbio\b|linkedin|profile|portfolio|"
    r"interview|\brfp\b|\brfq\b|hire|hiring|job|role|position|expert|expertise|specialist|consult|"
    r"freelanc|contract|\bcto\b|fractional|advisor|engineer|developer|architect|case stud|testimonial|"
    r"client|pitch|capabilit|qualification|experience|background|career|screening|response to|reply to|offer",
    re.I,
)


def load_conversations(export_dir: Path) -> list[dict]:
    """Read conversations-*.json (new export layout) or conversations.json (old layout)."""
    files = sorted(export_dir.glob("conversations-*.json")) or sorted(export_dir.glob("conversations.json"))
    conversations: list[dict] = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, list):
            conversations.extend(data)
    return conversations


def conversation_messages(conv: dict) -> list[tuple[str, str]]:
    """Ordered (role, text) pairs along the active branch (current_node back to root)."""
    mapping = conv.get("mapping") or {}
    chain: list[str] = []
    seen: set[str] = set()
    node_id = conv.get("current_node")
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(node_id)
        node_id = (mapping[node_id] or {}).get("parent")

    messages: list[tuple[str, str]] = []
    for nid in reversed(chain):
        msg = (mapping[nid] or {}).get("message") or {}
        role = (msg.get("author") or {}).get("role")
        if role not in ("user", "assistant"):
            continue
        parts = (msg.get("content") or {}).get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if text:
            messages.append((role, text))
    return messages


def is_work_conversation(conv: dict) -> bool:
    """Cover letter mentioned in the title or any message, or a career-flavoured title."""
    title = conv.get("title") or ""
    if COVER_LETTER.search(title) or CAREER_TITLE.search(title):
        return True
    return any(COVER_LETTER.search(text) for _, text in conversation_messages(conv))


def is_signed(text: str) -> bool:
    tail = [line for line in text.splitlines() if line.strip()][-SIGNATURE_TAIL_LINES:]
    return bool(SIGNATURE.search("\n".join(tail)))


def build_signed_item(conv: dict) -> list[dict]:
    """The final Chris-signed message of a conversation (either role), or nothing. The first
    user message is never the letter: it is usually the job post and travels as context."""
    conv_id = conv.get("id") or conv.get("conversation_id")
    messages = conversation_messages(conv)
    first_user_idx = next((i for i, (role, _) in enumerate(messages) if role == "user"), None)
    signed = [text for i, (_, text) in enumerate(messages) if i != first_user_idx and is_signed(text)]
    if not conv_id or not signed:
        return []
    context = f"Conversation title: {conv.get('title') or ''}"
    first_user = next((text for role, text in messages if role == "user"), "")
    if first_user:
        context += f"\n\nFirst message of the conversation (often the client's job post):\n{first_user[:MAX_CONTEXT_CHARS]}"
    return [{"text": signed[-1][:MAX_SOURCE_CHARS], "source_ref": conv_id, "context": context}]


def chunk_text(text: str, size: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most `size` chars."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:size])
            para = para[size:]
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > size:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_items(conv: dict) -> list[dict]:
    """FactIngestItem dicts for one conversation (empty when nothing worth extracting)."""
    conv_id = conv.get("id") or conv.get("conversation_id")
    if not conv_id:
        return []
    messages = conversation_messages(conv)
    user_text = "\n\n".join(t for role, t in messages if role == "user")
    if len(user_text) < MIN_USER_CHARS:
        return []

    assistant = [t for role, t in messages if role == "assistant"]
    context = f"Conversation title: {conv.get('title') or ''}"
    if assistant:
        context += f"\n\nFinal assistant message:\n{assistant[-1][:MAX_CONTEXT_CHARS]}"

    chunks = chunk_text(user_text, MAX_SOURCE_CHARS)
    return [
        {
            "text": chunk,
            "source_ref": conv_id if len(chunks) == 1 else f"{conv_id}#{n + 1}",
            "context": context,
        }
        for n, chunk in enumerate(chunks)
    ]


def login(api: str, email: str, password: str) -> str:
    resp = requests.post(f"{api}/api/v1/auth/login", json={"email": email, "password": password}, timeout=30)
    if not resp.ok:
        print(f"Login failed: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    return resp.json()["access_token"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract fact candidates from a ChatGPT export")
    parser.add_argument("export_dir", nargs="?", default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--email", help="UpApply account email (required unless --dry-run)")
    parser.add_argument("--api", default=API_BASE)
    parser.add_argument("--batch-size", type=int, default=5, help="Items per /facts/ingest call (max 25)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N conversations")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report; no API calls")
    parser.add_argument("--source", choices=("signed", "work", "all"), default="signed",
                        help="signed: final Chris-signed letters (default); work: own turns from work chats; all")
    parser.add_argument("--all", action="store_true", help="Alias for --source all")
    args = parser.parse_args(argv)

    export_dir = Path(args.export_dir)
    source = "all" if args.all else args.source
    loaded = load_conversations(export_dir)
    if source == "signed":
        conversations = [c for c in loaded if build_signed_item(c)]
        builder, source_type, scope = build_signed_item, SIGNED_SOURCE_TYPE, "signed by Chris"
    else:
        conversations = loaded if source == "all" else [c for c in loaded if is_work_conversation(c)]
        builder, source_type, scope = build_items, SOURCE_TYPE, "all" if source == "all" else "work only"
    if args.limit:
        conversations = conversations[: args.limit]
    items = [item for conv in conversations for item in builder(conv)]
    print(f"{len(conversations)} of {len(loaded)} conversations ({scope}) -> {len(items)} items from {export_dir}")

    if args.dry_run:
        for item in items[:3]:
            print(f"--- {item['source_ref']} ---\n{item['text'][:400]}\n")
        return

    if not args.email:
        parser.error("--email is required unless --dry-run")
    password = os.environ.get("UPAPPLY_PASSWORD") or getpass.getpass("UpApply password: ")
    api = args.api.rstrip("/")
    headers = {"Authorization": f"Bearer {login(api, args.email, password)}"}

    batch_size = max(1, min(args.batch_size, 25))
    totals = {"created": 0, "merged": 0, "auto_approved": 0, "skipped": 0, "failed": 0}
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        resp = requests.post(
            f"{api}/api/v1/facts/ingest",
            json={"source_type": source_type, "items": batch, "auto_approve": False},
            headers=headers,
            timeout=600,
        )
        if not resp.ok:
            print(f"  Batch {start // batch_size + 1} failed: {resp.status_code} {resp.text[:300]}")
            totals["failed"] += len(batch)
            continue
        result = resp.json()
        for key in totals:
            totals[key] += result.get(key, 0)
        print(f"  {min(start + batch_size, len(items))}/{len(items)} items — {result}")

    print(f"Done: {totals}")


if __name__ == "__main__":
    main()
