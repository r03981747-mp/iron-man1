import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class BookFormat(str, enum.Enum):
    HARDCOVER = "hardcover"
    PAPERBACK = "paperback"
    EBOOK = "ebook"
    AUDIOBOOK = "audiobook"


class CopyStatus(str, enum.Enum):
    AVAILABLE = "available"
    ON_LOAN = "on_loan"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"
    LOST = "lost"


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    opening_hours: Mapped[dict | None] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    copies: Mapped[list["BookCopy"]] = relationship("BookCopy", back_populates="branch")


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(20))

    books: Mapped[list["Book"]] = relationship("Book", back_populates="category")


class Author(Base, TimestampMixin):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(500))

    books: Mapped[list["Book"]] = relationship("Book", back_populates="author")


class Publisher(Base, TimestampMixin):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))

    books: Mapped[list["Book"]] = relationship("Book", back_populates="publisher")


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    isbn: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("authors.id"))
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("publishers.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(50), default="English")
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    book_format: Mapped[BookFormat] = mapped_column(
        Enum(BookFormat, native_enum=False), default=BookFormat.HARDCOVER
    )
    total_copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    available_copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    replacement_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=25)
    digital_file_url: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    average_rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    author: Mapped["Author | None"] = relationship("Author", back_populates="books")
    publisher: Mapped["Publisher | None"] = relationship(
        "Publisher", back_populates="books"
    )
    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="books"
    )
    copies: Mapped[list["BookCopy"]] = relationship(
        "BookCopy", back_populates="book", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="book", cascade="all, delete-orphan"
    )
    loans: Mapped[list["Loan"]] = relationship("Loan", back_populates="book")
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="book"
    )
    shelf_entries: Mapped[list["ReadingShelf"]] = relationship(
        "ReadingShelf", back_populates="book", cascade="all, delete-orphan"
    )


class BookCopy(Base, TimestampMixin):
    __tablename__ = "book_copies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    barcode: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[CopyStatus] = mapped_column(
        Enum(CopyStatus, native_enum=False), default=CopyStatus.AVAILABLE
    )
    condition: Mapped[str] = mapped_column(String(50), default="good")
    shelf_location: Mapped[str | None] = mapped_column(String(100))
    acquired_date: Mapped[date | None] = mapped_column(Date, default=date.today)

    book: Mapped["Book"] = relationship("Book", back_populates="copies")
    branch: Mapped["Branch | None"] = relationship("Branch", back_populates="copies")
    loans: Mapped[list["Loan"]] = relationship("Loan", back_populates="copy")
