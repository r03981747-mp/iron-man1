from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.reading import ShelfStatus
from schemas.book import BookOut


class ShelfUpdate(BaseModel):
    status: ShelfStatus
    progress: Optional[int] = Field(default=None, ge=0, le=100)


class ShelfGoalUpdate(BaseModel):
    target: int = Field(ge=1, le=365)


class ShelfEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book: BookOut
    status: ShelfStatus
    progress: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime


class ReadingGoalOut(BaseModel):
    target: int
    finished: int
    year: int
    percent: int


class ShelfCollectionOut(BaseModel):
    items: list[ShelfEntryOut]
    counts: dict[str, int]
    goal: ReadingGoalOut
