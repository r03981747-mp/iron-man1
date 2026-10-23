import math
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user, staff_required
from database.session import get_db
from models.library import Book, BookCopy, CopyStatus
from models.loan import Fine, FineStatus, Loan, LoanStatus, Reservation, ReservationStatus
from models.payment import Payment, PaymentStatus
from models.reading import ReadingShelf, ShelfStatus
from models.user import User, UserRole
from utils.datetime_utils import ensure_naive_utc, utcnow

router = APIRouter(prefix="/analytics", tags=["Analytics"])

MONTH_LABELS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def _month_key(dt) -> str:
    dt = ensure_naive_utc(dt)
    return f"{dt.year}-{dt.month:02d}"


def _last_months(count: int = 6) -> list[tuple[str, str]]:
    now = utcnow()
    months: list[tuple[str, str]] = []
    year, month = now.year, now.month
    for _ in range(count):
        months.append((f"{year}-{month:02d}", f"{MONTH_LABELS[month - 1]} {year % 100:02d}"))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def _monthly_series(db: Session, months: int = 6) -> list[dict]:
    labels = _last_months(months)
    keys = [k for k, _ in labels]
    loans = db.scalars(select(Loan)).all()
    loans_counts: dict[str, int] = defaultdict(int)
    for loan in loans:
        loans_counts[_month_key(loan.borrowed_at)] += 1

    payments = db.scalars(
        select(Payment).where(Payment.status == PaymentStatus.SUCCEEDED)
    ).all()
    revenue: dict[str, float] = defaultdict(float)
    for payment in payments:
        revenue[_month_key(payment.created_at)] += float(payment.amount)

    return [
        {
            "month": label,
            "loans": loans_counts.get(key, 0),
            "revenue": round(revenue.get(key, 0), 2),
        }
        for key, label in labels
    ]


@router.get("/dashboard")
def dashboard(
    _: User = Depends(staff_required), db: Session = Depends(get_db)
) -> dict:
    total_books = db.scalar(select(func.count(Book.id)).where(Book.is_active.is_(True))) or 0
    total_copies = db.scalar(select(func.sum(Book.total_copies))) or 0
    available_copies = db.scalar(select(func.sum(Book.available_copies))) or 0
    total_members = db.scalar(select(func.count(User.id)).where(User.role == UserRole.MEMBER)) or 0
    active_loans = db.scalar(
        select(func.count(Loan.id)).where(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]))
    ) or 0
    overdue_loans = db.scalar(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.OVERDUE)
    ) or 0
    unpaid_fines = db.scalar(
        select(func.coalesce(func.sum(Fine.amount), 0)).where(Fine.status == FineStatus.UNPAID)
    ) or 0
    revenue_total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.SUCCEEDED
        )
    ) or 0
    month_prefix = utcnow().strftime("%Y-%m")
    revenue_this_month = sum(
        float(p.amount)
        for p in db.scalars(
            select(Payment).where(Payment.status == PaymentStatus.SUCCEEDED)
        ).all()
        if _month_key(p.created_at) == month_prefix
    )
    pending_reservations = db.scalar(
        select(func.count(Reservation.id)).where(
            Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.READY])
        )
    ) or 0
    damaged_copies = db.scalar(
        select(func.count(BookCopy.id)).where(BookCopy.status == CopyStatus.MAINTENANCE)
    ) or 0

    popular_rows = db.execute(
        select(Book.id, Book.title, Book.average_rating, func.count(Loan.id).label("loans"))
        .join(Loan, Loan.book_id == Book.id)
        .group_by(Book.id)
        .order_by(func.count(Loan.id).desc())
        .limit(5)
    ).all()

    recent_loans = db.scalars(
        select(Loan)
        .options(selectinload(Loan.book), selectinload(Loan.member), selectinload(Loan.copy))
        .order_by(Loan.borrowed_at.desc())
        .limit(6)
    ).unique().all()

    return {
        "totals": {
            "books": total_books,
            "copies": int(total_copies),
            "available_copies": int(available_copies),
            "members": total_members,
            "active_loans": active_loans,
            "overdue_loans": overdue_loans,
            "pending_reservations": pending_reservations,
            "damaged_copies": damaged_copies,
        },
        "finance": {
            "unpaid_fines": round(float(unpaid_fines), 2),
            "revenue_total": round(float(revenue_total), 2),
            "revenue_this_month": round(revenue_this_month, 2),
            "currency": "USD",
        },
        "monthly": _monthly_series(db, 6),
        "popular_books": [
            {
                "id": row.id,
                "title": row.title,
                "rating": round(row.average_rating or 0, 2),
                "loans": row.loans,
            }
            for row in popular_rows
        ],
        "recent_loans": [
            {
                "id": loan.id,
                "book": loan.book.title if loan.book else None,
                "member": loan.member.full_name if loan.member else None,
                "borrowed_at": loan.borrowed_at,
                "due_date": loan.due_date,
                "status": loan.status.value,
            }
            for loan in recent_loans
        ],
    }


