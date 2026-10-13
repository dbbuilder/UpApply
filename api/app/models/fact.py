"""Fact model — atomic, verified claims about the user that generation may cite."""
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

FACT_KINDS = ("project", "metric", "credential", "client_quote", "role", "tech", "outcome")
FACT_STATUSES = ("candidate", "approved", "rejected")
JOB_TYPES = ("cto", "saas", "sql", "cloud", "ai", "fullstack")


class Fact(Base):
    """One atomic claim (what to say). Only status='approved' rows are retrievable.

    ARRAY/JSONB columns are not mutation-tracked: always assign a new list.
    """

    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    skills: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    industries: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    job_types: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )

    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", server_default="candidate"
    )

    # First source that produced the fact; `sources` holds every merged provenance entry
    # as {"source_type", "source_ref", "snippet"}.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    times_in_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Embeds statement + detail only
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_facts_user_status", "user_id", "status"),
        Index(
            "ix_facts_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
