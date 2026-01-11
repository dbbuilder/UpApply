"""Profile endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserProfile
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
    ProfileGoals,
    ProfilePreferences,
    ProfileDealbreakers,
    ProfilePricing,
    ResumeImportRequest,
    ResumeImportResponse,
)
from app.services.resume_parser import parse_resume

router = APIRouter()


async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Get or create user profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        await db.flush()

    return profile


@router.get("", response_model=ProfileResponse)
async def get_profile(profile: UserProfile = Depends(get_user_profile)):
    """Get current user's profile."""
    return profile


@router.put("", response_model=ProfileResponse)
async def update_profile(
    profile_data: ProfileUpdate,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile (full update)."""
    update_data = profile_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return profile


@router.put("/goals", response_model=ProfileResponse)
async def update_goals(
    goals: ProfileGoals,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update profile goals section."""
    update_data = goals.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return profile


@router.put("/preferences", response_model=ProfileResponse)
async def update_preferences(
    preferences: ProfilePreferences,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update profile preferences section."""
    update_data = preferences.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return profile


@router.put("/dealbreakers", response_model=ProfileResponse)
async def update_dealbreakers(
    dealbreakers: ProfileDealbreakers,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update profile deal breakers section."""
    update_data = dealbreakers.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return profile


@router.put("/pricing", response_model=ProfileResponse)
async def update_pricing(
    pricing: ProfilePricing,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update profile pricing section."""
    update_data = pricing.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return profile


@router.post("/import-resume", response_model=ResumeImportResponse)
async def import_resume(
    request: ResumeImportRequest,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Parse resume and extract profile data and memories."""
    # Parse resume using AI
    parsed = await parse_resume(request.resume_text)

    # Store raw resume text
    profile.resume_text = request.resume_text

    # Update profile with parsed data
    if parsed.get("full_name"):
        profile.full_name = parsed["full_name"]
    if parsed.get("professional_title"):
        profile.professional_title = parsed["professional_title"]
    if parsed.get("bio"):
        profile.bio = parsed["bio"]
    if parsed.get("skills"):
        profile.skills = parsed["skills"]
    if parsed.get("work_history"):
        profile.work_history = parsed["work_history"]
    if parsed.get("education"):
        profile.education = parsed["education"]
    if parsed.get("certifications"):
        profile.certifications = parsed["certifications"]

    await db.commit()
    await db.refresh(profile)

    return ResumeImportResponse(
        full_name=parsed.get("full_name"),
        professional_title=parsed.get("professional_title"),
        bio=parsed.get("bio"),
        skills=parsed.get("skills"),
        work_history=parsed.get("work_history"),
        education=parsed.get("education"),
        certifications=parsed.get("certifications"),
        extracted_memories=parsed.get("memories", []),
    )


@router.post("/complete-setup", response_model=ProfileResponse)
async def complete_setup(
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Mark profile setup as complete."""
    profile.setup_completed = True
    profile.setup_step = None

    await db.commit()
    await db.refresh(profile)

    return profile


@router.put("/setup-step/{step}", response_model=ProfileResponse)
async def update_setup_step(
    step: int,
    profile: UserProfile = Depends(get_user_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update current setup wizard step."""
    if step < 1 or step > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step must be between 1 and 6",
        )

    profile.setup_step = step

    await db.commit()
    await db.refresh(profile)

    return profile
