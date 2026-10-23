from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.loan import FineStatus, LoanStatus, ReservationStatus


class LoanCreate(BaseModel):
    book_id: int
    member_id: Optional[int] = None  # staff only; defaults to current user
    copy_id: Optional[int] = None
    days: Optional[int] = Field(default=None, ge=1, le=90)


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    copy_id: Optional[int] = None
    member_id: int
    branch_id: Optional[int] = None
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime] = None
    status: LoanStatus
    renewed_count: int
    fine_amount: float

    book_title: Optional[str] = None
    member_name: Optional[str] = None
    copy_barcode: Optional[str] = None
    days_overdue: int = 0


class LoanListOut(BaseModel):
    items: List[LoanOut]
    total: int


class ReturnOut(BaseModel):
    loan: LoanOut
    fine_amount: float
    days_overdue: int
    message: str


class ReservationCreate(BaseModel):
    book_id: int
    member_id: Optional[int] = None


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    member_id: int
    branch_id: Optional[int] = None
    reserved_at: datetime
    expires_at: Optional[datetime] = None
    status: ReservationStatus
    book_title: Optional[str] = None
    member_name: Optional[str] = None


class FineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loan_id: Optional[int] = None
    member_id: int
    amount: float
    reason: str
    status: FineStatus
    paid_at: Optional[datetime] = None
    created_at: datetime
    member_name: Optional[str] = None
    book_title: Optional[str] = None


class FineAction(BaseModel):
    reason: Optional[str] = None
