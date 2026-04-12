"""OutcomeEvent — records every user action for the agent feedback loop."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job_queue import JobQueueItem


class OutcomeEvent(Base):
    """One row per significant user/agent action.

    event_type values:
      suggested   — agent added job to queue (shown to user)
      approved    — user approved a suggestion
      rejected    — user passed on a suggestion
      submitted   — proposal submitted (future)
      responded   — client replied to proposal (future)
      hired       — user was hired (future)

    meta is a free-form JSON dict. Examples:
      {"rejection_reason": "budget too low"}
      {"edit_distance_pct": 12.4, "word_count_delta": -45}
    """

    __tablename__ = "outcome_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_queue_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("job_queue.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="outcome_events")
    job_queue_item: Mapped[Optional["JobQueueItem"]] = relationship("JobQueueItem")
