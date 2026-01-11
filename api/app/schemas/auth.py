"""Authentication schemas."""
from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: str  # user id
    exp: int


class UserResponse(BaseModel):
    """Schema for user info response."""

    id: str
    email: str
    is_active: bool
    is_verified: bool
    has_profile: bool = False

    model_config = {"from_attributes": True}
