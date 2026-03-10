"""User and UserProfile models."""
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text, Integer, Numeric, Date, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """User account for authentication."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    memories: Mapped[List["Memory"]] = relationship(
        "Memory", back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[List["Application"]] = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    screening_answers: Mapped[List["ScreeningAnswer"]] = relationship(
        "ScreeningAnswer", back_populates="user", cascade="all, delete-orphan"
    )
    proposals: Mapped[List["Proposal"]] = relationship(
        "Proposal", back_populates="user", cascade="all, delete-orphan"
    )
    search_queries: Mapped[List["SearchQuery"]] = relationship(
        "SearchQuery", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    """Extended user profile with preferences and settings."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Identity
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    professional_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    headline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Resume data (parsed)
    resume_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skills: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # [{name, level, years}]
    work_history: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    education: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    certifications: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    portfolio_links: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Goals & Aspirations
    career_goals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ideal_project_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skills_to_highlight: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    skills_to_develop: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Project Preferences
    preferred_project_types: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    preferred_industries: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    preferred_team_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    preferred_client_types: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    project_duration_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Deal Breakers & Avoidances
    avoid_keywords: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    avoid_industries: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    minimum_budget: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    minimum_hourly_rate: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    red_flag_patterns: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Communication & Style
    tone_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    communication_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_time_expectation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    working_hours_preference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_closing: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # e.g. "Best regards,\nChris"

    # Per-user cover letter credential routing — job-type → anchor guidance + always_include list
    proposal_anchors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Unique Value Propositions
    unique_strengths: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    success_stories: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    client_testimonial_themes: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Pricing Strategy
    hourly_rate_min: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    hourly_rate_max: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    hourly_rate_preferred: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    fixed_price_minimum: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    pricing_flexibility: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Availability
    hours_per_week_available: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    availability_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    currently_accepting_work: Mapped[bool] = mapped_column(Boolean, default=True)

    # Setup tracking
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    setup_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")


# Import these at the bottom to avoid circular imports
from app.models.memory import Memory
from app.models.job import Job
from app.models.application import Application
from app.models.screening_answer import ScreeningAnswer
from app.models.proposal import Proposal
from app.models.search_query import SearchQuery
