"""Feedback model for user feedback on generated content."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Integer, Boolean, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.application import Application
    from app.models.cover_letter import CoverLetter


class Feedback(Base):
    """User feedback on generated content and application outcomes."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    cover_letter_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cover_letters.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Feedback type
    feedback_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # thumbs_up, thumbs_down, edited, regenerated, outcome

    # Rating and comments
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Edit tracking
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Specific feedback
    was_helpful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    would_use_again: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    application: Mapped[Optional["Application"]] = relationship(
        "Application", back_populates="feedback"
    )
