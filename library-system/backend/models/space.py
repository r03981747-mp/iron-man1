import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class BookingStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Room(Base, TimestampMixin):
    """A bookable library space such as a study room or recording studio."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    room_type: Mapped[str] = mapped_column(String(60), default="study")
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    hourly_rate: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    description: Mapped[str | None] = mapped_column(Text)
    amenities: Mapped[list | None] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)

    branch: Mapped["Branch | None"] = relationship("Branch")
    bookings: Mapped[list["RoomBooking"]] = relationship(
        "RoomBooking", back_populates="room", cascade="all, delete-orphan"
    )


class RoomBooking(Base, TimestampMixin):
    __tablename__ = "room_bookings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, native_enum=False), default=BookingStatus.CONFIRMED
    )
    notes: Mapped[str | None] = mapped_column(Text)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    room: Mapped["Room"] = relationship("Room", back_populates="bookings")
    member: Mapped["User"] = relationship("User")
