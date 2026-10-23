from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoomBookingCreate(BaseModel):
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = Field(default=None, max_length=500)


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    branch_id: Optional[int] = None
    room_type: str
    capacity: int
    hourly_rate: float
    description: Optional[str] = None
    amenities: List[str] = Field(default_factory=list)
    is_active: bool
    branch_name: Optional[str] = None
    upcoming_bookings: int = 0


class RoomBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    member_id: int
    start_time: datetime
    end_time: datetime
    status: str
    notes: Optional[str] = None
    total_amount: float = 0
    created_at: datetime
    room_name: Optional[str] = None
    member_name: Optional[str] = None
