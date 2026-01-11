"""Memory endpoints with pgvector semantic search."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding
from app.models.user import User
from app.models.memory import Memory
from app.schemas.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryBulkImport,
)

router = APIRouter()


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memory_data: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new memory with embedding."""
    # Generate embedding for the memory content
    text_for_embedding = f"{memory_data.title}\n{memory_data.content}"
    if memory_data.outcome:
        text_for_embedding += f"\nOutcome: {memory_data.outcome}"

    embedding = await generate_embedding(text_for_embedding)

    # Create memory
    memory = Memory(
        user_id=current_user.id,
        title=memory_data.title,
        content=memory_data.content,
        category=memory_data.category,
        skills_demonstrated=memory_data.skills_demonstrated,
        industry=memory_data.industry,
        project_type=memory_data.project_type,
        client_type=memory_data.client_type,
        outcome=memory_data.outcome,
        metrics=memory_data.metrics,
        client_feedback=memory_data.client_feedback,
        source=memory_data.source,
        importance_score=memory_data.importance_score,
        embedding=embedding,
    )

    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    return memory


@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's memories."""
    query = select(Memory).where(Memory.user_id == current_user.id)

    if category:
        query = query.where(Memory.category == category)

    query = query.order_by(Memory.importance_score.desc(), Memory.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    memories = result.scalars().all()

    return memories


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific memory."""
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id, Memory.user_id == current_user.id
        )
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return memory


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    memory_data: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a memory."""
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id, Memory.user_id == current_user.id
        )
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # Update fields
    update_data = memory_data.model_dump(exclude_unset=True)
    content_changed = "title" in update_data or "content" in update_data or "outcome" in update_data

    for field, value in update_data.items():
        setattr(memory, field, value)

    # Regenerate embedding if content changed
    if content_changed:
        text_for_embedding = f"{memory.title}\n{memory.content}"
        if memory.outcome:
            text_for_embedding += f"\nOutcome: {memory.outcome}"
        memory.embedding = await generate_embedding(text_for_embedding)

    await db.commit()
    await db.refresh(memory)

    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory."""
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id, Memory.user_id == current_user.id
        )
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    await db.delete(memory)
    await db.commit()


@router.post("/search", response_model=List[MemorySearchResult])
async def search_memories(
    request: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search for relevant memories using pgvector."""
    # Generate embedding for search query
    query_embedding = await generate_embedding(request.query)

    # Build query with cosine similarity
    # Using raw SQL for pgvector operations
    from sqlalchemy import text

    sql = text("""
        SELECT
            id, user_id, title, content, category,
            skills_demonstrated, industry, project_type, client_type,
            outcome, metrics, client_feedback, source, importance_score,
            created_at, updated_at,
            1 - (embedding <=> :embedding::vector) as similarity
        FROM memories
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "user_id": current_user.id,
            "limit": request.limit,
        },
    )

    rows = result.fetchall()

    # Filter by threshold and format results
    search_results = []
    for row in rows:
        similarity = row.similarity
        if similarity < request.threshold:
            continue

        memory = MemoryResponse(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            content=row.content,
            category=row.category,
            skills_demonstrated=row.skills_demonstrated,
            industry=row.industry,
            project_type=row.project_type,
            client_type=row.client_type,
            outcome=row.outcome,
            metrics=row.metrics,
            client_feedback=row.client_feedback,
            source=row.source,
            importance_score=float(row.importance_score) if row.importance_score else 0.5,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

        search_results.append(
            MemorySearchResult(
                memory=memory,
                similarity=similarity,
                relevance_explanation=None,
            )
        )

    return search_results


@router.post("/bulk-import", response_model=List[MemoryResponse])
async def bulk_import_memories(
    request: MemoryBulkImport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import memories (e.g., from resume parsing)."""
    created_memories = []

    for memory_data in request.memories:
        # Generate embedding
        text_for_embedding = f"{memory_data.title}\n{memory_data.content}"
        if memory_data.outcome:
            text_for_embedding += f"\nOutcome: {memory_data.outcome}"

        embedding = await generate_embedding(text_for_embedding)

        memory = Memory(
            user_id=current_user.id,
            title=memory_data.title,
            content=memory_data.content,
            category=memory_data.category,
            skills_demonstrated=memory_data.skills_demonstrated,
            industry=memory_data.industry,
            project_type=memory_data.project_type,
            client_type=memory_data.client_type,
            outcome=memory_data.outcome,
            metrics=memory_data.metrics,
            client_feedback=memory_data.client_feedback,
            source=memory_data.source or "bulk_import",
            importance_score=memory_data.importance_score,
            embedding=embedding,
        )

        db.add(memory)
        created_memories.append(memory)

    await db.commit()

    # Refresh all memories
    for memory in created_memories:
        await db.refresh(memory)

    return created_memories
