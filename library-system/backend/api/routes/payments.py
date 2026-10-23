from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user, staff_required
from config.settings import settings
from database.session import get_db
from models.event import EventRegistration, RegistrationStatus
from models.loan import Fine, FineStatus
from models.payment import (
    MembershipSubscription,
    Payment,
    PaymentStatus,
    PaymentType,
    SubscriptionStatus,
)
from models.user import MembershipTier, User, UserRole
from schemas.payment import (
    CheckoutOut,
    FineCheckoutCreate,
    PaymentIntentCreate,
    PaymentIntentOut,
    PaymentOut,
    SubscriptionCreate,
    SubscriptionOut,
)
from utils.audit import record_audit
from utils.datetime_utils import utcnow

try:  # pragma: no cover - optional dependency in some environments
    import stripe
except ImportError:  # pragma: no cover
    stripe = None

router = APIRouter(prefix="/payments", tags=["Payments"])


def _configure_stripe() -> bool:
    if stripe is None or not settings.STRIPE_SECRET_KEY:
        return False
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return True


def _payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        member_id=payment.member_id,
        amount=float(payment.amount),
        currency=payment.currency,
        payment_type=payment.payment_type,
        status=payment.status,
        description=payment.description,
        stripe_payment_intent_id=payment.stripe_payment_intent_id,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
        member_name=payment.member.full_name if payment.member else None,
    )


def _unpaid_fines(db: Session, member_id: int, fine_ids: list[int]) -> list[Fine]:
    """Validate that every requested fine belongs to the member and is unpaid."""
    requested = list(dict.fromkeys(fine_ids))
    if not requested:
        raise HTTPException(status_code=400, detail="Choose at least one unpaid fine")
    fines = db.scalars(
        select(Fine).where(
            Fine.id.in_(requested),
            Fine.member_id == member_id,
            Fine.status == FineStatus.UNPAID,
        )
    ).all()
    if len(fines) != len(requested):
        raise HTTPException(
            status_code=400,
            detail="One or more fines were not found or are already settled",
        )
    return fines


def _settle_payment(
    db: Session,
    payment: Payment,
    *,
    actor_id: int | None = None,
    channel: str = "api",
) -> None:
    """Mark a payment (and its linked fines) settled exactly once."""
    if payment.status == PaymentStatus.SUCCEEDED:
        return

    now = utcnow()
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = now
    fine_ids = (payment.meta or {}).get("fine_ids", [])
    for fine in db.scalars(select(Fine).where(Fine.id.in_(fine_ids))).all():
        if fine.status == FineStatus.UNPAID:
            fine.status = FineStatus.PAID
            fine.paid_at = now

    record_audit(
        db,
        action="payment.succeeded",
        user_id=actor_id or payment.member_id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "type": payment.payment_type.value,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "fine_ids": fine_ids,
            "channel": channel,
        },
    )


def _activate_subscription(
    db: Session,
    subscription: MembershipSubscription,
    *,
    stripe_subscription_id: str | None = None,
    channel: str = "stripe",
) -> None:
    """Activate a membership subscription idempotently."""
    was_active = subscription.status == SubscriptionStatus.ACTIVE
    now = utcnow()
    subscription.status = SubscriptionStatus.ACTIVE
    if stripe_subscription_id:
        subscription.stripe_subscription_id = stripe_subscription_id
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    member = db.get(User, subscription.member_id)
    if member:
        member.membership_tier = MembershipTier(subscription.tier)
    if not was_active:
        record_audit(
            db,
            action="membership.activated",
            user_id=subscription.member_id,
            entity_type="subscription",
            entity_id=subscription.id,
            details={"tier": subscription.tier, "channel": channel},
        )


