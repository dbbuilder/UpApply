"""JobReview model for scored job user ratings."""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Float, Integer, Index, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobReview(Base):
    __tablename__ = "job_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    upwork_job_url: Mapped[str] = mapped_column(String(500), nullable=False)
    upwork_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str] = mapped_column(String(500), nullable=False)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chips: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    budget_amount: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    budget_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    user_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'upwork_job_url', name='uq_job_review_user_url'),
    )
