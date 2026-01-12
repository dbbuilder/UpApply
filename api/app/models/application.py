"""Application model for tracking job applications and outcomes."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, String, Text, Numeric, Enum, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job
    from app.models.cover_letter import CoverLetter
    from app.models.feedback import Feedback


class ApplicationStatus(str, PyEnum):
    """Application status enum."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    VIEWED = "viewed"
    RESPONDED = "responded"
    INTERVIEWED = "interviewed"
    OFFERED = "offered"
    HIRED = "hired"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class Application(Base):
    """Track job applications and their outcomes."""

    __tablename__ = "applications"

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
    cover_letter_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("cover_letters.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Application details
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.DRAFT
    )
    bid_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Outcome tracking
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    earnings: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Timestamps
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_recorded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    cover_letter: Mapped[Optional["CoverLetter"]] = relationship(
        "CoverLetter", back_populates="application"
    )
    feedback: Mapped[Optional["Feedback"]] = relationship(
        "Feedback", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
