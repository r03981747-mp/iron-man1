from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user
from database.session import get_db
from models.library import Book
from models.reading import ReadingShelf, ShelfStatus
from models.user import User
from schemas.book import BookOut
from schemas.reading import (
    ReadingGoalOut,
    ShelfCollectionOut,
    ShelfEntryOut,
    ShelfGoalUpdate,
    ShelfUpdate,
)
from utils.audit import record_audit
from utils.datetime_utils import ensure_naive_utc, utcnow

router = APIRouter(prefix="/shelves", tags=["Reading shelves"])

_SHELF_LOADERS = (
    selectinload(ReadingShelf.book).selectinload(Book.author),
    selectinload(ReadingShelf.book).selectinload(Book.publisher),
    selectinload(ReadingShelf.book).selectinload(Book.category),
)


def _goal_for(db: Session, user: User) -> ReadingGoalOut:
    """Calculate the annual goal from the reader's finished shelf.

    The date is deliberately calculated from the shelf record rather than from
    loan history: a reader may finish a book they already own, and that still
    counts toward their personal challenge.
    """
    now = utcnow()
    year_start = datetime(now.year, 1, 1)
    finished = db.scalars(
        select(ReadingShelf).where(
            ReadingShelf.user_id == user.id,
            ReadingShelf.status == ShelfStatus.FINISHED,
        )
    ).all()
    count = 0
    for entry in finished:
        stamped = ensure_naive_utc(entry.finished_at or entry.updated_at or entry.created_at)
        if stamped is not None and stamped >= year_start:
            count += 1
    target = max(1, int(user.reading_goal or 12))
    return ReadingGoalOut(
        target=target,
        finished=count,
        year=now.year,
        percent=min(100, round((count / target) * 100)),
    )


def _counts(items: list[ReadingShelf]) -> dict[str, int]:
    counts = {status.value: 0 for status in ShelfStatus}
    for item in items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return counts


def _entry_out(entry: ReadingShelf) -> ShelfEntryOut:
    return ShelfEntryOut(
        book=BookOut.model_validate(entry.book),
        status=entry.status,
        progress=entry.progress,
        started_at=entry.started_at,
        finished_at=entry.finished_at,
        updated_at=entry.updated_at,
    )


@router.get("/me", response_model=ShelfCollectionOut)
def my_shelves(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: ShelfStatus | None = Query(default=None, alias="status"),
) -> ShelfCollectionOut:
    entries = db.scalars(
        select(ReadingShelf)
        .where(ReadingShelf.user_id == current_user.id)
        .options(*_SHELF_LOADERS)
        .order_by(ReadingShelf.updated_at.desc(), ReadingShelf.id.desc())
    ).unique().all()
    visible = [entry for entry in entries if status_filter is None or entry.status == status_filter]
    return ShelfCollectionOut(
        items=[_entry_out(entry) for entry in visible],
        counts=_counts(entries),
        goal=_goal_for(db, current_user),
    )


@router.put("/me/goal", response_model=ReadingGoalOut)
def update_goal(
    payload: ShelfGoalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReadingGoalOut:
    previous = current_user.reading_goal
    current_user.reading_goal = payload.target
    record_audit(
        db,
        action="reading_goal.updated",
        user_id=current_user.id,
        entity_type="user",
        entity_id=current_user.id,
        details={"previous": previous, "target": payload.target},
    )
    db.commit()
    db.refresh(current_user)
    return _goal_for(db, current_user)


@router.put("/me/{book_id}", response_model=ShelfEntryOut)
def save_to_shelf(
    book_id: int,
    payload: ShelfUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShelfEntryOut:
    book = db.get(Book, book_id)
    if book is None or not book.is_active:
        raise HTTPException(status_code=404, detail="Book not found")

    entry = db.scalar(
        select(ReadingShelf)
        .where(
            ReadingShelf.user_id == current_user.id,
            ReadingShelf.book_id == book_id,
        )
        .options(*_SHELF_LOADERS)
    )
    previous = entry.status.value if entry else None
    now = utcnow()

    if entry is None:
        entry = ReadingShelf(
            user_id=current_user.id,
            book_id=book_id,
            status=payload.status,
            progress=0,
        )
        db.add(entry)

    entry.status = payload.status
    if payload.status == ShelfStatus.WANT_TO_READ:
        entry.progress = 0
        entry.started_at = None
        entry.finished_at = None
    elif payload.status == ShelfStatus.READING:
        if payload.progress is not None:
            entry.progress = payload.progress
        elif previous != ShelfStatus.READING.value:
            entry.progress = 0
        entry.started_at = entry.started_at or now
        entry.finished_at = None
    else:  # finished
        entry.progress = 100
        entry.started_at = entry.started_at or now
        entry.finished_at = entry.finished_at or now

    db.flush()
    record_audit(
        db,
        action="shelf.updated",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book.id,
        details={
            "title": book.title,
            "shelf": entry.status.value,
            "previous": previous,
            "progress": entry.progress,
        },
    )
    db.commit()
    db.refresh(entry)
    return _entry_out(entry)


@router.delete("/me/{book_id}", status_code=status.HTTP_200_OK)
def remove_from_shelf(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    entry = db.scalar(
        select(ReadingShelf).where(
            ReadingShelf.user_id == current_user.id,
            ReadingShelf.book_id == book_id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="This book is not on your shelves")
    title = entry.book.title if entry.book else f"Book #{book_id}"
    db.delete(entry)
    record_audit(
        db,
        action="shelf.removed",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book_id,
        details={"title": title},
    )
    db.commit()
    return {"message": f"“{title}” removed from your shelves."}
