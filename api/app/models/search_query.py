"""SearchQuery model for tracking saved search queries and their performance."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job


class SearchQuery(Base):
    """A saved Upwork search query with cumulative performance statistics."""

    __tablename__ = "search_queries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The search query string (q= parameter value)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional extra Upwork URL parameters, e.g. "contractor_tier=2,3&proposals=0-4"
    url_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Origin: manual | ai_generated | seeded | imported
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    # Optional FK to the parent query this was derived from
    parent_query_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("search_queries.id", ondelete="SET NULL"),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Cumulative performance stats (updated by /record-run) ---
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Number of jobs that scored >= 70 across all runs
    high_score_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="search_queries")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="search_query")
    children: Mapped[list["SearchQuery"]] = relationship(
        "SearchQuery",
        foreign_keys=[parent_query_id],
        back_populates="parent",
    )
    parent: Mapped[Optional["SearchQuery"]] = relationship(
        "SearchQuery",
        foreign_keys=[parent_query_id],
        back_populates="children",
        remote_side=[id],
    )

    __table_args__ = (
        Index("ix_search_queries_user_id", "user_id"),
    )

    @property
    def performance_score(self) -> float:
        """Composite score rewarding high-quality, high-volume results.

        Formula:
          quality_ratio = high_score_count / total_jobs_found
          volume_factor = min(1.0, total_jobs_found / 10)   # saturates at 10 jobs
          score         = avg_match_score × quality_ratio × volume_factor

        A query returning 3 jobs all at 90 beats one returning 30 jobs at avg 40.
        Returns 0.0 if the query has never been run or found no jobs.
        """
        if self.run_count == 0 or self.total_jobs_found == 0:
            return 0.0
        quality_ratio = self.high_score_count / self.total_jobs_found
        volume_factor = min(1.0, self.total_jobs_found / 10)
        return round((self.avg_match_score or 0.0) * quality_ratio * volume_factor, 1)

    @property
    def is_stale(self) -> bool:
        """True if never run or last run more than 24 hours ago."""
        if self.last_run_at is None:
            return True
        from datetime import timezone
        age = datetime.now(timezone.utc) - self.last_run_at
        return age.total_seconds() > 86_400

    @property
    def is_low_performer(self) -> bool:
        """True if the query has run ≥3 times and shows poor results."""
        if self.run_count < 3:
            return False
        return (self.avg_match_score or 0.0) < 35 or self.total_jobs_found < 2
