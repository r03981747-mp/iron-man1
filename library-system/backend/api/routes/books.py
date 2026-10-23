import math
import random
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user, staff_required
from database.session import get_db
from models.library import (
    Author,
    Book,
    BookCopy,
    BookFormat,
    Branch,
    Category,
    CopyStatus,
    Publisher,
)
from models.review import Review
from models.user import User
from schemas.book import (
    BookCopyCreate,
    BookCopyOut,
    BookCreate,
    BookListOut,
    BookOut,
    BookUpdate,
    CatalogSuggestionOut,
    CatalogSuggestionRequest,
    ReviewCreate,
    ReviewOut,
)
from utils.audit import record_audit
from utils.datetime_utils import utcnow

router = APIRouter(tags=["Books"])

_BOOK_LOADERS = (
    selectinload(Book.author),
    selectinload(Book.publisher),
    selectinload(Book.category),
)

# Transparent keyword signals used by the catalog assistant. This is a local
# heuristic, not a hosted AI model: it suggests metadata the librarian can edit.
_CATEGORY_SIGNALS = {
    "Technology": (
        "artificial intelligence",
        "software",
        "computer",
        "algorithm",
        "data",
        "code",
        "machine",
        "programming",
        "cyber",
        "robot",
    ),
    "Science": (
        "physics",
        "biology",
        "space",
        "evolution",
        "brain",
        "science",
        "quantum",
        "cosmos",
        "climate",
        "nature",
    ),
    "History": (
        "history",
        "war",
        "empire",
        "ancient",
        "revolution",
        "civilisation",
        "civilization",
        "century",
    ),
    "Psychology": (
        "psychology",
        "mind",
        "habit",
        "behaviour",
        "behavior",
        "thinking",
        "emotion",
        "decision",
    ),
    "Biography": ("memoir", "biography", "autobiography", "life of", "portrait of"),
    "Fiction": ("novel", "story", "fiction", "love", "dystopian", "fantasy", "mystery"),
}
_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "book",
    "from",
    "into",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "with",
    "would",
    "your",
}


