import math
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user, staff_required
from config.settings import settings
from database.session import get_db
from models.library import Book, BookCopy, CopyStatus
from models.loan import Fine, FineStatus, Loan, LoanStatus, Reservation, ReservationStatus
from models.notification import Notification
from models.payment import Payment, PaymentStatus, PaymentType
from models.user import User, UserRole
from schemas.loan import (
    FineAction,
    FineOut,
    LoanCreate,
    LoanListOut,
    LoanOut,
    ReservationCreate,
    ReservationOut,
    ReturnOut,
)
from utils.audit import record_audit
from utils.datetime_utils import ensure_naive_utc, utcnow

router = APIRouter(tags=["Circulation"])

_LOAN_LOADERS = (
    selectinload(Loan.book),
    selectinload(Loan.member),
    selectinload(Loan.copy),
)


def _is_staff(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.LIBRARIAN)


def _notify(db: Session, user_id: int, title: str, message: str, kind: str = "info") -> None:
    db.add(
        Notification(user_id=user_id, type=kind, title=title, message=message)
    )


def _loan_out(loan: Loan) -> LoanOut:
    now = utcnow()
    due = ensure_naive_utc(loan.due_date)
    days_overdue = 0
    if due is not None and loan.status in (LoanStatus.ACTIVE, LoanStatus.OVERDUE):
        if now > due:
            days_overdue = math.ceil((now - due).total_seconds() / 86400)
    return LoanOut(
        id=loan.id,
        book_id=loan.book_id,
        copy_id=loan.copy_id,
        member_id=loan.member_id,
        branch_id=loan.branch_id,
        borrowed_at=loan.borrowed_at,
        due_date=loan.due_date,
        returned_at=loan.returned_at,
        status=loan.status,
        renewed_count=loan.renewed_count,
        fine_amount=float(loan.fine_amount or 0),
        book_title=loan.book.title if loan.book else None,
        member_name=loan.member.full_name if loan.member else None,
        copy_barcode=loan.copy.barcode if loan.copy else None,
        days_overdue=days_overdue,
    )


def _refresh_overdue(db: Session) -> None:
    db.execute(
        update(Loan)
        .where(Loan.status == LoanStatus.ACTIVE, Loan.due_date < utcnow())
        .values(status=LoanStatus.OVERDUE)
    )
    db.commit()


@router.post("/loans", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def checkout_book(
    payload: LoanCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanOut:
    member_id = payload.member_id or current_user.id
    if not _is_staff(current_user) and member_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only borrow books for yourself"
        )
    member = db.get(User, member_id)
    if member is None or not member.is_active:
        raise HTTPException(status_code=400, detail="Member account is not active")

    active_count = (
        db.scalar(
            select(func.count(Loan.id)).where(
                Loan.member_id == member_id,
                Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
            )
        )
        or 0
    )
    if active_count >= settings.MAX_ACTIVE_LOANS:
        raise HTTPException(
            status_code=400,
            detail=f"Borrowing limit reached ({settings.MAX_ACTIVE_LOANS} books)",
        )

    book = db.get(Book, payload.book_id)
    if book is None or not book.is_active:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.available_copies <= 0:
        raise HTTPException(
            status_code=400,
            detail="No copies available right now. Please place a reservation.",
        )

    copy: BookCopy | None = None
    if payload.copy_id is not None:
        copy = db.get(BookCopy, payload.copy_id)
        if copy is None or copy.book_id != book.id:
            raise HTTPException(status_code=404, detail="Copy not found")
        if copy.status != CopyStatus.AVAILABLE:
            raise HTTPException(status_code=400, detail="This copy is not available")
    else:
        copy = db.scalar(
            select(BookCopy)
            .where(
                BookCopy.book_id == book.id,
                BookCopy.status == CopyStatus.AVAILABLE,
            )
            .order_by(BookCopy.id)
        )

    if copy is not None:
        copy.status = CopyStatus.ON_LOAN

    book.available_copies = max(0, book.available_copies - 1)
    now = utcnow()
    days = payload.days or settings.DEFAULT_LOAN_DAYS
    loan = Loan(
        book_id=book.id,
        copy_id=copy.id if copy else None,
        member_id=member_id,
        branch_id=copy.branch_id if copy else None,
        issued_by_id=current_user.id,
        borrowed_at=now,
        due_date=now + timedelta(days=days),
        status=LoanStatus.ACTIVE,
    )
    db.add(loan)

    reservation = db.scalar(
        select(Reservation).where(
            Reservation.book_id == book.id,
            Reservation.member_id == member_id,
            Reservation.status == ReservationStatus.READY,
        )
    )
    if reservation is not None:
        reservation.status = ReservationStatus.FULFILLED

    _notify(
        db,
        member_id,
        "Book checked out",
        f"'{book.title}' is due on {loan.due_date:%d %b %Y}.",
        "loan",
    )
    db.flush()
    record_audit(
        db,
        action="loan.checked_out",
        user_id=current_user.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "book": book.title,
            "member": member.full_name,
            "due_date": loan.due_date.isoformat(),
            "copy": copy.barcode if copy else None,
        },
    )
    db.commit()
    db.refresh(loan)
    return _loan_out(loan)


