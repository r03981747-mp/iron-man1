from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.payment import PaymentStatus, PaymentType, SubscriptionStatus


class PaymentIntentCreate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    payment_type: PaymentType = PaymentType.FINE
    description: Optional[str] = None
    fine_ids: List[int] = Field(default_factory=list)
    event_id: Optional[int] = None
    currency: str = "USD"


class FineCheckoutCreate(BaseModel):
    fine_ids: List[int] = Field(min_length=1)
    description: Optional[str] = None


class PaymentIntentOut(BaseModel):
    payment_id: int
    amount: float
    currency: str
    status: PaymentStatus
    client_secret: Optional[str] = None
    mock: bool = True
    message: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    amount: float
    currency: str
    payment_type: PaymentType
    status: PaymentStatus
    description: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    member_name: Optional[str] = None


class SubscriptionCreate(BaseModel):
    tier: str = Field(pattern="^(basic|student|premium|family)$")
    payment_method_id: Optional[str] = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    tier: str
    status: SubscriptionStatus
    amount: float
    currency: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool
    created_at: datetime


class CheckoutOut(BaseModel):
    url: Optional[str] = None
    session_id: Optional[str] = None
    mock: bool = True
    message: str
