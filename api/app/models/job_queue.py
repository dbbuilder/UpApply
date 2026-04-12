"""JobQueue model — agent-discovered jobs awaiting user review."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from decimal import Decimal
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.search_query import SearchQuery


class JobQueueItem(Base):
    """A job the agent discovered and queued for user review.

    Status flow: suggested → approved | rejected | applied | expired
    """

    __tablename__ = "job_queue"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Job identity
    upwork_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Job metadata
    skills: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True, default=list)
    budget_amount: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    budget_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Agent scoring
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chips: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True, default=list)

    # Status / lifecycle
    # suggested | approved | rejected | applied | expired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="suggested")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    source_query_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("search_queries.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Draft cover letter (generated when job is approved at Level 3+)
    # draft_status: none | generating | ready | sent
    draft_cover_letter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="none")
    draft_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Submission tracking (recorded when user confirms auto-fill)
    bid_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    connects_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Post-submit monitoring (background script updates these)
    upwork_proposal_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    last_status_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # none | viewed | responded | invited | declined
    client_response_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    client_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="job_queue_items")
    source_query: Mapped[Optional["SearchQuery"]] = relationship("SearchQuery")

    __table_args__ = (
        UniqueConstraint("user_id", "upwork_url", name="uq_job_queue_user_url"),
        Index("ix_job_queue_user_status", "user_id", "status"),
    )
