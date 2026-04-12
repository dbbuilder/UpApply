"""GlobalSignalPool — anonymized cross-user outcome signals for collaborative learning."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GlobalSignalPool(Base):
    """One row per anonymized outcome signal contributed to the platform.

    Privacy guarantees:
    - No user_id, no email, no proposal text is stored
    - skill_hash is SHA-256 of sorted, normalized skill names only
    - outcome_code is a coarse category (no job title, no client info)
    - edit_distance_pct is a float [0.0, 1.0] — no text content

    Used for:
    - Cold-start: new user with matching skill_hash inherits median score_threshold
    - Score calibration: score_at_submission vs outcome_code correlation
    - Generation quality: edit_distance_pct trends → which skill buckets rewrite more
    """

    __tablename__ = "global_signal_pool"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    skill_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_code: Mapped[str] = mapped_column(String(20), nullable=False)
    score_at_submission: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    edit_distance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_signal_pool_skill_outcome", "skill_hash", "outcome_code"),
    )