@router.get("/me")
def my_summary(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    now = utcnow()
    active_loans = db.scalars(
        select(Loan)
        .where(
            Loan.member_id == current_user.id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
        )
        .options(selectinload(Loan.book), selectinload(Loan.copy))
        .order_by(Loan.due_date)
    ).unique().all()
    returned_count = db.scalar(
        select(func.count(Loan.id)).where(
            Loan.member_id == current_user.id, Loan.status == LoanStatus.RETURNED
        )
    ) or 0
    unpaid = db.scalar(
        select(func.coalesce(func.sum(Fine.amount), 0)).where(
            Fine.member_id == current_user.id, Fine.status == FineStatus.UNPAID
        )
    ) or 0
    reservations = db.scalars(
        select(Reservation)
        .where(
            Reservation.member_id == current_user.id,
            Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.READY]),
        )
        .options(selectinload(Reservation.book))
    ).unique().all()
    next_due = min(
        (ensure_naive_utc(l.due_date) for l in active_loans), default=None
    )

    # Reading-goal progress comes from the personal "finished" shelf. Counting
    # here keeps the dashboard consistent with /shelves/me and avoids storing a
    # denormalized counter that can drift.
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    finished_entries = db.scalars(
        select(ReadingShelf).where(
            ReadingShelf.user_id == current_user.id,
            ReadingShelf.status == ShelfStatus.FINISHED,
        )
    ).all()
    finished_this_year = 0
    for entry in finished_entries:
        stamped = ensure_naive_utc(entry.finished_at or entry.updated_at or entry.created_at)
        if stamped is not None and stamped >= year_start:
            finished_this_year += 1
    goal_target = max(1, int(current_user.reading_goal or 12))

    return {
        "member": {
            "id": current_user.id,
            "name": current_user.full_name,
            "tier": current_user.membership_tier.value,
            "card": current_user.library_card_number,
        },
        "active_loans": len(active_loans),
        "books_read": returned_count,
        "finished_this_year": finished_this_year,
        "reading_goal": goal_target,
        "reading_goal_percent": min(100, round((finished_this_year / goal_target) * 100)),
        "reading_goal_year": now.year,
        "unpaid_fines": round(float(unpaid), 2),
        "reservations": len(reservations),
        "next_due_date": next_due.isoformat() if next_due else None,
        "current_loans": [
            {
                "id": loan.id,
                "book": loan.book.title if loan.book else None,
                "due_date": loan.due_date,
                "status": loan.status.value,
                "days_left": max(
                    0,
                    math.ceil(
                        (ensure_naive_utc(loan.due_date) - now).total_seconds() / 86400
                    ),
                )
                if ensure_naive_utc(loan.due_date) > now
                else -math.ceil(
                    (now - ensure_naive_utc(loan.due_date)).total_seconds() / 86400
                ),
            }
            for loan in active_loans
        ],
        "my_reservations": [
            {
                "id": r.id,
                "book": r.book.title if r.book else None,
                "status": r.status.value,
            }
            for r in reservations
        ],
    }


@router.get("/revenue")
def revenue_report(
    _: User = Depends(staff_required), db: Session = Depends(get_db)
) -> dict:
    monthly = _monthly_series(db, 12)
    by_type_rows = db.execute(
        select(Payment.payment_type, func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.status == PaymentStatus.SUCCEEDED)
        .group_by(Payment.payment_type)
    ).all()
    return {
        "monthly": monthly,
        "total": round(sum(m["revenue"] for m in monthly), 2),
        "by_type": {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): round(
                float(row[1]), 2
            )
            for row in by_type_rows
        },
    }


@router.get("/popular-books")
def popular_books(
    _: User = Depends(staff_required), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.execute(
        select(
            Book.id,
            Book.title,
            Book.average_rating,
            func.count(Loan.id).label("loans"),
        )
        .join(Loan, Loan.book_id == Book.id)
        .group_by(Book.id)
        .order_by(func.count(Loan.id).desc())
        .limit(10)
    ).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "rating": round(r.average_rating or 0, 2),
            "loans": r.loans,
        }
        for r in rows
    ]