@router.post("/books/suggest", response_model=CatalogSuggestionOut)
def suggest_catalog_entry(
    payload: CatalogSuggestionRequest,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> CatalogSuggestionOut:
    """Suggest category, tags and a starter description from catalog keywords."""
    blob = " ".join(
        part for part in (payload.title, payload.author_name, payload.description) if part
    ).lower()
    categories = {
        category.name: category
        for category in db.scalars(select(Category).order_by(Category.id)).all()
    }

    best_name = None
    best_hits: list[str] = []
    for name, signals in _CATEGORY_SIGNALS.items():
        hits = [signal for signal in signals if signal in blob]
        if len(hits) > len(best_hits):
            best_name = name
            best_hits = hits
    if best_name not in categories:
        best_name = next(iter(categories), None)

    tags: list[str] = []
    if best_name:
        tags.append(best_name.lower())
    for word in re.findall(r"[a-z][a-z-]{3,}", blob):
        if word not in _STOPWORDS and word not in tags:
            tags.append(word)
    tags = tags[:6]

    author = f" by {payload.author_name}" if payload.author_name else ""
    category_label = best_name.lower() if best_name else "general"
    if payload.description and len(payload.description.strip()) >= 40:
        description = payload.description.strip()
    else:
        description = (
            f"{payload.title}{author} is a {category_label} title that explores "
            "ideas readers can borrow, discuss and discover at the library. "
            "Edit this starter description before publishing the catalogue record."
        )

    confidence = 82 if best_hits else 58
    if payload.description and len(payload.description.strip()) >= 40:
        confidence += 5
    rationale = (
        "Suggested from title, author and description keywords using a local "
        "heuristic. Review every field before saving; no external AI service is called."
    )
    return CatalogSuggestionOut(
        category_id=categories[best_name].id if best_name and best_name in categories else None,
        category=best_name,
        tags=tags,
        description=description,
        book_format=BookFormat.HARDCOVER,
        confidence=min(confidence, 94),
        rationale=rationale,
    )


@router.get("/books", response_model=BookListOut)
def list_books(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Search title, author, ISBN"),
    category_id: int | None = None,
    author_id: int | None = None,
    book_format: BookFormat | None = None,
    available_only: bool = False,
    sort: str = Query(default="newest", pattern="^(newest|title|rating|popular)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
) -> BookListOut:
    stmt = select(Book).where(Book.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(Author, Book.author_id == Author.id).where(
            or_(
                Book.title.ilike(like),
                Book.subtitle.ilike(like),
                Book.isbn.ilike(like),
                Author.name.ilike(like),
            )
        )
    if category_id:
        stmt = stmt.where(Book.category_id == category_id)
    if author_id:
        stmt = stmt.where(Book.author_id == author_id)
    if book_format:
        stmt = stmt.where(Book.book_format == book_format)
    if available_only:
        stmt = stmt.where(Book.available_copies > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sort == "title":
        stmt = stmt.order_by(Book.title.asc())
    elif sort == "rating":
        stmt = stmt.order_by(Book.average_rating.desc(), Book.review_count.desc())
    elif sort == "popular":
        stmt = stmt.order_by(Book.review_count.desc(), Book.average_rating.desc())
    else:
        stmt = stmt.order_by(Book.created_at.desc())

    stmt = (
        stmt.options(*_BOOK_LOADERS)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.scalars(stmt).unique().all()
    pages = max(1, math.ceil(total / page_size))
    return BookListOut(
        items=[BookOut.model_validate(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/books/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)) -> Book:
    book = db.scalar(
        select(Book).where(Book.id == book_id).options(*_BOOK_LOADERS)
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Book:
    data = payload.model_dump()
    data.pop("available_copies", None)
    total = max(0, int(data.pop("total_copies", 0) or 0))
    if data.get("isbn"):
        duplicate = db.scalar(select(Book).where(Book.isbn == data["isbn"]))
        if duplicate is not None:
            raise HTTPException(
                status_code=409, detail="A book with this ISBN already exists"
            )
    book = Book(**data, total_copies=total, available_copies=total)
    db.add(book)
    db.flush()

    branch = db.scalar(
        select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
    )
    for index in range(total):
        db.add(
            BookCopy(
                book_id=book.id,
                barcode=f"BC-{book.id:05d}-{index + 1:03d}",
                branch_id=branch.id if branch else None,
                condition="good",
                acquired_date=utcnow().date(),
            )
        )

    record_audit(
        db,
        action="book.created",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book.id,
        details={
            "title": book.title,
            "isbn": book.isbn,
            "copies": total,
            "format": book.book_format.value if book.book_format else None,
        },
    )
    db.commit()
    db.refresh(book)
    return book


@router.put("/books/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    payload: BookUpdate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    updates = payload.model_dump(exclude_unset=True)
    new_total = updates.get("total_copies")
    if new_total is not None:
        delta = new_total - book.total_copies
        book.total_copies = new_total
        book.available_copies = max(0, min(new_total, book.available_copies + delta))
        updates.pop("total_copies")
    for field, value in updates.items():
        setattr(book, field, value)
    record_audit(
        db,
        action="book.updated",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book.id,
        details={
            "title": book.title,
            "fields": sorted(updates),
            "total_copies": new_total if new_total is not None else book.total_copies,
        },
    )
    db.commit()
    db.refresh(book)
    return book


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> None:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    book.is_active = False
    record_audit(
        db,
        action="book.archived",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book.id,
        details={"title": book.title, "isbn": book.isbn},
    )
    db.commit()


@router.post(
    "/books/{book_id}/copies",
    response_model=BookCopyOut,
    status_code=status.HTTP_201_CREATED,
)
def add_copy(
    book_id: int,
    payload: BookCopyCreate,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> BookCopy:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if payload.branch_id and db.get(Branch, payload.branch_id) is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    barcode = payload.barcode or f"BC-{book_id}-{random.randint(100000, 999999)}"
    if db.scalar(select(BookCopy).where(BookCopy.barcode == barcode)):
        raise HTTPException(status_code=409, detail="Barcode already exists")
    copy = BookCopy(
        book_id=book_id,
        barcode=barcode,
        branch_id=payload.branch_id,
        condition=payload.condition,
        shelf_location=payload.shelf_location,
        acquired_date=payload.acquired_date or utcnow().date(),
    )
    book.total_copies += 1
    book.available_copies += 1
    db.add(copy)
    db.flush()
    record_audit(
        db,
        action="copy.added",
        user_id=current_user.id,
        entity_type="book",
        entity_id=book.id,
        details={
            "title": book.title,
            "barcode": copy.barcode,
            "branch_id": copy.branch_id,
        },
    )
    db.commit()
    db.refresh(copy)
    return copy


@router.get("/books/{book_id}/copies", response_model=list[BookCopyOut])
def list_copies(book_id: int, db: Session = Depends(get_db)) -> list[BookCopy]:
    if db.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return list(
        db.scalars(
            select(BookCopy)
            .where(BookCopy.book_id == book_id)
            .order_by(BookCopy.id)
        ).all()
    )


@router.get("/books/{book_id}/reviews", response_model=list[ReviewOut])
def list_reviews(book_id: int, db: Session = Depends(get_db)) -> list[ReviewOut]:
    reviews = db.scalars(
        select(Review)
        .where(Review.book_id == book_id)
        .options(selectinload(Review.member))
        .order_by(Review.created_at.desc())
    ).all()
    return [
        ReviewOut(
            id=r.id,
            book_id=r.book_id,
            member_id=r.member_id,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
            member_name=r.member.full_name if r.member else None,
        )
        for r in reviews
    ]


@router.post(
    "/books/{book_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def create_or_update_review(
    book_id: int,
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewOut:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    review = db.scalar(
        select(Review).where(
            Review.book_id == book_id, Review.member_id == current_user.id
        )
    )
    previous_rating = review.rating if review else None
    if review:
        review.rating = payload.rating
        review.comment = payload.comment
    else:
        review = Review(
            book_id=book_id,
            member_id=current_user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(review)
    db.flush()

    # Seeded catalog ratings are imported aggregates; keep them intact while
    # folding a member's new or edited rating into the running average.
    count_before = int(book.review_count or 0)
    avg_before = float(book.average_rating or 0)
    if count_before <= 0:
        book.average_rating = float(payload.rating)
        book.review_count = 1
    elif previous_rating is None:
        book.average_rating = round(
            ((avg_before * count_before) + payload.rating) / (count_before + 1), 2
        )
        book.review_count = count_before + 1
    else:
        book.average_rating = round(
            ((avg_before * count_before) - previous_rating + payload.rating)
            / count_before,
            2,
        )
    db.commit()
    db.refresh(review)
    return ReviewOut(
        id=review.id,
        book_id=review.book_id,
        member_id=review.member_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        member_name=current_user.full_name,
    )
