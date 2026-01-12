"""Proposal model for storing submitted proposals with vector embeddings."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Numeric, Boolean, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job


class Proposal(Base):
    """Store submitted proposals for learning and reuse."""

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Upwork identifiers for deduplication
    upwork_proposal_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, unique=True
    )
    upwork_job_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Proposal content
    cover_letter_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Job context (stored for reference even if job record is deleted)
    job_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    job_description_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_skills: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    job_budget: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Bid details
    bid_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    bid_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # hourly, fixed

    # Vector embedding for semantic search
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    # Outcome tracking
    status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # submitted, viewed, responded, hired, declined
    was_hired: Mapped[Optional[bool]] = mapped_column(nullable=True)
    client_responded: Mapped[Optional[bool]] = mapped_column(nullable=True)
    earnings: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(
        String(50), default="manual"
    )  # manual, scraped, extension

    # Timestamps
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="proposals")
    job: Mapped[Optional["Job"]] = relationship("Job", back_populates="proposals")

    __table_args__ = (
        Index(
            "ix_proposals_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
