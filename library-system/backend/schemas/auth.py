from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.user import MembershipTier, UserRole


# ----------------------------- Auth ---------------------------------------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    date_of_birth: Optional[date] = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    membership_tier: MembershipTier
    library_card_number: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    reading_goal: int = 12


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    avatar_url: Optional[str] = None
    reading_goal: Optional[int] = Field(default=None, ge=1, le=365)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class MembershipUpdate(BaseModel):
    tier: MembershipTier


class StaffUserCreate(UserCreate):
    role: UserRole = UserRole.LIBRARIAN
