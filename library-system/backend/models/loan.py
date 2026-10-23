import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class LoanStatus(str, enum.Enum):
    ACTIVE = "active"
    RETURNED = "returned"
    OVERDUE = "overdue"
    LOST = "lost"


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class FineStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    WAIVED = "waived"


class Loan(Base, TimestampMixin):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    copy_id: Mapped[int | None] = mapped_column(ForeignKey("book_copies.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    borrowed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, native_enum=False), default=LoanStatus.ACTIVE
    )
    renewed_count: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    book: Mapped["Book"] = relationship("Book", back_populates="loans")
    copy: Mapped["BookCopy | None"] = relationship("BookCopy", back_populates="loans")
    member: Mapped["User"] = relationship(
        "User", back_populates="loans", foreign_keys=[member_id]
    )
    issued_by: Mapped["User | None"] = relationship("User", foreign_keys=[issued_by_id])
    fines: Mapped[list["Fine"]] = relationship("Fine", back_populates="loan")


class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, native_enum=False), default=ReservationStatus.PENDING
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    book: Mapped["Book"] = relationship("Book", back_populates="reservations")
    member: Mapped["User"] = relationship("User", back_populates="reservations")


class Fine(Base, TimestampMixin):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="Overdue book")
    status: Mapped[FineStatus] = mapped_column(
        Enum(FineStatus, native_enum=False), default=FineStatus.UNPAID
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waived_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    loan: Mapped["Loan | None"] = relationship("Loan", back_populates="fines")
    member: Mapped["User"] = relationship(
        "User", back_populates="fines", foreign_keys=[member_id]
    )
