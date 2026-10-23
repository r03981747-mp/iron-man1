from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    branch_id: Optional[int] = None
    start_time: datetime
    end_time: datetime
    capacity: int = Field(default=50, ge=1)
    ticket_price: float = Field(default=0, ge=0)
    image_url: Optional[str] = None
    is_published: bool = True


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    branch_id: Optional[int] = None
    start_time: datetime
    end_time: datetime
    capacity: int
    ticket_price: float
    image_url: Optional[str] = None
    is_published: bool
    registered_count: int = 0


class EventRegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    member_id: int
    status: str
    created_at: datetime
    member_name: Optional[str] = None


class EventListOut(BaseModel):
    items: List[EventOut]
    total: int
