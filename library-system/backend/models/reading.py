import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class ShelfStatus(str, enum.Enum):
    """The three simple shelves readers expect from a modern library app."""

    WANT_TO_READ = "want_to_read"
    READING = "reading"
    FINISHED = "finished"


class ReadingShelf(Base, TimestampMixin):
    """A member's personal relationship with one catalog title.

    A single row per (member, book) keeps the model small while letting the UI
    move a title between "want to read", "reading" and "finished". Progress is
    stored separately so a reader can keep a percentage without needing a
    second table.
    """

    __tablename__ = "reading_shelves"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_reading_shelf_user_book"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_reading_shelf_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    status: Mapped[ShelfStatus] = mapped_column(
        Enum(ShelfStatus, native_enum=False),
        default=ShelfStatus.WANT_TO_READ,
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", back_populates="shelves")
    book: Mapped["Book"] = relationship("Book", back_populates="shelf_entries")