@router.get("/loans", response_model=LoanListOut)
def list_loans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    member_id: int | None = None,
    status_filter: LoanStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> LoanListOut:
    _refresh_overdue(db)
    stmt = select(Loan).options(*_LOAN_LOADERS)
    if not _is_staff(current_user):
        stmt = stmt.where(Loan.member_id == current_user.id)
    elif member_id:
        stmt = stmt.where(Loan.member_id == member_id)
    if status_filter:
        stmt = stmt.where(Loan.status == status_filter)
    stmt = stmt.order_by(Loan.borrowed_at.desc()).offset(skip).limit(limit)
    loans = db.scalars(stmt).unique().all()
    return LoanListOut(items=[_loan_out(loan) for loan in loans], total=len(loans))


@router.get("/loans/overdue", response_model=LoanListOut)
def overdue_loans(
    _: User = Depends(staff_required), db: Session = Depends(get_db)
) -> LoanListOut:
    _refresh_overdue(db)
    loans = db.scalars(
        select(Loan)
        .where(Loan.status == LoanStatus.OVERDUE)
        .options(*_LOAN_LOADERS)
        .order_by(Loan.due_date)
    ).unique().all()
    return LoanListOut(items=[_loan_out(loan) for loan in loans], total=len(loans))


@router.post("/loans/{loan_id}/return", response_model=ReturnOut)
def return_book(
    loan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReturnOut:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    if not _is_staff(current_user) and loan.member_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to return this loan")
    if loan.status not in (LoanStatus.ACTIVE, LoanStatus.OVERDUE):
        raise HTTPException(status_code=400, detail="This loan is already closed")

    now = utcnow()
    due = ensure_naive_utc(loan.due_date)
    days_overdue = 0
    if due is not None and now > due:
        days_overdue = math.ceil((now - due).total_seconds() / 86400)
    fine_amount = round(days_overdue * settings.FINE_PER_DAY, 2)

    loan.returned_at = now
    loan.status = LoanStatus.RETURNED
    loan.fine_amount = fine_amount

    if fine_amount > 0:
        db.add(
            Fine(
                loan_id=loan.id,
                member_id=loan.member_id,
                amount=fine_amount,
                reason=(
                    f"Overdue by {days_overdue} "
                    f"day{'s' if days_overdue != 1 else ''}"
                ),
            )
        )
        _notify(
            db,
            loan.member_id,
            "Overdue fine added",
            f"A fine of ${fine_amount:.2f} was added for '{loan.book.title}'.",
            "fine",
        )

    if loan.copy is not None:
        loan.copy.status = CopyStatus.AVAILABLE
    if loan.book is not None:
        loan.book.available_copies = min(
            loan.book.total_copies, loan.book.available_copies + 1
        )
        next_reservation = db.scalar(
            select(Reservation)
            .where(
                Reservation.book_id == loan.book_id,
                Reservation.status == ReservationStatus.PENDING,
            )
            .order_by(Reservation.reserved_at)
        )
        if next_reservation is not None:
            next_reservation.status = ReservationStatus.READY
            next_reservation.expires_at = now + timedelta(days=3)
            next_reservation.notified_at = now
            _notify(
                db,
                next_reservation.member_id,
                "Reserved book is ready",
                f"'{loan.book.title}' is waiting for you. Pick it up within 3 days.",
                "reservation",
            )

    record_audit(
        db,
        action="loan.returned",
        user_id=current_user.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "book": loan.book.title if loan.book else None,
            "member": loan.member.full_name if loan.member else None,
            "days_overdue": days_overdue,
            "fine_amount": fine_amount,
        },
    )
    db.commit()
    db.refresh(loan)
    message = "Book returned on time. Thank you!"
    if fine_amount > 0:
        message = (
            f"Book returned {days_overdue} "
            f"day{'s' if days_overdue != 1 else ''} late. Fine: ${fine_amount:.2f}"
        )
    return ReturnOut(
        loan=_loan_out(loan),
        fine_amount=fine_amount,
        days_overdue=days_overdue,
        message=message,
    )


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(
    loan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanOut:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    if not _is_staff(current_user) and loan.member_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to renew this loan")
    if loan.status != LoanStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="Only active, non-overdue loans can be renewed",
        )
    if loan.renewed_count >= settings.MAX_RENEWALS:
        raise HTTPException(
            status_code=400,
            detail=f"Renewal limit reached ({settings.MAX_RENEWALS})",
        )
    now = utcnow()
    due = ensure_naive_utc(loan.due_date)
    if due is not None and due < now:
        raise HTTPException(
            status_code=400, detail="Overdue loans cannot be renewed"
        )
    holds = db.scalar(
        select(Reservation.id).where(
            Reservation.book_id == loan.book_id,
            Reservation.status.in_(
                [ReservationStatus.PENDING, ReservationStatus.READY]
            ),
        )
    )
    if holds:
        raise HTTPException(
            status_code=400, detail="This book has pending reservations"
        )
    loan.due_date = max(now, due or now) + timedelta(days=settings.DEFAULT_LOAN_DAYS)
    loan.renewed_count += 1
    record_audit(
        db,
        action="loan.renewed",
        user_id=current_user.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "book": loan.book.title if loan.book else None,
            "member": loan.member.full_name if loan.member else None,
            "renewed_count": loan.renewed_count,
            "due_date": loan.due_date.isoformat(),
        },
    )
    db.commit()
    db.refresh(loan)
    return _loan_out(loan)


