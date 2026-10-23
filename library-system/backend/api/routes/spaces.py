from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user
from database.session import get_db
from models.space import BookingStatus, Room, RoomBooking
from models.user import User, UserRole
from schemas.space import RoomBookingCreate, RoomBookingOut, RoomOut
from utils.audit import record_audit
from utils.datetime_utils import ensure_naive_utc, utcnow

router = APIRouter(prefix="/rooms", tags=["Spaces"])


def _is_staff(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.LIBRARIAN)


def _booking_out(booking: RoomBooking) -> RoomBookingOut:
    return RoomBookingOut(
        id=booking.id,
        room_id=booking.room_id,
        member_id=booking.member_id,
        start_time=booking.start_time,
        end_time=booking.end_time,
        status=booking.status.value,
        notes=booking.notes,
        total_amount=float(booking.total_amount or 0),
        created_at=booking.created_at,
        room_name=booking.room.name if booking.room else None,
        member_name=booking.member.full_name if booking.member else None,
    )


@router.get("", response_model=list[RoomOut])
def list_rooms(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RoomOut]:
    now = utcnow()
    rooms = db.scalars(
        select(Room)
        .options(selectinload(Room.branch))
        .where(Room.is_active.is_(True))
        .order_by(Room.id)
    ).all()
    counts = dict(
        db.execute(
            select(RoomBooking.room_id, func.count(RoomBooking.id))
            .where(
                RoomBooking.status == BookingStatus.CONFIRMED,
                RoomBooking.end_time >= now,
            )
            .group_by(RoomBooking.room_id)
        ).all()
    )
    return [
        RoomOut(
            id=room.id,
            name=room.name,
            branch_id=room.branch_id,
            room_type=room.room_type,
            capacity=room.capacity,
            hourly_rate=float(room.hourly_rate or 0),
            description=room.description,
            amenities=room.amenities or [],
            is_active=room.is_active,
            branch_name=room.branch.name if room.branch else None,
            upcoming_bookings=counts.get(room.id, 0),
        )
        for room in rooms
    ]


@router.get("/bookings", response_model=list[RoomBookingOut])
def list_room_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    upcoming_only: bool = Query(default=True),
) -> list[RoomBookingOut]:
    stmt = (
        select(RoomBooking)
        .options(selectinload(RoomBooking.room), selectinload(RoomBooking.member))
        .order_by(RoomBooking.start_time.asc())
    )
    if not _is_staff(current_user):
        stmt = stmt.where(RoomBooking.member_id == current_user.id)
    if upcoming_only:
        stmt = stmt.where(RoomBooking.end_time >= utcnow())
    bookings = db.scalars(stmt).all()
    return [_booking_out(booking) for booking in bookings]


@router.post(
    "/{room_id}/bookings",
    response_model=RoomBookingOut,
    status_code=status.HTTP_201_CREATED,
)
def book_room(
    room_id: int,
    payload: RoomBookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoomBookingOut:
    room = db.get(Room, room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=404, detail="Room not found")

    start = ensure_naive_utc(payload.start_time)
    end = ensure_naive_utc(payload.end_time)
    now = utcnow()
    if start < now - timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="Choose a start time in the future")
    if end <= start:
        raise HTTPException(status_code=400, detail="The end time must be after the start time")
    if end - start > timedelta(hours=4):
        raise HTTPException(status_code=400, detail="Rooms can be booked for up to 4 hours at a time")

    conflict = db.scalar(
        select(RoomBooking).where(
            RoomBooking.room_id == room.id,
            RoomBooking.status == BookingStatus.CONFIRMED,
            RoomBooking.start_time < end,
            RoomBooking.end_time > start,
        )
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail="That slot is already booked. Please choose another time.",
        )

    hours = Decimal(str((end - start).total_seconds())) / Decimal("3600")
    total = (Decimal(str(room.hourly_rate or 0)) * hours).quantize(Decimal("0.01"))
    booking = RoomBooking(
        room_id=room.id,
        member_id=current_user.id,
        start_time=start,
        end_time=end,
        status=BookingStatus.CONFIRMED,
        notes=payload.notes,
        total_amount=total,
    )
    db.add(booking)
    db.flush()
    record_audit(
        db,
        action="room.booked",
        user_id=current_user.id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={
            "room": room.name,
            "member": current_user.full_name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total": float(total),
        },
    )
    db.commit()
    db.refresh(booking)
    return _booking_out(booking)


@router.post("/bookings/{booking_id}/cancel", response_model=RoomBookingOut)
def cancel_room_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoomBookingOut:
    booking = db.scalar(
        select(RoomBooking)
        .options(selectinload(RoomBooking.room), selectinload(RoomBooking.member))
        .where(RoomBooking.id == booking_id)
    )
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.member_id != current_user.id and not _is_staff(current_user):
        raise HTTPException(status_code=403, detail="You cannot cancel this booking")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="This booking is no longer active")

    booking.status = BookingStatus.CANCELLED
    record_audit(
        db,
        action="room.booking_cancelled",
        user_id=current_user.id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={
            "room": booking.room.name if booking.room else None,
            "member": booking.member.full_name if booking.member else None,
        },
    )
    db.commit()
    db.refresh(booking)
    return _booking_out(booking)
