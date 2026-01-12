"""API v1 router aggregating all routes."""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.profile import router as profile_router
from app.api.v1.memories import router as memories_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.applications import router as applications_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.screening_answers import router as screening_answers_router
from app.api.v1.proposals import router as proposals_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(profile_router, prefix="/profile", tags=["Profile"])
router.include_router(memories_router, prefix="/memories", tags=["Memories"])
router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
router.include_router(applications_router, prefix="/applications", tags=["Applications"])
router.include_router(feedback_router, prefix="/feedback", tags=["Feedback"])
router.include_router(screening_answers_router, prefix="/screening-answers", tags=["Screening Answers"])
router.include_router(proposals_router, prefix="/proposals", tags=["Proposals"])
