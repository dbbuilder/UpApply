"""Authentication endpoints."""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.core.config import settings
from app.models.user import User, UserProfile
from app.schemas.auth import UserRegister, UserLogin, Token, UserResponse
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    try:
        email = user_data.email.lower().strip()
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create user
        logger.info(f"Creating user with email: {email}")
        user = User(
            email=email,
            hashed_password=hash_password(user_data.password),
        )
        db.add(user)
        await db.flush()
        logger.info(f"User created with id: {user.id}")

        # Create empty profile
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.commit()
        logger.info("Profile created and committed")

        # Generate token
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )

        return Token(access_token=access_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        )


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login and get access token."""
    # Find user (normalize email to lowercase)
    result = await db.execute(select(User).where(User.email == user_data.email.lower().strip()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    # Generate token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    return Token(access_token=access_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """Refresh access token."""
    access_token = create_access_token(
        data={"sub": str(current_user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user information."""
    # Check if user has a profile
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    # A profile is considered "complete" if setup_completed is True OR if the
    # profile has real data (name/title/goals/skills), which handles accounts
    # created before the wizard existed or where the final step was skipped.
    profile_has_data = (
        profile is not None and (
            profile.setup_completed
            or bool(profile.full_name)
            or bool(profile.professional_title)
            or bool(profile.career_goals)
            or bool(profile.skills)
        )
    )

    # Auto-heal: persist setup_completed so future calls don't re-check
    if profile is not None and not profile.setup_completed and profile_has_data:
        profile.setup_completed = True
        await db.commit()

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        has_profile=profile_has_data,
    )
