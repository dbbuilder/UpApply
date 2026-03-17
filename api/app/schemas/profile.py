"""User profile schemas."""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class Skill(BaseModel):
    """Schema for a skill entry."""

    name: str
    level: str = "intermediate"  # beginner, intermediate, expert
    years: Optional[int] = None


class WorkHistoryEntry(BaseModel):
    """Schema for work history entry."""

    title: str
    company: str
    duration: Optional[str] = None
    description: Optional[str] = None
    highlights: Optional[List[str]] = None


class EducationEntry(BaseModel):
    """Schema for education entry."""

    degree: str
    institution: str
    year: Optional[int] = None
    relevant_courses: Optional[List[str]] = None


# Identity section
class ProfileIdentity(BaseModel):
    """Schema for profile identity section."""

    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None


# Goals section
class ProfileGoals(BaseModel):
    """Schema for profile goals section."""

    career_goals: Optional[str] = None
    ideal_project_description: Optional[str] = None
    skills_to_highlight: Optional[List[str]] = None
    skills_to_develop: Optional[List[str]] = None


# Preferences section
class ProfilePreferences(BaseModel):
    """Schema for profile preferences section."""

    preferred_project_types: Optional[List[str]] = None
    preferred_industries: Optional[List[str]] = None
    preferred_team_size: Optional[str] = None
    preferred_client_types: Optional[List[str]] = None
    project_duration_preference: Optional[str] = None


# Deal breakers section
class ProfileDealbreakers(BaseModel):
    """Schema for profile deal breakers section."""

    avoid_keywords: Optional[List[str]] = None
    avoid_industries: Optional[List[str]] = None
    minimum_budget: Optional[float] = None
    minimum_hourly_rate: Optional[float] = None
    red_flag_patterns: Optional[List[str]] = None


# Communication section
class ProfileCommunication(BaseModel):
    """Schema for profile communication preferences."""

    tone_preference: Optional[str] = None  # professional, casual, technical, friendly
    communication_style: Optional[str] = None
    response_time_expectation: Optional[str] = None
    timezone: Optional[str] = None
    working_hours_preference: Optional[str] = None
    preferred_closing: Optional[str] = None  # e.g. "Best regards,\nChris"


# Unique strengths section
class ProfileStrengths(BaseModel):
    """Schema for profile unique strengths."""

    unique_strengths: Optional[List[str]] = None
    success_stories: Optional[List[str]] = None
    client_testimonial_themes: Optional[List[str]] = None


# Pricing section
class ProfilePricing(BaseModel):
    """Schema for profile pricing strategy."""

    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    hourly_rate_preferred: Optional[float] = None
    fixed_price_minimum: Optional[float] = None
    pricing_flexibility: Optional[str] = None


# Availability section
class ProfileAvailability(BaseModel):
    """Schema for profile availability."""

    hours_per_week_available: Optional[int] = None
    availability_start_date: Optional[date] = None
    currently_accepting_work: bool = True


# Full profile create/update
class ProfileCreate(BaseModel):
    """Schema for creating a profile."""

    # Identity
    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None

    # Resume data
    resume_text: Optional[str] = None
    skills: Optional[List[Skill]] = None
    work_history: Optional[List[WorkHistoryEntry]] = None
    education: Optional[List[EducationEntry]] = None
    certifications: Optional[List[str]] = None
    portfolio_links: Optional[List[str]] = None

    # Goals
    career_goals: Optional[str] = None
    ideal_project_description: Optional[str] = None
    skills_to_highlight: Optional[List[str]] = None
    skills_to_develop: Optional[List[str]] = None

    # Preferences
    preferred_project_types: Optional[List[str]] = None
    preferred_industries: Optional[List[str]] = None
    preferred_team_size: Optional[str] = None
    preferred_client_types: Optional[List[str]] = None
    project_duration_preference: Optional[str] = None

    # Deal breakers
    avoid_keywords: Optional[List[str]] = None
    avoid_industries: Optional[List[str]] = None
    minimum_budget: Optional[float] = None
    minimum_hourly_rate: Optional[float] = None
    red_flag_patterns: Optional[List[str]] = None

    # Communication
    tone_preference: Optional[str] = None
    communication_style: Optional[str] = None
    response_time_expectation: Optional[str] = None
    timezone: Optional[str] = None
    working_hours_preference: Optional[str] = None
    preferred_closing: Optional[str] = None

    # Strengths
    unique_strengths: Optional[List[str]] = None
    success_stories: Optional[List[str]] = None
    client_testimonial_themes: Optional[List[str]] = None

    # Pricing
    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    hourly_rate_preferred: Optional[float] = None
    fixed_price_minimum: Optional[float] = None
    pricing_flexibility: Optional[str] = None

    # Availability
    hours_per_week_available: Optional[int] = None
    availability_start_date: Optional[date] = None
    currently_accepting_work: bool = True

    # Per-user cover letter credential routing
    proposal_anchors: Optional[Dict[str, Any]] = None


