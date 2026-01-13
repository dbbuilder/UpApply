"""Beta feedback model for tester feedback collection."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Text, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BetaFeedback(Base):
    """Model for collecting beta tester feedback."""

    __tablename__ = "beta_feedback"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Feedback type: bug, feature_request, usability, general
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # The feedback content
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional contact info
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Context information
    page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extension_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    browser_info: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # User ID if logged in (optional)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
