"""UserGuardrailConfig — per-user hard limits for Level 5 autonomous operation."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserGuardrailConfig(Base):
    """Hard limits that constrain the Level 5 autonomous agent.

    These are user-configurable safety rails. The agent will STOP and alert
    when any limit is reached — it never bypasses guardrails regardless of
    autonomy level.

    Defaults are conservative: 5 proposals/day, 20 connects reserve, no bid cap.
    """

    __tablename__ = "user_guardrail_configs"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Master switch — set to False to pause all autonomous activity
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Proposal volume cap (per calendar day UTC)
    max_proposals_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Minimum connects to keep in reserve (agent won't spend below this)
    min_connects_reserve: Mapped[int] = mapped_column(Integer, nullable=False, default=20)

    # Bid caps (None = no cap)
    max_bid_hourly: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    max_bid_fixed: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Minimum score the agent will consider for autonomous submission (higher than global threshold)
    min_score_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)

    # Optional quiet window (UTC hours) — agent skips runs within this window
    pause_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pause_end_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Connects tracking
    connects_balance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    connects_balance_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notification preferences
    digest_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="guardrail_config")
