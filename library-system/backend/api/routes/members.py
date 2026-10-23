from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.deps import admin_required, get_current_user, staff_required
from api.routes.auth import generate_card_number
from auth.security import hash_password
from database.session import get_db
from models.user import MembershipTier, User, UserRole
from schemas.auth import (
    MembershipUpdate,
    StaffUserCreate,
    UserOut,
    UserUpdate,
)
from utils.audit import record_audit

router = APIRouter(prefix="/members", tags=["Members"])


@router.get("", response_model=list[UserOut])
def list_members(
    db: Session = Depends(get_db),
    _: User = Depends(staff_required),
    q: str | None = Query(default=None),
    role: UserRole | None = None,
    tier: MembershipTier | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[User]:
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.library_card_number.ilike(like),
            )
        )
    if role:
        stmt = stmt.where(User.role == role)
    if tier:
        stmt = stmt.where(User.membership_tier == tier)
    stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: StaffUserCreate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> User:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email exists")
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
        date_of_birth=payload.date_of_birth,
        role=payload.role,
        library_card_number=generate_card_number(db),
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="member.created",
        user_id=current_user.id,
        entity_type="member",
        entity_id=user.id,
        details={
            "name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "card": user.library_card_number,
        },
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/stats/summary")
def member_summary(
    db: Session = Depends(get_db), _: User = Depends(staff_required)
) -> dict:
    total = db.scalar(select(func.count(User.id)).where(User.role == UserRole.MEMBER))
    active = db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.MEMBER, User.is_active.is_(True)
        )
    )
    by_tier = dict(
        db.execute(
            select(User.membership_tier, func.count(User.id))
            .where(User.role == UserRole.MEMBER)
            .group_by(User.membership_tier)
        ).all()
    )
    return {
        "total_members": total or 0,
        "active_members": active or 0,
        "by_tier": {str(k.value if hasattr(k, "value") else k): v for k, v in by_tier.items()},
    }


@router.get("/{member_id}", response_model=UserOut)
def get_member(
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if current_user.role == UserRole.MEMBER and current_user.id != member_id:
        raise HTTPException(status_code=403, detail="Not allowed to view this member")
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.put("/{member_id}", response_model=UserOut)
def update_member(
    member_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    is_staff = current_user.role in (UserRole.ADMIN, UserRole.LIBRARIAN)
    if not is_staff and current_user.id != member_id:
        raise HTTPException(status_code=403, detail="Not allowed to edit this member")
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(member, field, value)
    record_audit(
        db,
        action="member.updated",
        user_id=current_user.id,
        entity_type="member",
        entity_id=member.id,
        details={"name": member.full_name, "fields": sorted(updates)},
    )
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{member_id}/role", response_model=UserOut)
def change_role(
    member_id: int,
    role: UserRole,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> User:
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    previous = member.role.value
    member.role = role
    record_audit(
        db,
        action="member.role_changed",
        user_id=current_user.id,
        entity_type="member",
        entity_id=member.id,
        details={"name": member.full_name, "from": previous, "to": role.value},
    )
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{member_id}/membership", response_model=UserOut)
def change_membership(
    member_id: int,
    payload: MembershipUpdate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> User:
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    previous = member.membership_tier.value
    member.membership_tier = payload.tier
    record_audit(
        db,
        action="member.tier_changed",
        user_id=current_user.id,
        entity_type="member",
        entity_id=member.id,
        details={"name": member.full_name, "from": previous, "to": payload.tier.value},
    )
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{member_id}/deactivate", response_model=UserOut)
def toggle_active(
    member_id: int,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> User:
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    member.is_active = not member.is_active
    record_audit(
        db,
        action="member.activation_changed",
        user_id=current_user.id,
        entity_type="member",
        entity_id=member.id,
        details={
            "name": member.full_name,
            "email": member.email,
            "is_active": member.is_active,
        },
    )
    db.commit()
    db.refresh(member)
    return member

