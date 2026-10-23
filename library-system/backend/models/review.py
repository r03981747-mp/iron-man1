from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base
from models.base import TimestampMixin


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("book_id", "member_id", name="uq_review_book_member"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    book: Mapped["Book"] = relationship("Book", back_populates="reviews")
    member: Mapped["User"] = relationship("User", back_populates="reviews")
