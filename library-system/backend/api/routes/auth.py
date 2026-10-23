import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from database.session import get_db
from models.user import MembershipTier, User, UserRole
from schemas.auth import (
    PasswordChange,
    Token,
    TokenRefresh,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)
from utils.audit import record_audit
from utils.datetime_utils import utcnow

router = APIRouter(prefix="/auth", tags=["Authentication"])


def generate_card_number(db: Session) -> str:
    for _ in range(20):
        number = f"LIB-{utcnow().year}-{random.randint(0, 999999):06d}"
        exists = db.scalar(select(User).where(User.library_card_number == number))
        if not exists:
            return number
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a library card number",
    )


def issue_tokens(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        address=payload.address,
        date_of_birth=payload.date_of_birth,
        role=UserRole.MEMBER,
        membership_tier=MembershipTier.BASIC,
        library_card_number=generate_card_number(db),
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="auth.registered",
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return issue_tokens(user)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    user.last_login = utcnow()
    record_audit(
        db,
        action="auth.login",
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "role": user.role.value},
    )
    db.commit()
    return issue_tokens(user)


@router.post("/refresh", response_model=Token)
def refresh(payload: TokenRefresh, db: Session = Depends(get_db)) -> Token:
    data = decode_token(payload.refresh_token, expected_type="refresh")
    user = db.get(User, int(data["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    return issue_tokens(user)


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # JWTs are stateless. The client discards both tokens; this endpoint exists
    # so clients have a single, auditable place to end a session.
    record_audit(
        db,
        action="auth.logout",
        user_id=current_user.id,
        entity_type="user",
        entity_id=current_user.id,
    )
    db.commit()
    return {"message": f"Goodbye, {current_user.full_name.split()[0]}! Logged out."}


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(payload.new_password)
    record_audit(
        db,
        action="auth.password_changed",
        user_id=current_user.id,
        entity_type="user",
        entity_id=current_user.id,
    )
    db.commit()
    return {"message": "Password updated successfully"}