def _record_membership_payment(
    db: Session,
    subscription: MembershipSubscription,
    session_data: dict,
    *,
    channel: str,
) -> None:
    """Record the first paid invoice for a hosted membership checkout once."""
    session_id = session_data.get("id")
    if not session_id:
        return
    existing = db.scalar(
        select(Payment).where(Payment.stripe_checkout_session_id == session_id)
    )
    if existing:
        return
    amount = session_data.get("amount_total")
    amount_value = float(amount) / 100 if amount is not None else float(subscription.amount)
    if amount_value <= 0:
        return
    payment = Payment(
        member_id=subscription.member_id,
        amount=amount_value,
        currency=(session_data.get("currency") or subscription.currency).upper(),
        payment_type=PaymentType.MEMBERSHIP,
        status=PaymentStatus.SUCCEEDED,
        description=f"{subscription.tier.title()} membership (Stripe Checkout)",
        stripe_checkout_session_id=session_id,
        meta={"subscription_id": subscription.id},
        paid_at=utcnow(),
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        action="payment.succeeded",
        user_id=subscription.member_id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "type": payment.payment_type.value,
            "amount": amount_value,
            "currency": payment.currency,
            "subscription_id": subscription.id,
            "channel": channel,
        },
    )


def _checkout_urls() -> tuple[str, str]:
    base_url = settings.APP_BASE_URL.rstrip("/")
    return (
        f"{base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        f"{base_url}/?checkout=cancelled",
    )


@router.post("/intent", response_model=PaymentIntentOut)
def create_payment_intent(
    payload: PaymentIntentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentIntentOut:
    amount = payload.amount
    fine_ids: list[int] = []

    if payload.payment_type == PaymentType.FINE:
        if payload.fine_ids:
            fines = db.scalars(
                select(Fine).where(
                    Fine.id.in_(payload.fine_ids),
                    Fine.member_id == current_user.id,
                    Fine.status == FineStatus.UNPAID,
                )
            ).all()
            if len(fines) != len(payload.fine_ids):
                raise HTTPException(
                    status_code=400,
                    detail="One or more fines were not found or are already settled",
                )
            amount = float(sum(float(f.amount) for f in fines))
            fine_ids = [f.id for f in fines]
        if not amount:
            raise HTTPException(
                status_code=400, detail="Provide a fine to pay or a payment amount"
            )
    elif payload.payment_type == PaymentType.MEMBERSHIP:
        price = settings.membership_prices.get(current_user.membership_tier.value, 0)
        amount = amount or price
        if not amount:
            raise HTTPException(
                status_code=400,
                detail="Your current membership is free; use the subscribe endpoint",
            )
    elif not amount:
        raise HTTPException(status_code=400, detail="Payment amount is required")

    payment = Payment(
        member_id=current_user.id,
        amount=amount,
        currency=payload.currency or settings.DEFAULT_CURRENCY,
        payment_type=payload.payment_type,
        description=payload.description,
        meta={"fine_ids": fine_ids, "event_id": payload.event_id},
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    db.flush()

    client_secret = None
    mock = True
    if _configure_stripe():
        mock = False
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(round(amount * 100)),
                currency=(payload.currency or settings.DEFAULT_CURRENCY).lower(),
                metadata={
                    "payment_id": str(payment.id),
                    "member_id": str(current_user.id),
                    "type": payload.payment_type.value,
                },
                automatic_payment_methods={"enabled": True},
            )
            payment.stripe_payment_intent_id = intent.id
            client_secret = intent.client_secret
            message = "Stripe payment intent created. Confirm it with the client secret."
        except Exception as exc:  # pragma: no cover - network dependent
            db.rollback()
            raise HTTPException(
                status_code=502, detail=f"Stripe error: {exc}"
            ) from exc
    else:
        now = utcnow()
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = now
        if fine_ids:
            fines = db.scalars(select(Fine).where(Fine.id.in_(fine_ids))).all()
            for fine in fines:
                fine.status = FineStatus.PAID
                fine.paid_at = now
        message = (
            "Development mode: payment captured instantly because Stripe keys "
            "are not configured."
        )

    record_audit(
        db,
        action=(
            "payment.succeeded"
            if payment.status == PaymentStatus.SUCCEEDED
            else "payment.created"
        ),
        user_id=current_user.id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "type": payment.payment_type.value,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "fine_ids": fine_ids,
            "mock": mock,
        },
    )
    db.commit()
    db.refresh(payment)
    return PaymentIntentOut(
        payment_id=payment.id,
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status,
        client_secret=client_secret,
        mock=mock,
        message=message,
    )


