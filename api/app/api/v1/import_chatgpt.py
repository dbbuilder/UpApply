"""Import ChatGPT conversations.json export — extract memories and cover letters."""
import json
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.security import get_current_user
from app.models.user import User
from app.models.memory import Memory
from app.models.proposal import Proposal

router = APIRouter()


class ImportResult(BaseModel):
    memories_imported: int
    proposals_imported: int
    conversations_processed: int
    skipped: int


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_messages(conversation: dict) -> list[dict]:
    """Flatten a conversation's mapping into ordered [role, text] pairs."""
    mapping = conversation.get("mapping", {})
    if not mapping:
        return []

    # Build parent→children graph and find root
    nodes: dict = {}
    for node_id, node in mapping.items():
        nodes[node_id] = node

    # Walk from current_node back to root, then reverse
    current = conversation.get("current_node") or ""
    chain: list[str] = []
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        chain.append(current)
        current = (nodes.get(current) or {}).get("parent") or ""
    chain.reverse()

    messages: list[dict] = []
    for node_id in chain:
        node = nodes.get(node_id, {})
        msg = node.get("message")
        if not msg:
            continue
        role = (msg.get("author") or {}).get("role", "")
        if role not in ("user", "assistant"):
            continue
        parts = (msg.get("content") or {}).get("parts") or []
        text = " ".join(str(p) for p in parts if isinstance(p, str)).strip()
        if text:
            messages.append({"role": role, "text": text})
    return messages


def _conversation_text(messages: list[dict], max_chars: int = 6000) -> str:
    lines = []
    for m in messages:
        tag = "User" if m["role"] == "user" else "ChatGPT"
        lines.append(f"{tag}: {m['text']}")
    full = "\n\n".join(lines)
    return full[:max_chars]


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
You are extracting useful professional context from a ChatGPT conversation history
belonging to a freelancer. Your output is a JSON object with two arrays:

"memories": array of objects with:
  - "title": short title (≤80 chars)
  - "content": the full memory text (1-4 sentences)
  - "category": one of project|achievement|skill_demo|feedback|lesson|context
  - "outcome": optional outcome string (leave "" if none)
  - "skills_demonstrated": array of skill strings (can be empty)

"proposals": array of cover letter texts the freelancer generated or discussed,
  each as a plain string. Only include actual cover letter / proposal text,
  not general advice.

Rules:
- Only extract facts about THIS freelancer — their projects, skills, wins, clients,
  lessons, and writing samples. Skip generic ChatGPT advice.
- Skip anything about other people's work.
- If nothing useful is found, return {"memories": [], "proposals": []}.
- Output ONLY valid JSON, no markdown fences, no extra commentary.\
"""


async def _extract_from_conversation(
    client: AsyncAnthropic,
    conv_text: str,
    title: str,
) -> dict:
    prompt = f'Conversation title: "{title}"\n\n{conv_text}'
    try:
        resp = await client.messages.create(
            model=settings.cover_letter_model,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.2,
        )
        raw = resp.content[0].text.strip()
        return json.loads(raw)
    except Exception:
        return {"memories": [], "proposals": []}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/import-chatgpt-conversations", response_model=ImportResult)
async def import_chatgpt_conversations(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload conversations.json from a ChatGPT data export.
    Claude extracts memories (project stories, skills, wins) and cover letters
    (stored as Proposal records) to feed future cover letter generation.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Upload a .json file")

    raw = await file.read()
    try:
        conversations: list = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(conversations, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array of conversations")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    memories_imported = 0
    proposals_imported = 0
    conversations_processed = 0
    skipped = 0

    # Process in batches of 5 to avoid overwhelming Claude
    batch_size = 5

    for i in range(0, len(conversations), batch_size):
        batch = conversations[i : i + batch_size]

        tasks = []
        for conv in batch:
            messages = _extract_messages(conv)
            if not messages:
                skipped += 1
                continue
            text = _conversation_text(messages)
            title = conv.get("title") or "Untitled"
            tasks.append(_extract_from_conversation(client, text, title))

        if not tasks:
            continue

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                skipped += 1
                continue

            conversations_processed += 1
            extracted_memories = result.get("memories") or []
            extracted_proposals = result.get("proposals") or []

            # Embed and save memories in parallel
            mem_embed_tasks = [
                generate_embedding(f"{m.get('title', '')}\n{m.get('content', '')}")
                for m in extracted_memories
                if m.get("content")
            ]
            if mem_embed_tasks:
                embeddings = await asyncio.gather(*mem_embed_tasks, return_exceptions=True)
                for mem_data, embedding in zip(
                    [m for m in extracted_memories if m.get("content")], embeddings
                ):
                    if isinstance(embedding, Exception):
                        continue
                    memory = Memory(
                        user_id=current_user.id,
                        title=str(mem_data.get("title") or "")[:200],
                        content=str(mem_data.get("content") or ""),
                        category=str(mem_data.get("category") or "project"),
                        outcome=str(mem_data.get("outcome") or "") or None,
                        skills_demonstrated=mem_data.get("skills_demonstrated") or [],
                        embedding=embedding,
                        source="chatgpt_import",
                    )
                    db.add(memory)
                    memories_imported += 1

            # Embed and save proposals (cover letters)
            prop_embed_tasks = [
                generate_embedding(text[:2000])
                for text in extracted_proposals
                if isinstance(text, str) and len(text) > 100
            ]
            if prop_embed_tasks:
                prop_embeddings = await asyncio.gather(*prop_embed_tasks, return_exceptions=True)
                valid_proposals = [
                    t for t in extracted_proposals
                    if isinstance(t, str) and len(t) > 100
                ]
                for prop_text, embedding in zip(valid_proposals, prop_embeddings):
                    if isinstance(embedding, Exception):
                        continue
                    proposal = Proposal(
                        user_id=current_user.id,
                        upwork_job_url=f"chatgpt_import_{current_user.id}_{proposals_imported}",
                        job_title="Imported from ChatGPT",
                        cover_letter_text=prop_text,
                        was_hired=False,
                        status="imported",
                        source="chatgpt_import",
                        embedding=embedding,
                    )
                    db.add(proposal)
                    proposals_imported += 1

        await db.commit()

    return ImportResult(
        memories_imported=memories_imported,
        proposals_imported=proposals_imported,
        conversations_processed=conversations_processed,
        skipped=skipped,
    )