# ---------------------------- Reservations --------------------------------
@router.post(
    "/reservations",
    response_model=ReservationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(
    payload: ReservationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReservationOut:
    member_id = payload.member_id or current_user.id
    if not _is_staff(current_user) and member_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only reserve books for yourself"
        )
    book = db.get(Book, payload.book_id)
    if book is None or not book.is_active:
        raise HTTPException(status_code=404, detail="Book not found")
    existing = db.scalar(
        select(Reservation).where(
            Reservation.book_id == book.id,
            Reservation.member_id == member_id,
            Reservation.status.in_(
                [ReservationStatus.PENDING, ReservationStatus.READY]
            ),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="You already have an active reservation"
        )
    reservation = Reservation(
        book_id=book.id,
        member_id=member_id,
        status=ReservationStatus.PENDING,
    )
    db.add(reservation)
    db.flush()
    record_audit(
        db,
        action="reservation.created",
        user_id=current_user.id,
        entity_type="reservation",
        entity_id=reservation.id,
        details={"book": book.title, "member_id": member_id},
    )
    db.commit()
    db.refresh(reservation)
    return ReservationOut(
        id=reservation.id,
        book_id=reservation.book_id,
        member_id=reservation.member_id,
        branch_id=reservation.branch_id,
        reserved_at=reservation.reserved_at,
        expires_at=reservation.expires_at,
        status=reservation.status,
        book_title=book.title,
        member_name=current_user.full_name if member_id == current_user.id else None,
    )


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    member_id: int | None = None,
) -> list[ReservationOut]:
    stmt = select(Reservation).options(
        selectinload(Reservation.book), selectinload(Reservation.member)
    )
    if not _is_staff(current_user):
        stmt = stmt.where(Reservation.member_id == current_user.id)
    elif member_id:
        stmt = stmt.where(Reservation.member_id == member_id)
    reservations = db.scalars(
        stmt.order_by(Reservation.reserved_at.desc())
    ).unique().all()
    return [
        ReservationOut(
            id=r.id,
            book_id=r.book_id,
            member_id=r.member_id,
            branch_id=r.branch_id,
            reserved_at=r.reserved_at,
            expires_at=r.expires_at,
            status=r.status,
            book_title=r.book.title if r.book else None,
            member_name=r.member.full_name if r.member else None,
        )
        for r in reservations
    ]


@router.delete("/reservations/{reservation_id}", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReservationOut:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if not _is_staff(current_user) and reservation.member_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not allowed to cancel this reservation"
        )
    if reservation.status not in (
        ReservationStatus.PENDING,
        ReservationStatus.READY,
    ):
        raise HTTPException(status_code=400, detail="Reservation is not active")
    reservation.status = ReservationStatus.CANCELLED
    record_audit(
        db,
        action="reservation.cancelled",
        user_id=current_user.id,
        entity_type="reservation",
        entity_id=reservation.id,
        details={"book_id": reservation.book_id, "member_id": reservation.member_id},
    )
    db.commit()
    db.refresh(reservation)
    return ReservationOut(
        id=reservation.id,
        book_id=reservation.book_id,
        member_id=reservation.member_id,
        branch_id=reservation.branch_id,
        reserved_at=reservation.reserved_at,
        expires_at=reservation.expires_at,
        status=reservation.status,
    )


# -------------------------------- Fines -----------------------------------
@router.get("/fines", response_model=list[FineOut])
def list_fines(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: FineStatus | None = Query(default=None, alias="status"),
) -> list[FineOut]:
    stmt = select(Fine).options(
        selectinload(Fine.member), selectinload(Fine.loan).selectinload(Loan.book)
    )
    if not _is_staff(current_user):
        stmt = stmt.where(Fine.member_id == current_user.id)
    if status_filter:
        stmt = stmt.where(Fine.status == status_filter)
    fines = db.scalars(stmt.order_by(Fine.created_at.desc())).unique().all()
    return [
        FineOut(
            id=f.id,
            loan_id=f.loan_id,
            member_id=f.member_id,
            amount=float(f.amount),
            reason=f.reason,
            status=f.status,
            paid_at=f.paid_at,
            created_at=f.created_at,
            member_name=f.member.full_name if f.member else None,
            book_title=f.loan.book.title if f.loan and f.loan.book else None,
        )
        for f in fines
    ]


@router.post("/fines/{fine_id}/pay")
def pay_fine_at_desk(
    fine_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise HTTPException(status_code=404, detail="Fine not found")
    if not _is_staff(current_user) and fine.member_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to pay this fine")
    if fine.status != FineStatus.UNPAID:
        raise HTTPException(status_code=400, detail="Fine is not unpaid")
    now = utcnow()
    fine.status = FineStatus.PAID
    fine.paid_at = now
    payment = Payment(
        member_id=fine.member_id,
        amount=fine.amount,
        payment_type=PaymentType.FINE,
        status=PaymentStatus.SUCCEEDED,
        description=f"Fine #{fine.id} paid at the desk",
        paid_at=now,
        meta={"fine_ids": [fine.id]},
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        action="fine.paid",
        user_id=current_user.id,
        entity_type="fine",
        entity_id=fine.id,
        details={
            "member_id": fine.member_id,
            "amount": float(fine.amount),
            "payment_id": payment.id,
            "channel": "desk",
        },
    )
    db.commit()
    db.refresh(payment)
    return {
        "message": "Fine paid successfully",
        "payment_id": payment.id,
        "amount": float(fine.amount),
    }


@router.post("/fines/{fine_id}/waive", response_model=FineOut)
def waive_fine(
    fine_id: int,
    payload: FineAction,
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> FineOut:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise HTTPException(status_code=404, detail="Fine not found")
    if fine.status != FineStatus.UNPAID:
        raise HTTPException(status_code=400, detail="Fine is not unpaid")
    fine.status = FineStatus.WAIVED
    fine.waived_by_id = current_user.id
    if payload.reason:
        fine.reason = f"{fine.reason} — waived: {payload.reason}"
    record_audit(
        db,
        action="fine.waived",
        user_id=current_user.id,
        entity_type="fine",
        entity_id=fine.id,
        details={
            "member_id": fine.member_id,
            "amount": float(fine.amount),
            "reason": payload.reason,
        },
    )
    db.commit()
    db.refresh(fine)
    return FineOut(
        id=fine.id,
        loan_id=fine.loan_id,
        member_id=fine.member_id,
        amount=float(fine.amount),
        reason=fine.reason,
        status=fine.status,
        paid_at=fine.paid_at,
        created_at=fine.created_at,
    )
