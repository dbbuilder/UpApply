"""CoverLetter model for generated cover letters."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Integer, Boolean, Numeric, Float, func, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job
    from app.models.application import Application


class CoverLetter(Base):
    """Generated cover letters for jobs."""

    __tablename__ = "cover_letters"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Generated content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Generation metadata
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Memories used for generation (for transparency and learning)
    memories_used: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Quality metrics
    ai_confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Submission tracking — captures what was actually sent and when
    submitted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    was_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)

    # Generation v2 traceability (migration 023) — what §3 learning scores against
    brief: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fact_ids_used: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(36)), nullable=True)
    voice_sample_ids: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(36)), nullable=True)
    verify_warnings: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Refine + learn loop (migration 024)
    refine_messages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    final_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_answers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edit_distance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    job: Mapped["Job"] = relationship("Job", back_populates="cover_letters")
    application: Mapped[Optional["Application"]] = relationship(
        "Application", back_populates="cover_letter"
    )
