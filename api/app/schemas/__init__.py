"""Pydantic schemas for UpApply API."""
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    TokenPayload,
    UserResponse,
)
from app.schemas.profile import (
    Skill,
    WorkHistoryEntry,
    EducationEntry,
    ProfileIdentity,
    ProfileGoals,
    ProfilePreferences,
    ProfileDealbreakers,
    ProfileCommunication,
    ProfileStrengths,
    ProfilePricing,
    ProfileAvailability,
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
    ResumeImportRequest,
    ResumeImportResponse,
)
from app.schemas.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryBulkImport,
)
from app.schemas.job import (
    ClientInfo,
    JobCreate,
    JobResponse,
    SkillMatch,
    JobAnalysisRequest,
    JobAnalysisResponse,
    CoverLetterGenerateRequest,
    CoverLetterResponse,
    CoverLetterRegenerateRequest,
)
from app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationOutcome,
    ApplicationResponse,
    ApplicationStats,
)
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    AnalyticsDashboard,
)

__all__ = [
    # Auth
    "UserRegister",
    "UserLogin",
    "Token",
    "TokenPayload",
    "UserResponse",
    # Profile
    "Skill",
    "WorkHistoryEntry",
    "EducationEntry",
    "ProfileIdentity",
    "ProfileGoals",
    "ProfilePreferences",
    "ProfileDealbreakers",
    "ProfileCommunication",
    "ProfileStrengths",
    "ProfilePricing",
    "ProfileAvailability",
    "ProfileCreate",
    "ProfileUpdate",
    "ProfileResponse",
    "ResumeImportRequest",
    "ResumeImportResponse",
    # Memory
    "MemoryCreate",
    "MemoryUpdate",
    "MemoryResponse",
    "MemorySearchRequest",
    "MemorySearchResult",
    "MemoryBulkImport",
    # Job
    "ClientInfo",
    "JobCreate",
    "JobResponse",
    "SkillMatch",
    "JobAnalysisRequest",
    "JobAnalysisResponse",
    "CoverLetterGenerateRequest",
    "CoverLetterResponse",
    "CoverLetterRegenerateRequest",
    # Application
    "ApplicationCreate",
    "ApplicationUpdate",
    "ApplicationOutcome",
    "ApplicationResponse",
    "ApplicationStats",
    # Feedback
    "FeedbackCreate",
    "FeedbackResponse",
    "AnalyticsDashboard",
]
