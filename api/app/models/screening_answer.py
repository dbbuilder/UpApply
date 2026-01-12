"""Screening answer model for storing Q&A from job applications."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, func, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job


class ScreeningAnswer(Base):
    """Store screening question answers for semantic search and reuse."""

    __tablename__ = "screening_answers"

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
    application_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Question and answer content
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Context for better matching
    question_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # experience, availability, rate, technical, general
    job_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    job_skills: Mapped[Optional[List[str]]] = mapped_column(
        Text, nullable=True
    )  # Comma-separated for simplicity

    # Vector embeddings for semantic search
    question_embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )
    answer_embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    # Outcome tracking (did this answer lead to success?)
    was_successful: Mapped[Optional[bool]] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="screening_answers")
    job: Mapped[Optional["Job"]] = relationship("Job", back_populates="screening_answers")

    __table_args__ = (
        Index(
            "ix_screening_answers_question_embedding_hnsw",
            "question_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"question_embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_screening_answers_answer_embedding_hnsw",
            "answer_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"answer_embedding": "vector_cosine_ops"},
        ),
    )
