from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user, staff_required
from config.settings import settings
from database.session import get_db
from models.event import Event, EventRegistration, RegistrationStatus
from models.payment import Payment, PaymentStatus, PaymentType
from models.user import User, UserRole
from schemas.event import (
    EventCreate,
    EventListOut,
    EventOut,
    EventRegistrationOut,
)
from utils.audit import record_audit
from utils.datetime_utils import utcnow

router = APIRouter(prefix="/events", tags=["Events"])


def _event_out(event: Event, registered: int = 0) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        branch_id=event.branch_id,
        start_time=event.start_time,
        end_time=event.end_time,
        capacity=event.capacity,
        ticket_price=float(event.ticket_price),
        image_url=event.image_url,
        is_published=event.is_published,
        registered_count=registered,
    )


def _registered_count(db: Session, event_id: int) -> int:
    return (
        db.scalar(
            select(func.count(EventRegistration.id)).where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == RegistrationStatus.REGISTERED,
            )
        )
        or 0
    )


@router.get("", response_model=EventListOut)
def list_events(
    db: Session = Depends(get_db),
    upcoming_only: bool = True,
) -> EventListOut:
    stmt = select(Event).where(Event.is_published.is_(True))
    if upcoming_only:
        stmt = stmt.where(Event.end_time >= utcnow())
    events = db.scalars(stmt.order_by(Event.start_time)).all()
    items = [_event_out(e, _registered_count(db, e.id)) for e in events]
    return EventListOut(items=items, total=len(items))


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_out(event, _registered_count(db, event_id))


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> EventOut:
    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status_code=400, detail="Event end time must be after the start time"
        )
    event = Event(
        **payload.model_dump(),
        created_by_id=current_user.id,
    )
    db.add(event)
    db.flush()
    record_audit(
        db,
        action="event.created",
        user_id=current_user.id,
        entity_type="event",
        entity_id=event.id,
        details={
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "capacity": event.capacity,
            "ticket_price": float(event.ticket_price),
        },
    )
    db.commit()
    db.refresh(event)
    return _event_out(event, 0)


@router.put("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    payload: EventCreate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump().items():
        setattr(event, field, value)
    record_audit(
        db,
        action="event.updated",
        user_id=current_user.id,
        entity_type="event",
        entity_id=event.id,
        details={"title": event.title, "capacity": event.capacity},
    )
    db.commit()
    db.refresh(event)
    return _event_out(event, _registered_count(db, event_id))


@router.post("/{event_id}/register")
def register_for_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(Event, event_id)
    if event is None or not event.is_published:
        raise HTTPException(status_code=404, detail="Event not found")

    existing = db.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.member_id == current_user.id,
            EventRegistration.status == RegistrationStatus.REGISTERED,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="You are already registered for this event"
        )

    if _registered_count(db, event_id) >= event.capacity:
        raise HTTPException(status_code=400, detail="This event is fully booked")

    payment: Payment | None = None
    client_secret = None
    mock = True
    message = "Registration confirmed."

    if float(event.ticket_price) > 0:
        payment = Payment(
            member_id=current_user.id,
            amount=event.ticket_price,
            currency=settings.DEFAULT_CURRENCY,
            payment_type=PaymentType.EVENT,
            description=f"Ticket: {event.title}",
            meta={"event_id": event.id},
            status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.flush()

        from api.routes.payments import _configure_stripe
        import stripe as _stripe

        if _configure_stripe():
            mock = False
            base_url = settings.APP_BASE_URL.rstrip("/")
            session = _stripe.checkout.Session.create(
                mode="payment",
                customer_email=current_user.email,
                line_items=[
                    {
                        "price_data": {
                            "currency": settings.DEFAULT_CURRENCY.lower(),
                            "product_data": {"name": f"Ticket: {event.title}"},
                            "unit_amount": int(round(float(event.ticket_price) * 100)),
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "payment_id": str(payment.id),
                    "event_id": str(event.id),
                    "member_id": str(current_user.id),
                },
                success_url=(
                    f"{base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
                ),
                cancel_url=f"{base_url}/?checkout=cancelled",
            )
            payment.stripe_checkout_session_id = session.id
            client_secret = session.url
            message = "Complete payment to finish your registration."
        else:
            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = utcnow()
            message = "Free preview mode: ticket paid successfully."

    registration = EventRegistration(
        event_id=event.id,
        member_id=current_user.id,
        status=RegistrationStatus.REGISTERED,
        payment_id=payment.id if payment else None,
    )
    db.add(registration)
    db.flush()
    record_audit(
        db,
        action="event.registered",
        user_id=current_user.id,
        entity_type="event",
        entity_id=event.id,
        details={
            "title": event.title,
            "member": current_user.full_name,
            "registration_id": registration.id,
            "ticket_price": float(event.ticket_price),
            "payment_id": payment.id if payment else None,
        },
    )
    db.commit()
    db.refresh(registration)

    return {
        "registration": EventRegistrationOut(
            id=registration.id,
            event_id=registration.event_id,
            member_id=registration.member_id,
            status=registration.status.value,
            created_at=registration.created_at,
            member_name=current_user.full_name,
        ).model_dump(mode="json"),
        "payment_id": payment.id if payment else None,
        "checkout_url": client_secret,
        "mock": mock,
        "message": message,
    }


@router.delete("/{event_id}/register", status_code=status.HTTP_204_NO_CONTENT)
def cancel_registration(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    registration = db.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.member_id == current_user.id,
            EventRegistration.status == RegistrationStatus.REGISTERED,
        )
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Registration not found")
    registration.status = RegistrationStatus.CANCELLED
    record_audit(
        db,
        action="event.registration_cancelled",
        user_id=current_user.id,
        entity_type="event",
        entity_id=event_id,
        details={"member": current_user.full_name},
    )
    db.commit()


@router.get(
    "/{event_id}/registrations", response_model=list[EventRegistrationOut]
)
def list_registrations(
    event_id: int,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> list[EventRegistrationOut]:
    registrations = db.scalars(
        select(EventRegistration)
        .where(EventRegistration.event_id == event_id)
        .options(selectinload(EventRegistration.member))
        .order_by(EventRegistration.created_at)
    ).all()
    return [
        EventRegistrationOut(
            id=r.id,
            event_id=r.event_id,
            member_id=r.member_id,
            status=r.status.value,
            created_at=r.created_at,
            member_name=r.member.full_name if r.member else None,
        )
        for r in registrations
    ]
