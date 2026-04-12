"""UserAutonomyProfile — tracks per-user agent autonomy level and progression stats."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserAutonomyProfile(Base):
    """Stores a user's current autonomy level and the metrics used to advance/downgrade it.

    Level progression:
      1 Observer  → 2 Suggester (10 jobs shown)
      2 Suggester → 3 Drafter   (60% approval, 20 suggestions)
      3 Drafter   → 4 Assisted  (avg edit distance ≤15%, 10 proposals drafted)
      4 Assisted  → 5 Autonomous (25% response rate, 20 submissions)
      5 Autonomous → 6 Optimizing (manual opt-in only)
    """

    __tablename__ = "user_autonomy_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Current autonomy level (1–6)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Progression counters
    suggestions_shown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggestions_approved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposals_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposals_responded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposals_hired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Derived quality metrics
    avg_edit_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Governance
    last_evaluated: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=55.0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="autonomy_profile")

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def approval_rate(self) -> float:
        """Fraction of shown suggestions the user approved."""
        if self.suggestions_shown == 0:
            return 0.0
        return self.suggestions_approved / self.suggestions_shown

    @property
    def response_rate(self) -> float:
        """Fraction of submitted proposals that received a client response."""
        if self.proposals_submitted == 0:
            return 0.0
        return self.proposals_responded / self.proposals_submitted
