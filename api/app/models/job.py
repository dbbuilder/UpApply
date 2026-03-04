"""Job model for scraped Upwork jobs."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Numeric, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.application import Application
    from app.models.cover_letter import CoverLetter
    from app.models.screening_answer import ScreeningAnswer
    from app.models.proposal import Proposal


class Job(Base):
    """Upwork job postings scraped or submitted via extension."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Upwork identifiers
    upwork_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    upwork_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Job details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Budget/Rate
    budget_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # hourly, fixed
    budget_amount: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    budget_min: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    budget_max: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Skills
    skills_required: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    experience_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    project_length: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Client info
    client_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {rating, location, hire_rate, total_spent, member_since}

    # Vector embedding
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    # Full job posting data (from "View job posting" link)
    full_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachment_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachment_metadata: Mapped[Optional[List[dict]]] = mapped_column(JSONB, nullable=True)
    # [{filename, content_type, size, extraction_status, error}]

    # Analysis results (cached)
    match_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    analysis: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {skill_matches, missing_skills, strengths, concerns, deal_breaker_warnings}

    # Source tracking
    is_saved: Mapped[bool] = mapped_column(default=False, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # "extension" | "saved" | "search"
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    posted_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    applications: Mapped[List["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )
    cover_letters: Mapped[List["CoverLetter"]] = relationship(
        "CoverLetter", back_populates="job", cascade="all, delete-orphan"
    )
    screening_answers: Mapped[List["ScreeningAnswer"]] = relationship(
        "ScreeningAnswer", back_populates="job"
    )
    proposals: Mapped[List["Proposal"]] = relationship(
        "Proposal", back_populates="job"
    )

    __table_args__ = (
        Index("ix_jobs_user_upwork", "user_id", "upwork_job_id", unique=True),
        Index(
            "ix_jobs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
