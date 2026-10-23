import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class RegistrationStatus(str, enum.Enum):
    REGISTERED = "registered"
    CANCELLED = "cancelled"
    ATTENDED = "attended"


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=50)
    ticket_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    image_url: Mapped[str | None] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="event", cascade="all, delete-orphan"
    )


class EventRegistration(Base, TimestampMixin):
    __tablename__ = "event_registrations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, native_enum=False),
        default=RegistrationStatus.REGISTERED,
    )
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))

    event: Mapped["Event"] = relationship("Event", back_populates="registrations")
    member: Mapped["User"] = relationship("User", back_populates="event_registrations")