@router.post("/fines/checkout", response_model=CheckoutOut)
def checkout_fines(
    payload: FineCheckoutCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    """Pay fines through Stripe Checkout, or settle instantly in development."""
    fines = _unpaid_fines(db, current_user.id, payload.fine_ids)
    amount = float(sum(float(fine.amount) for fine in fines))
    description = payload.description or (
        f"Library fine payment ({len(fines)} item{'s' if len(fines) != 1 else ''})"
    )
    payment = Payment(
        member_id=current_user.id,
        amount=amount,
        currency=settings.DEFAULT_CURRENCY,
        payment_type=PaymentType.FINE,
        description=description,
        meta={"fine_ids": [fine.id for fine in fines]},
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    db.flush()

    if _configure_stripe():
        success_url, cancel_url = _checkout_urls()
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=current_user.email,
                line_items=[
                    {
                        "price_data": {
                            "currency": settings.DEFAULT_CURRENCY.lower(),
                            "product_data": {"name": description},
                            "unit_amount": int(round(amount * 100)),
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "payment_id": str(payment.id),
                    "member_id": str(current_user.id),
                    "type": PaymentType.FINE.value,
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            payment.stripe_checkout_session_id = session.id
            record_audit(
                db,
                action="payment.created",
                user_id=current_user.id,
                entity_type="payment",
                entity_id=payment.id,
                details={
                    "type": payment.payment_type.value,
                    "amount": amount,
                    "currency": payment.currency,
                    "fine_ids": [fine.id for fine in fines],
                    "channel": "stripe_checkout",
                },
            )
            db.commit()
            return CheckoutOut(
                url=session.url,
                session_id=session.id,
                mock=False,
                message="Redirecting to Stripe Checkout.",
            )
        except Exception as exc:  # pragma: no cover - network dependent
            db.rollback()
            raise HTTPException(
                status_code=502, detail=f"Stripe error: {exc}"
            ) from exc

    _settle_payment(
        db,
        payment,
        actor_id=current_user.id,
        channel="development",
    )
    db.commit()
    return CheckoutOut(
        mock=True,
        message=(
            "Development mode: payment captured instantly because Stripe keys "
            "are not configured."
        ),
    )


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentOut:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.member_id != current_user.id and current_user.role == UserRole.MEMBER:
        raise HTTPException(status_code=403, detail="Not allowed to confirm this payment")
    if payment.status == PaymentStatus.SUCCEEDED:
        return _payment_out(payment)

    if _configure_stripe() and payment.stripe_payment_intent_id:
        try:
            intent = stripe.PaymentIntent.retrieve(payment.stripe_payment_intent_id)
            if intent.status != "succeeded":
                raise HTTPException(
                    status_code=400,
                    detail=f"Stripe payment is '{intent.status}', not succeeded yet",
                )
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    _settle_payment(
        db,
        payment,
        actor_id=current_user.id,
        channel="intent_confirm",
    )
    db.commit()
    db.refresh(payment)
    return _payment_out(payment)


@router.get("", response_model=list[PaymentOut])
def list_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PaymentOut]:
    stmt = select(Payment).order_by(Payment.created_at.desc())
    if current_user.role == UserRole.MEMBER:
        stmt = stmt.where(Payment.member_id == current_user.id)
    payments = db.scalars(stmt).all()
    return [_payment_out(p) for p in payments]


@router.post("/subscribe", response_model=CheckoutOut)
def subscribe(
    payload: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    tier = MembershipTier(payload.tier)
    price = settings.membership_prices.get(tier.value, 0)

    if price <= 0:
        current_user.membership_tier = MembershipTier.BASIC
        record_audit(
            db,
            action="membership.changed",
            user_id=current_user.id,
            entity_type="member",
            entity_id=current_user.id,
            details={"tier": MembershipTier.BASIC.value, "price": 0},
        )
        db.commit()
        return CheckoutOut(
            mock=True,
            message="Switched to the free Basic membership.",
        )

    subscription = MembershipSubscription(
        member_id=current_user.id,
        tier=tier.value,
        status=SubscriptionStatus.INCOMPLETE,
        amount=price,
        currency=settings.DEFAULT_CURRENCY,
    )
    db.add(subscription)
    db.flush()

    if _configure_stripe():
        success_url, cancel_url = _checkout_urls()
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                customer_email=current_user.email,
                line_items=[
                    {
                        "price_data": {
                            "currency": settings.DEFAULT_CURRENCY.lower(),
                            "product_data": {
                                "name": f"{tier.value.title()} Library Membership"
                            },
                            "unit_amount": int(round(price * 100)),
                            "recurring": {"interval": "month"},
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "subscription_id": str(subscription.id),
                    "member_id": str(current_user.id),
                    "tier": tier.value,
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            record_audit(
                db,
                action="membership.checkout_started",
                user_id=current_user.id,
                entity_type="subscription",
                entity_id=subscription.id,
                details={"tier": tier.value, "amount": price},
            )
            db.commit()
            return CheckoutOut(
                url=session.url,
                session_id=session.id,
                mock=False,
                message="Redirecting to Stripe Checkout.",
            )
        except Exception as exc:  # pragma: no cover
            db.rollback()
            raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    # Development mode: activate immediately.
    now = utcnow()
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    current_user.membership_tier = tier
    payment = Payment(
        member_id=current_user.id,
        amount=price,
        payment_type=PaymentType.MEMBERSHIP,
        status=PaymentStatus.SUCCEEDED,
        description=f"{tier.value.title()} membership (monthly)",
        paid_at=now,
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        action="membership.activated",
        user_id=current_user.id,
        entity_type="subscription",
        entity_id=subscription.id,
        details={
            "tier": tier.value,
            "amount": price,
            "payment_id": payment.id,
            "mock": True,
        },
    )
    db.commit()
    return CheckoutOut(
        mock=True,
        message=(
            f"{tier.value.title()} membership activated in development mode "
            "(no Stripe key configured)."
        ),
    )


@router.get("/subscriptions/me", response_model=list[SubscriptionOut])
def my_subscriptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subs = db.scalars(
        select(MembershipSubscription)
        .where(MembershipSubscription.member_id == current_user.id)
        .order_by(MembershipSubscription.created_at.desc())
    ).all()
    return [
        SubscriptionOut(
            id=s.id,
            member_id=s.member_id,
            tier=s.tier,
            status=s.status,
            amount=float(s.amount),
            currency=s.currency,
            current_period_start=s.current_period_start,
            current_period_end=s.current_period_end,
            cancel_at_period_end=s.cancel_at_period_end,
            created_at=s.created_at,
        )
        for s in subs
    ]


@router.post("/checkout/{session_id}/confirm", response_model=CheckoutOut)
def confirm_checkout_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    """Confirm a hosted Checkout return when a webhook is not configured locally."""
    if not _configure_stripe():
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        data = session.to_dict()
    except Exception as exc:  # pragma: no cover - network dependent
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    meta = data.get("metadata") or {}
    member_id = int(meta.get("member_id") or 0)
    if member_id != current_user.id and current_user.role == UserRole.MEMBER:
        raise HTTPException(status_code=403, detail="Not allowed to confirm this checkout")

    subscription_id = meta.get("subscription_id")
    if subscription_id:
        if data.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Checkout is not complete yet")
        subscription = db.get(MembershipSubscription, int(subscription_id))
        if subscription is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        _activate_subscription(
            db,
            subscription,
            stripe_subscription_id=data.get("subscription"),
            channel="stripe_checkout_return",
        )
        _record_membership_payment(
            db,
            subscription,
            data,
            channel="stripe_checkout_return",
        )
        db.commit()
        return CheckoutOut(
            mock=False,
            message="Membership activated. Welcome to the library!",
        )

    payment_id = meta.get("payment_id")
    if payment_id:
        if data.get("payment_status") != "paid":
            raise HTTPException(status_code=400, detail="Payment is not complete yet")
        payment = db.get(Payment, int(payment_id))
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        _settle_payment(
            db,
            payment,
            actor_id=current_user.id,
            channel="stripe_checkout_return",
        )
        db.commit()
        return CheckoutOut(
            mock=False,
            message="Payment confirmed — thank you!",
        )

    raise HTTPException(status_code=404, detail="Unknown checkout session")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    if stripe is None:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    _configure_stripe()

    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}") from exc
    else:
        import json

        event = json.loads(payload or b"{}")

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        meta = data.get("metadata") or {}
        sub_id = meta.get("subscription_id")
        payment_id = meta.get("payment_id")
        if sub_id:
            subscription = db.get(MembershipSubscription, int(sub_id))
            if subscription:
                _activate_subscription(
                    db,
                    subscription,
                    stripe_subscription_id=data.get("subscription") or data.get("id"),
                    channel="stripe_webhook",
                )
                _record_membership_payment(
                    db,
                    subscription,
                    data,
                    channel="stripe_webhook",
                )
                db.commit()
        elif payment_id:
            payment = db.get(Payment, int(payment_id))
            if payment:
                _settle_payment(
                    db,
                    payment,
                    channel="stripe_checkout_webhook",
                )
                db.commit()

    elif event_type == "payment_intent.succeeded":
        intent_id = data.get("id")
        payment = db.scalar(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
        if payment:
            _settle_payment(
                db,
                payment,
                channel="stripe_webhook",
            )
            db.commit()

    elif event_type == "invoice.paid":
        stripe_sub_id = data.get("subscription")
        subscription = db.scalar(
            select(MembershipSubscription).where(
                MembershipSubscription.stripe_subscription_id == stripe_sub_id
            )
        )
        if subscription:
            _activate_subscription(
                db,
                subscription,
                stripe_subscription_id=stripe_sub_id,
                channel="stripe_invoice",
            )
            # Renewal already has an active subscription; keep the audit distinct.
            record_audit(
                db,
                action="membership.renewed",
                user_id=subscription.member_id,
                entity_type="subscription",
                entity_id=subscription.id,
                details={"tier": subscription.tier, "channel": "stripe_invoice"},
            )
            db.commit()

    elif event_type == "checkout.session.expired":
        meta = data.get("metadata") or {}
        payment_id = meta.get("payment_id")
        subscription_id = meta.get("subscription_id")
        if payment_id:
            payment = db.get(Payment, int(payment_id))
            if payment and payment.status == PaymentStatus.PENDING:
                payment.status = PaymentStatus.FAILED
                event_id = meta.get("event_id") or (payment.meta or {}).get("event_id")
                if event_id:
                    registration = db.scalar(
                        select(EventRegistration).where(
                            EventRegistration.event_id == int(event_id),
                            EventRegistration.member_id == payment.member_id,
                            EventRegistration.status == RegistrationStatus.REGISTERED,
                        )
                    )
                    if registration:
                        registration.status = RegistrationStatus.CANCELLED
                record_audit(
                    db,
                    action="payment.failed",
                    user_id=payment.member_id,
                    entity_type="payment",
                    entity_id=payment.id,
                    details={
                        "type": payment.payment_type.value,
                        "amount": float(payment.amount),
                        "channel": "stripe_checkout_expired",
                    },
                )
                db.commit()
        elif subscription_id:
            subscription = db.get(MembershipSubscription, int(subscription_id))
            if subscription and subscription.status == SubscriptionStatus.INCOMPLETE:
                subscription.status = SubscriptionStatus.CANCELED
                record_audit(
                    db,
                    action="membership.cancelled",
                    user_id=subscription.member_id,
                    entity_type="subscription",
                    entity_id=subscription.id,
                    details={"tier": subscription.tier, "channel": "checkout_expired"},
                )
                db.commit()

    return {"received": True}
