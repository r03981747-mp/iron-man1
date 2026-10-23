import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class PaymentType(str, enum.Enum):
    FINE = "fine"
    MEMBERSHIP = "membership"
    EVENT = "event"
    PURCHASE = "purchase"
    DONATION = "donation"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class SubscriptionStatus(str, enum.Enum):
    INCOMPLETE = "incomplete"
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, native_enum=False), default=PaymentType.FINE
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING
    )
    description: Mapped[str | None] = mapped_column(Text)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member: Mapped["User"] = relationship("User", back_populates="payments")


class MembershipSubscription(Base, TimestampMixin):
    __tablename__ = "membership_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    tier: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False),
        default=SubscriptionStatus.ACTIVE,
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)

    member: Mapped["User"] = relationship("User")
