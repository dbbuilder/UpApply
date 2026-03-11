#!/usr/bin/env python3
"""
Import ChatGPT conversation corpus into UpApply as semantic memories.

Extracts two types of memories from a ChatGPT export directory:
  1. Past proposals — cover letter conversations (job posting + final letter)
  2. Bio/achievement memories — from a user-supplied JSON file

Usage:
    python scripts/import_chatgpt_corpus.py \\
        --data-dir /path/to/chatgpt-export \\
        --email you@example.com \\
        --password <password> \\
        [--bio-file scripts/my_bio_memories.json] \\
        [--api https://upapply-api.onrender.com] \\
        [--batch-size 10] \\
        [--dry-run] \\
        [--proposals-only] \\
        [--bio-only]

Bio file format (JSON array of memory objects):
    [
      {
        "title": "Short descriptive title",
        "content": "Full memory text...",
        "category": "achievement|project|skill_demo|lesson|feedback",
        "skills_demonstrated": ["Python", "Azure", ...],
        "industry": "Education|Healthcare|SaaS|...",
        "project_type": "Cloud Migration|SaaS Platform|...",
        "outcome": "Optional outcome description",
        "importance_score": 0.0-1.0
      },
      ...
    ]

Example bio file for Chris: scripts/chris_bio_memories.json
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://upapply-api.onrender.com"

# ──────────────────────────────────────────────────────────────────────────────
# Technology keyword → skills mapping
# ──────────────────────────────────────────────────────────────────────────────

TECH_SKILLS = {
    "sql server": "SQL Server", "t-sql": "T-SQL", "tsql": "T-SQL",
    "azure sql": "Azure SQL", "azure": "Azure", "azure devops": "Azure DevOps",
    "azure functions": "Azure Functions", "azure app service": "Azure App Service",
    "azure key vault": "Azure Key Vault", "azure static web": "Azure Static Web Apps",
    "azure front door": "Azure Front Door", "arm template": "ARM Templates",
    "c#": "C#", ".net": ".NET", "asp.net": "ASP.NET Core",
    "entity framework": "Entity Framework", "serilog": "Serilog",
    "vb.net": "VB.NET", "blazor": "Blazor",
    "python": "Python", "fastapi": "FastAPI", "django": "Django",
    "flask": "Flask", "sqlalchemy": "SQLAlchemy", "alembic": "Alembic",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "pgvector": "pgvector", "chromadb": "ChromaDB", "weaviate": "Weaviate",
    "redis": "Redis", "elasticsearch": "Elasticsearch",
    "node.js": "Node.js", "nodejs": "Node.js", "express": "Express",
    "react": "React", "vue": "Vue.js", "angular": "Angular",
    "typescript": "TypeScript", "javascript": "JavaScript",
    "tailwind": "Tailwind CSS", "bootstrap": "Bootstrap",
    "docker": "Docker", "kubernetes": "Kubernetes", "render": "Render",
    "fly.io": "Fly.io", "vercel": "Vercel", "aws": "AWS",
    "openai": "OpenAI API", "gpt-4": "GPT-4", "embedding": "OpenAI Embeddings",
    "rag": "RAG", "vector": "Vector Search", "llm": "LLM Integration",
    "powershell": "PowerShell", "bash": "Bash", "git": "Git",
    "stripe": "Stripe", "sendgrid": "SendGrid", "twilio": "Twilio",
    "flutter": "Flutter", "capacitor": "Capacitor",
    "iis": "IIS", "sql agent": "SQL Agent", "replication": "SQL Replication",
}

INDUSTRY_MAP = {
    "school": "Education", "education": "Education", "ferpa": "Education",
    "student": "Education", "campus": "Education", "k-12": "Education",
    "university": "Education", "college": "Education",
    "health": "Healthcare", "medical": "Healthcare", "hipaa": "Healthcare",
    "hospital": "Healthcare", "clinic": "Healthcare", "ehr": "Healthcare",
    "truck": "Transportation", "dispatch": "Transportation", "cdl": "Transportation",
    "logistics": "Transportation", "freight": "Transportation",
    "finance": "Finance", "fintech": "Finance", "payment": "Finance",
    "billing": "Finance", "accounting": "Finance", "invoice": "Finance",
    "real estate": "Real Estate", "property": "Real Estate",
    "retail": "Retail", "ecommerce": "Retail", "e-commerce": "Retail",
    "restaurant": "Food & Beverage", "food": "Food & Beverage",
    "nonprofit": "Non-Profit", "non-profit": "Non-Profit",
    "church": "Faith / Non-Profit", "faith": "Faith / Non-Profit",
    "aesthetics": "Beauty / Aesthetics", "salon": "Beauty / Aesthetics",
    "government": "Government", "compliance": "Compliance",
    "security": "Security", "saas": "SaaS", "startup": "Startup",
}

# ──────────────────────────────────────────────────────────────────────────────
# Cover letter conversation detection
# ──────────────────────────────────────────────────────────────────────────────

COVER_LETTER_TITLE_PATTERNS = [
    r"\bcover letter\b", r"\bproposal\b", r"\bupwork\b",
    r"\bjob application\b", r"\bjob posting\b", r"\bapply\b",
    r"\bfreelance\b", r"\bpitch\b", r"\bjob description\b",
    r"\bhiring\b", r"\bcandidate\b", r"\bopportunity\b",
]

COVER_LETTER_CONTENT_PATTERNS = [
    r"write a cover letter", r"write a proposal", r"write an upwork",
    r"tailor.*cover letter", r"generate.*proposal", r"upwork.*proposal",
    r"job posting.*proposal", r"proposal.*upwork", r"cover letter.*job",
    r"i am looking for", r"we are looking for", r"seeking a",
    r"job description", r"hourly rate", r"\bbudget\b.*\$",
    r"fixed.price project", r"fixed price",
]

def is_cover_letter_conv(title: str, first_user_msg: str) -> bool:
    tl = title.lower()
    for pat in COVER_LETTER_TITLE_PATTERNS:
        if re.search(pat, tl):
            return True
    fl = first_user_msg.lower()
    for pat in COVER_LETTER_CONTENT_PATTERNS:
        if re.search(pat, fl):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Message extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_messages(conversation: dict) -> list[tuple[str, str]]:
    """Return ordered list of (role, text) for user/assistant messages."""
    mapping = conversation.get("mapping", {})
    nodes = list(mapping.values())

    # Build child → parent map and find root
    id_to_node = {n["id"]: n for n in nodes if "id" in n}
    child_to_parent = {}
    for node in nodes:
        for child_id in node.get("children", []):
            child_to_parent[child_id] = node["id"]

    # Find root (node with no parent)
    all_ids = set(id_to_node.keys())
    roots = all_ids - set(child_to_parent.keys())
    if not roots:
        return []

    # Walk tree in order (DFS, take first child at each branch)
    messages = []
    visited = set()

    def walk(node_id):
        if node_id in visited or node_id not in id_to_node:
            return
        visited.add(node_id)
        node = id_to_node[node_id]
        msg = node.get("message")
        if msg:
            role = msg.get("author", {}).get("role", "")
            parts = msg.get("content", {}).get("parts", [])
            text = " ".join(str(p) for p in parts if isinstance(p, str)).strip()
            if text and role in ("user", "assistant"):
                messages.append((role, text))
        for child_id in node.get("children", []):
            walk(child_id)

    for root_id in roots:
        walk(root_id)

    return messages


def extract_skills(text: str) -> list[str]:
    tl = text.lower()
    found = set()
    for keyword, skill in TECH_SKILLS.items():
        if keyword in tl:
            found.add(skill)
    return sorted(found)


def detect_industry(text: str) -> str | None:
    tl = text.lower()
    for keyword, industry in INDUSTRY_MAP.items():
        if keyword in tl:
            return industry
    return None


def make_title(text: str, max_len: int = 80) -> str:
    match = re.match(r"^([^.!?\n]{10,80}[.!?\n])", text.strip())
    if match:
        return match.group(1).strip()[:max_len]
    return text.strip()[:max_len].rsplit(" ", 1)[0] + ("..." if len(text) > max_len else "")


# ──────────────────────────────────────────────────────────────────────────────
# Memory builders
# ──────────────────────────────────────────────────────────────────────────────

def build_proposal_memory(title: str, job_text: str, letter_text: str) -> dict:
    combined = job_text + " " + letter_text
    skills = extract_skills(combined)
    industry = detect_industry(combined)

    # Trim to reasonable sizes — embed both job context and final letter
    job_snippet = job_text[:1500].strip()
    letter_snippet = letter_text[:2000].strip()

    content = f"JOB POSTING:\n{job_snippet}\n\nPROPOSAL WRITTEN:\n{letter_snippet}"

    return {
        "title": f"Past Proposal: {title[:60]}",
        "content": content,
        "category": "project",
        "skills_demonstrated": skills[:15] if skills else None,
        "industry": industry,
        "project_type": "Upwork Proposal",
        "client_type": "Upwork Client",
        "source": "chatgpt_corpus",
        "importance_score": 0.8,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Bio memory loader
# ──────────────────────────────────────────────────────────────────────────────

def load_bio_memories(bio_file: Path) -> list[dict]:
    """Load bio/achievement memories from a user-supplied JSON file."""
    if not bio_file.exists():
        print(f"Bio file not found: {bio_file}")
        sys.exit(1)
    with open(bio_file) as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"Bio file must be a JSON array. Got: {type(data)}")
        sys.exit(1)
    # Ensure required fields
    memories = []
    for i, item in enumerate(data):
        if not item.get("title") or not item.get("content"):
            print(f"  Skipping bio item {i}: missing title or content")
            continue
        item.setdefault("category", "achievement")
        item.setdefault("source", "bio_import")
        item.setdefault("importance_score", 0.8)
        memories.append(item)
    return memories


# See scripts/chris_bio_memories.json for Chris Therriault's pre-built bio memories.
# To create your own, follow the JSON format documented at the top of this file.

_bio_memories_placeholder = [  # noqa: F841  (not used at runtime, kept as format reference)
    {
        "title": "Example: your signature achievement",
        "content": "Describe your most impressive project or achievement here...",
        "category": "achievement",
        "skills_demonstrated": ["Technology A", "Technology B"],
        "industry": "Your Industry",
        "project_type": "Cloud Migration|SaaS|Consulting|etc.",
        "outcome": "Optional: quantified outcome",
        "importance_score": 1.0,
    },
]  # end _bio_memories_placeholder


# ──────────────────────────────────────────────────────────────────────────────
# API client
# ──────────────────────────────────────────────────────────────────────────────

def login(api: str, email: str, password: str) -> str:
    resp = requests.post(
        f"{api}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if not resp.ok:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print(f"Logged in as {email}")
    return token


def import_batch(api: str, token: str, batch: list[dict]) -> int:
    resp = requests.post(
        f"{api}/api/v1/memories/bulk-import",
        json={"memories": batch},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    if not resp.ok:
        print(f"  Batch failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return len(resp.json())


# ──────────────────────────────────────────────────────────────────────────────
# Main extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_proposals(data_dir: Path, verbose: bool = False) -> list[dict]:
    memories = []
    skipped = 0
    total_convs = 0

    for f in sorted(data_dir.glob("conversations-*.json")):
        with open(f) as fp:
            data = json.load(fp)

        for conv in data:
            total_convs += 1
            title = conv.get("title", "(no title)")
            messages = extract_messages(conv)
            user_msgs = [m for role, m in messages if role == "user"]
            asst_msgs = [m for role, m in messages if role == "assistant"]

            if not user_msgs or not asst_msgs:
                skipped += 1
                continue

            first_user = user_msgs[0]

            if not is_cover_letter_conv(title, first_user):
                skipped += 1
                continue

            # Job posting = first user message
            job_text = first_user

            # Final letter = last assistant message (most refined version)
            final_letter = asst_msgs[-1]

            # Skip if the final assistant message is very short (likely an error/clarification)
            if len(final_letter.strip()) < 100:
                if len(asst_msgs) > 1:
                    final_letter = asst_msgs[-2]
                else:
                    skipped += 1
                    continue

            mem = build_proposal_memory(title, job_text, final_letter)
            memories.append(mem)

            if verbose:
                print(f"  [PROPOSAL] {title[:70]}")

    print(f"Scanned {total_convs} conversations → {len(memories)} proposals extracted ({skipped} skipped)")
    return memories


def run_import(
    api: str,
    token: str,
    memories: list[dict],
    batch_size: int,
    label: str,
) -> int:
    if not memories:
        print(f"No {label} to import.")
        return 0

    batches = [memories[i : i + batch_size] for i in range(0, len(memories), batch_size)]
    print(f"\nImporting {len(memories)} {label} in {len(batches)} batches...")

    total = 0
    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} items)...", end=" ", flush=True)
        count = import_batch(api, token, batch)
        total += count
        print(f"OK ({count} imported)")
        if i < len(batches):
            time.sleep(0.75)  # be gentle

    return total


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import ChatGPT conversation corpus into UpApply memories"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Path to ChatGPT export directory containing conversations-*.json files",
    )
    parser.add_argument(
        "--bio-file",
        default=None,
        help=(
            "Path to a JSON file containing bio/achievement memories. "
            "See scripts/chris_bio_memories.json for format. "
            "Required unless --proposals-only is set."
        ),
    )
    parser.add_argument("--email", required=True, help="UpApply account email")
    parser.add_argument("--password", required=True, help="UpApply account password")
    parser.add_argument("--api", default=API_BASE, help=f"UpApply API base URL (default: {API_BASE})")
    parser.add_argument("--batch-size", type=int, default=10, help="Memories per batch (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without importing")
    parser.add_argument("--proposals-only", action="store_true", help="Import only past proposals (skip bio)")
    parser.add_argument("--bio-only", action="store_true", help="Import only bio memories (skip proposals)")
    parser.add_argument("--verbose", action="store_true", help="Show each extracted conversation title")
    args = parser.parse_args()

    do_proposals = not args.bio_only
    do_bio = not args.proposals_only

    # ── Validate args ─────────────────────────────────────────────────────────
    if do_proposals and not args.data_dir:
        print("--data-dir is required when importing proposals (or use --bio-only)")
        sys.exit(1)

    if do_bio and not args.bio_file:
        print("--bio-file is required when importing bio memories (or use --proposals-only)")
        print("Example: --bio-file scripts/chris_bio_memories.json")
        sys.exit(1)

    data_dir = Path(args.data_dir) if args.data_dir else None
    if data_dir and not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)

    # ── Extract ──────────────────────────────────────────────────────────────
    proposal_memories = []
    if do_proposals:
        print(f"\nScanning {data_dir} for cover letter conversations...")
        proposal_memories = extract_proposals(data_dir, verbose=args.verbose)

    bio_memories = []
    if do_bio:
        bio_file = Path(args.bio_file)
        bio_memories = load_bio_memories(bio_file)
        print(f"Bio/achievement memories: {len(bio_memories)} loaded from {bio_file.name}")

    total_queued = len(proposal_memories) + len(bio_memories)
    print(f"\nTotal memories queued: {total_queued}")

    # ── Dry run preview ───────────────────────────────────────────────────────
    if args.dry_run:
        print("\n─── DRY RUN PREVIEW ───────────────────────────────────────────")
        all_preview = bio_memories[:3] + proposal_memories[:3]
        for m in all_preview:
            print(f"\n  category:  {m.get('category')}")
            print(f"  title:     {m.get('title')}")
            print(f"  industry:  {m.get('industry')}")
            print(f"  skills:    {', '.join((m.get('skills_demonstrated') or [])[:5])}")
            print(f"  score:     {m.get('importance_score')}")
            snippet = m.get("content", "")[:120].replace("\n", " ")
            print(f"  content:   {snippet}...")
        print(f"\nWould import {total_queued} memories. Run without --dry-run to proceed.")
        return

    if total_queued == 0:
        print("Nothing to import.")
        return

    # ── Login and import ─────────────────────────────────────────────────────
    token = login(args.api, args.email, args.password)
    grand_total = 0

    if do_bio and bio_memories:
        grand_total += run_import(args.api, token, bio_memories, args.batch_size, "bio/achievement memories")

    if do_proposals and proposal_memories:
        grand_total += run_import(args.api, token, proposal_memories, args.batch_size, "past proposals")

    print(f"\nDone. {grand_total}/{total_queued} memories imported into UpApply.")
    print("Run a search at /api/v1/memories/search to verify semantic retrieval.")


if __name__ == "__main__":
    main()