class ProfileUpdate(ProfileCreate):
    """Schema for updating a profile (same as create, all optional)."""

    setup_completed: Optional[bool] = None
    setup_step: Optional[int] = None


class ProfileResponse(BaseModel):
    """Schema for profile response."""

    id: str
    user_id: str

    # Identity
    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None

    # Resume data
    skills: Optional[List[Skill]] = None
    work_history: Optional[List[WorkHistoryEntry]] = None
    education: Optional[List[EducationEntry]] = None
    certifications: Optional[List[str]] = None
    portfolio_links: Optional[List[str]] = None

    # Goals
    career_goals: Optional[str] = None
    ideal_project_description: Optional[str] = None
    skills_to_highlight: Optional[List[str]] = None
    skills_to_develop: Optional[List[str]] = None

    # Preferences
    preferred_project_types: Optional[List[str]] = None
    preferred_industries: Optional[List[str]] = None
    preferred_team_size: Optional[str] = None
    preferred_client_types: Optional[List[str]] = None
    project_duration_preference: Optional[str] = None

    # Deal breakers
    avoid_keywords: Optional[List[str]] = None
    avoid_industries: Optional[List[str]] = None
    minimum_budget: Optional[float] = None
    minimum_hourly_rate: Optional[float] = None
    red_flag_patterns: Optional[List[str]] = None

    # Communication
    tone_preference: Optional[str] = None
    communication_style: Optional[str] = None
    timezone: Optional[str] = None
    preferred_closing: Optional[str] = None

    # Strengths
    unique_strengths: Optional[List[str]] = None

    # Pricing
    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    hourly_rate_preferred: Optional[float] = None

    # Availability
    hours_per_week_available: Optional[int] = None
    currently_accepting_work: bool = True

    # Per-user cover letter credential routing
    proposal_anchors: Optional[Dict[str, Any]] = None

    # Setup status
    setup_completed: bool = False
    setup_step: Optional[int] = None

    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeImportRequest(BaseModel):
    """Schema for resume import request."""

    resume_text: str


class ResumeImportResponse(BaseModel):
    """Schema for resume import response."""

    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[Skill]] = None
    work_history: Optional[List[WorkHistoryEntry]] = None
    education: Optional[List[EducationEntry]] = None
    certifications: Optional[List[str]] = None
    extracted_memories: Optional[List[dict]] = None  # Memories extracted from resume


# Profile optimization schemas

class ProfileDimension(BaseModel):
    """A single scored dimension of the Upwork profile."""

    name: str
    score: int  # 0-100
    status: str  # 'good' | 'warning' | 'critical'
    summary: str
    detail: str


class ProfileRecommendation(BaseModel):
    """A prioritized improvement recommendation."""

    priority: str  # 'critical' | 'high' | 'medium' | 'low'
    dimension: str
    title: str
    problem: str
    action: str  # specific actionable instruction


class May2026Item(BaseModel):
    """Single item in the May 2026 specialized-profiles checklist."""

    item: str
    done: bool
    note: str


class ProfileOptimizeResponse(BaseModel):
    """Full AI-generated profile optimization report."""

    overall_score: int
    dimensions: List[ProfileDimension]
    recommendations: List[ProfileRecommendation]
    suggested_title: Optional[str] = None
    suggested_overview_hook: Optional[str] = None  # first ~250 chars rewrite
    suggested_skills: Optional[List[str]] = None
    may_2026_checklist: List[May2026Item]
    cached: bool = False
    cached_at: Optional[str] = None
