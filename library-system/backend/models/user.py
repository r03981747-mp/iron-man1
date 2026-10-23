import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    LIBRARIAN = "librarian"
    MEMBER = "member"


class MembershipTier(str, enum.Enum):
    BASIC = "basic"
    STUDENT = "student"
    PREMIUM = "premium"
    FAMILY = "family"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.MEMBER, nullable=False
    )
    membership_tier: Mapped[MembershipTier] = mapped_column(
        Enum(MembershipTier, native_enum=False),
        default=MembershipTier.BASIC,
        nullable=False,
    )
    library_card_number: Mapped[str | None] = mapped_column(
        String(50), unique=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # A lightweight annual reading challenge. Progress is calculated from the
    # reader's "finished" shelf rather than stored separately, so the number is
    # always trustworthy even if a book is moved between shelves.
    reading_goal: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    loans: Mapped[list["Loan"]] = relationship(
        "Loan", back_populates="member", foreign_keys="Loan.member_id"
    )
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="member"
    )
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="member")
    fines: Mapped[list["Fine"]] = relationship(
        "Fine", back_populates="member", foreign_keys="Fine.member_id"
    )
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="member")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user"
    )
    event_registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="member"
    )
    shelves: Mapped[list["ReadingShelf"]] = relationship(
        "ReadingShelf", back_populates="user", cascade="all, delete-orphan"
    )
