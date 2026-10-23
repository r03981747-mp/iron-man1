"""Seed the database with a realistic demo library."""

import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth.security import hash_password
from models.audit import AuditLog
from models.event import Event
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
from models.loan import Fine, FineStatus, Loan, LoanStatus, Reservation, ReservationStatus
from models.notification import Notification
from models.reading import ReadingShelf, ShelfStatus
from models.payment import (
    MembershipSubscription,
    Payment,
    PaymentStatus,
    PaymentType,
    SubscriptionStatus,
)
from models.review import Review
from models.space import BookingStatus, Room, RoomBooking
from models.user import MembershipTier, User, UserRole
from utils.datetime_utils import utcnow

rng = random.Random(42)


def _local_slot(
    days_ahead: int,
    hour: int,
    minute: int = 0,
    duration_hours: int = 2,
) -> tuple[datetime, datetime]:
    """Build a readable local-time event slot, stored as naive UTC."""
    local_now = datetime.now().astimezone()
    start_local = (local_now + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, start_utc + timedelta(hours=duration_hours)


BOOKS = [
    # title, isbn, author, category, year, copies, rating, reviews, tags, description
    (
        "1984",
        "9780451524935",
        "George Orwell",
        "Fiction",
        1949,
        4,
        4.8,
        1240,
        ["classic", "dystopian", "politics"],
        "Winston Smith rewrites history for the Ministry of Truth while dreaming of rebellion in a world of perpetual surveillance.",
    ),
    (
        "Animal Farm",
        "9780451526342",
        "George Orwell",
        "Fiction",
        1945,
        3,
        4.6,
        980,
        ["classic", "satire", "politics"],
        "A group of farm animals overthrow their human master, only to discover that absolute power corrupts absolutely.",
    ),
    (
        "Pride and Prejudice",
        "9780141439518",
        "Jane Austen",
        "Fiction",
        1813,
        3,
        4.7,
        1560,
        ["romance", "classic"],
        "Elizabeth Bennet navigates love, family and social expectation in Regency England.",
    ),
    (
        "Sapiens: A Brief History of Humankind",
        "9780062316097",
        "Yuval Noah Harari",
        "History",
        2011,
        5,
        4.5,
        2210,
        ["history", "anthropology", "bestseller"],
        "How Homo sapiens came to dominate the planet, told across 70,000 years of human history.",
    ),
    (
        "Homo Deus: A Brief History of Tomorrow",
        "9780062464316",
        "Yuval Noah Harari",
        "History",
        2015,
        3,
        4.3,
        840,
        ["future", "technology", "history"],
        "What happens when science, data and artificial intelligence redefine what it means to be human?",
    ),
    (
        "Clean Code",
        "9780132350884",
        "Robert C. Martin",
        "Technology",
        2008,
        4,
        4.7,
        1320,
        ["programming", "software", "engineering"],
        "A handbook of agile software craftsmanship, filled with principles for writing readable, maintainable code.",
    ),
    (
        "The Pragmatic Programmer",
        "9780201616224",
        "Andrew Hunt",
        "Technology",
        1999,
        3,
        4.6,
        1100,
        ["programming", "career", "software"],
        "Timeless advice on becoming a more effective and adaptive software developer.",
    ),
    (
        "Deep Learning",
        "9780262035613",
        "Ian Goodfellow",
        "Technology",
        2016,
        2,
        4.4,
        460,
        ["ai", "machine-learning", "textbook"],
        "The foundational textbook on deep learning theory, methods and applications.",
    ),
    (
        "A Brief History of Time",
        "9780553380163",
        "Stephen Hawking",
        "Science",
        1988,
        3,
        4.6,
        1440,
        ["physics", "cosmology", "science"],
        "A landmark exploration of the universe, black holes and the nature of time, written for everyone.",
    ),
    (
        "The Selfish Gene",
        "9780198788607",
        "Richard Dawkins",
        "Science",
        1976,
        2,
        4.4,
        620,
        ["biology", "evolution", "science"],
        "A revolutionary view of evolution from the perspective of the gene.",
    ),
    (
        "Foundation",
        "9780553293357",
        "Isaac Asimov",
        "Fiction",
        1951,
        3,
        4.7,
        1180,
        ["sci-fi", "classic", "series"],
        "As the Galactic Empire collapses, one man plots to shorten the coming dark age.",
    ),
    (
        "I, Robot",
        "9780553294385",
        "Isaac Asimov",
        "Fiction",
        1950,
        2,
        4.5,
        760,
        ["sci-fi", "short-stories", "classic"],
        "Nine stories that explore the ethics and unintended consequences of artificial intelligence.",
    ),
    (
        "Things Fall Apart",
        "9780385474542",
        "Chinua Achebe",
        "Fiction",
        1958,
        3,
        4.5,
        890,
        ["african-literature", "classic"],
        "The story of Okonkwo and the arrival of colonialism in Igbo society.",
    ),
    (
        "I Know Why the Caged Bird Sings",
        "9780345514400",
        "Maya Angelou",
        "Biography",
        1969,
        2,
        4.6,
        540,
        ["memoir", "autobiography", "classic"],
        "Maya Angelou's lyrical memoir of trauma, resilience and self-discovery.",
    ),
    (
        "Steve Jobs",
        "9781451648539",
        "Walter Isaacson",
        "Biography",
        2011,
        3,
        4.4,
        970,
        ["biography", "technology", "business"],
        "The definitive biography of Apple's visionary co-founder, based on hundreds of interviews.",
    ),
    (
        "Murder on the Orient Express",
        "9780062693662",
        "Agatha Christie",
        "Fiction",
        1934,
        3,
        4.6,
        1020,
        ["mystery", "crime", "classic"],
        "Hercule Poirot must solve a murder aboard a snowbound luxury train.",
    ),
    (
        "The Hobbit",
        "9780547928227",
        "J.R.R. Tolkien",
        "Fiction",
        1937,
        4,
        4.8,
        1870,
        ["fantasy", "adventure", "classic"],
        "Bilbo Baggins is swept into an epic quest for treasure and a dragon.",
    ),
    (
        "Thinking, Fast and Slow",
        "9780374533557",
        "Daniel Kahneman",
        "Psychology",
        2011,
        3,
        4.5,
        1340,
        ["psychology", "decision-making", "bestseller"],
        "Nobel laureate Daniel Kahneman reveals the two systems that drive the way we think.",
    ),
    (
        "The Alchemist",
        "9780061122415",
        "Paulo Coelho",
        "Fiction",
        1988,
        4,
        4.4,
        2050,
        ["philosophy", "inspirational", "classic"],
        "A shepherd boy travels the world in search of treasure and finds wisdom instead.",
    ),
    (
        "The Great Gatsby",
        "9780743273565",
        "F. Scott Fitzgerald",
        "Fiction",
        1925,
        2,
        4.3,
        1490,
        ["classic", "american-literature"],
        "Jay Gatsby's glittering world of parties and obsession on Long Island's Gold Coast.",
    ),
]

PUBLISHER_BY_TITLE = {
    "1984": "Penguin Random House",
    "Animal Farm": "Penguin Random House",
    "Pride and Prejudice": "Penguin Random House",
    "Sapiens: A Brief History of Humankind": "HarperCollins",
    "Homo Deus: A Brief History of Tomorrow": "HarperCollins",
    "Clean Code": "O'Reilly Media",
    "The Pragmatic Programmer": "Addison-Wesley",
    "Deep Learning": "MIT Press",
    "A Brief History of Time": "Penguin Random House",
    "The Selfish Gene": "Oxford University Press",
    "Foundation": "Penguin Random House",
    "I, Robot": "Penguin Random House",
    "Things Fall Apart": "Penguin Random House",
    "I Know Why the Caged Bird Sings": "Penguin Random House",
    "Steve Jobs": "Simon & Schuster",
    "Murder on the Orient Express": "HarperCollins",
    "The Hobbit": "HarperCollins",
    "Thinking, Fast and Slow": "Macmillan Publishers",
    "The Alchemist": "HarperCollins",
    "The Great Gatsby": "Simon & Schuster",
}

AUTHOR_BIOS = {
    "George Orwell": "English novelist and essayist known for his critique of totalitarianism.",
    "Jane Austen": "English novelist whose social commentary defined the Regency novel.",
    "Yuval Noah Harari": "Historian and professor at the Hebrew University of Jerusalem.",
    "Robert C. Martin": "Software engineer and author known as 'Uncle Bob'.",
    "Andrew Hunt": "Software developer and co-author of The Pragmatic Programmer.",
    "Ian Goodfellow": "Machine learning researcher and inventor of generative adversarial networks.",
    "Stephen Hawking": "Theoretical physicist and cosmologist.",
    "Richard Dawkins": "Evolutionary biologist and author.",
    "Isaac Asimov": "Biochemist and one of the most prolific science fiction writers.",
    "Chinua Achebe": "Nigerian novelist, poet and critic.",
    "Maya Angelou": "American poet, memoirist and civil rights activist.",
    "Walter Isaacson": "Biographer and former editor of Time magazine.",
    "Agatha Christie": "The best-selling novelist of all time, creator of Hercule Poirot.",
    "J.R.R. Tolkien": "Philologist and author of The Lord of the Rings.",
    "Daniel Kahneman": "Psychologist and Nobel laureate in economics.",
    "Paulo Coelho": "Brazilian novelist and lyricist.",
    "F. Scott Fitzgerald": "American novelist of the Jazz Age.",
}


def _cover(isbn: str) -> str:
    return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"


# Public-domain editions available on Project Gutenberg.
DIGITAL_EDITIONS = {
    "Pride and Prejudice": "https://www.gutenberg.org/cache/epub/1342/pg1342-images.html",
    "The Great Gatsby": "https://www.gutenberg.org/cache/epub/64317/pg64317-images.html",
}


def seed_database(db: Session) -> None:
    existing = db.scalar(select(func.count(User.id))) or 0
    if existing:
        return

    now = utcnow()

    # ------------------------------ Branches ------------------------------
    central = Branch(
        name="Central Library",
        address="12 MG Road, Bengaluru, Karnataka 560001",
        phone="+91 80 4123 5678",
        email="central@library.com",
        opening_hours={
            "mon_fri": "9:00 AM – 8:00 PM",
            "sat_sun": "10:00 AM – 6:00 PM",
        },
    )
    east = Branch(
        name="Eastside Branch",
        address="45 Indiranagar 100ft Road, Bengaluru 560038",
        phone="+91 80 4123 9012",
        email="east@library.com",
        opening_hours={
            "mon_fri": "10:00 AM – 7:00 PM",
            "sat_sun": "10:00 AM – 4:00 PM",
        },
    )
    db.add_all([central, east])
    db.flush()

    # ------------------------------- Spaces --------------------------------
    reading_room = Room(
        name="The Reading Room",
        branch_id=central.id,
        room_type="study",
        capacity=6,
        hourly_rate=0,
        description=(
            "A calm, book-lined room for deep work, group revision and quiet "
            "study sessions."
        ),
        amenities=["Whiteboard", "Power outlets", "Quiet zone"],
    )
    innovation_studio = Room(
        name="Innovation Studio",
        branch_id=east.id,
        room_type="studio",
        capacity=8,
        hourly_rate=0,
        description=(
            "A flexible makerspace for recording, prototyping and small "
            "digital-media workshops."
        ),
        amenities=["Recording mic", "Large display", "Maker bench"],
    )
    focus_pod = Room(
        name="Focus Pod",
        branch_id=central.id,
        room_type="focus",
        capacity=2,
        hourly_rate=0,
        description="A compact sound-treated pod for calls, interviews and solo focus.",
        amenities=["Acoustic panels", "USB-C dock"],
    )
    community_room = Room(
        name="Community Room",
        branch_id=east.id,
        room_type="meeting",
        capacity=20,
        hourly_rate=0,
        description=(
            "A welcoming space for reading groups, tutoring and community "
            "meet-ups. Bookings are free for members."
        ),
        amenities=["Projector", "Movable tables", "Step-free access"],
    )
    db.add_all([reading_room, innovation_studio, focus_pod, community_room])
    db.flush()

    # ----------------------------- Categories -----------------------------
    category_specs = {
        "Fiction": ("Novels, short stories and literary classics", "#6366f1"),
        "History": ("Human history, civilisations and world events", "#f59e0b"),
        "Technology": ("Software, computing and engineering", "#10b981"),
        "Science": ("Physics, biology and the natural world", "#06b6d4"),
        "Biography": ("Lives of remarkable people", "#ec4899"),
        "Psychology": ("Mind, behaviour and decision making", "#8b5cf6"),
    }
    categories = {}
    for name, (description, color) in category_specs.items():
        category = Category(name=name, description=description, color=color)
        db.add(category)
        categories[name] = category
    db.flush()

    # ------------------------------ Authors -------------------------------
    authors = {}
    for name, bio in AUTHOR_BIOS.items():
        author = Author(name=name, bio=bio)
        db.add(author)
        authors[name] = author
    db.flush()

    # ---------------------------- Publishers ------------------------------
    publisher_names = [
        "Penguin Random House",
        "HarperCollins",
        "O'Reilly Media",
        "Oxford University Press",
        "Simon & Schuster",
        "Macmillan Publishers",
        "MIT Press",
        "Addison-Wesley",
    ]
    publishers = {}
    for name in publisher_names:
        publisher = Publisher(name=name, website="https://example.com")
        db.add(publisher)
        publishers[name] = publisher
    db.flush()

    # ------------------------------- Books --------------------------------
    books: list[Book] = []
    for index, (
        title,
        isbn,
        author_name,
        category_name,
        year,
        copies,
        rating,
        review_count,
        tags,
        description,
    ) in enumerate(BOOKS):
        book = Book(
            isbn=isbn,
            title=title,
            description=description,
            author_id=authors[author_name].id,
            publisher_id=publishers[
                PUBLISHER_BY_TITLE.get(title, "Penguin Random House")
            ].id,
            category_id=categories[category_name].id,
            publication_year=year,
            language="English",
            cover_image_url=_cover(isbn),
            digital_file_url=DIGITAL_EDITIONS.get(title),
            book_format=BookFormat.HARDCOVER,
            total_copies=copies,
            available_copies=copies,
            price=round(12.99 + (index % 8) * 3.0, 2),
            replacement_cost=round(25 + (index % 5) * 5.0, 2),
            tags=tags,
            average_rating=rating,
            review_count=review_count,
        )
        db.add(book)
        books.append(book)
    db.flush()

    # ------------------------------ Copies --------------------------------
    for book in books:
        branch_split = max(1, math.ceil(book.total_copies * 0.7))
        for i in range(book.total_copies):
            branch = central if i < branch_split else east
            db.add(
                BookCopy(
                    book_id=book.id,
                    branch_id=branch.id,
                    barcode=f"BC-{book.id:04d}-{i + 1:02d}",
                    status=CopyStatus.AVAILABLE,
                    condition="good" if i % 4 else "like_new",
                    shelf_location=f"{book.category_id:02d}-{chr(65 + (i % 5))}{i + 1:02d}",
                )
            )
    db.flush()

    # ------------------------------- Users --------------------------------
    admin = User(
        email="admin@library.com",
        hashed_password=hash_password("Admin@123"),
        full_name="Rahul Gowda",
        phone="+91 98765 43210",
        role=UserRole.ADMIN,
        membership_tier=MembershipTier.PREMIUM,
        library_card_number="LIB-ADMIN-0001",
        reading_goal=12,
        is_verified=True,
    )
    librarian = User(
        email="librarian@library.com",
        hashed_password=hash_password("Librarian@123"),
        full_name="Meera Iyer",
        phone="+91 98765 43211",
        role=UserRole.LIBRARIAN,
        membership_tier=MembershipTier.PREMIUM,
        library_card_number="LIB-STAFF-0002",
        reading_goal=20,
        is_verified=True,
    )
    member = User(
        email="member@library.com",
        hashed_password=hash_password("Member@123"),
        full_name="Aarav Sharma",
        phone="+91 90000 11111",
        address="7 Brigade Road, Bengaluru",
        role=UserRole.MEMBER,
        membership_tier=MembershipTier.BASIC,
        library_card_number="LIB-2026-000001",
        reading_goal=24,
        is_verified=True,
    )
    priya = User(
        email="priya@library.com",
        hashed_password=hash_password("Member@123"),
        full_name="Priya Patel",
        phone="+91 90000 22222",
        role=UserRole.MEMBER,
        membership_tier=MembershipTier.PREMIUM,
        library_card_number="LIB-2026-000002",
        reading_goal=30,
        is_verified=True,
    )
    john = User(
        email="john@library.com",
        hashed_password=hash_password("Member@123"),
        full_name="John Mathew",
        phone="+91 90000 33333",
        role=UserRole.MEMBER,
        membership_tier=MembershipTier.STUDENT,
        library_card_number="LIB-2026-000003",
        reading_goal=18,
        is_verified=True,
    )
    sara = User(
        email="sara@library.com",
        hashed_password=hash_password("Member@123"),
        full_name="Sara Khan",
        phone="+91 90000 44444",
        role=UserRole.MEMBER,
        membership_tier=MembershipTier.FAMILY,
        library_card_number="LIB-2026-000004",
        reading_goal=16,
        is_verified=True,
    )
    members = [member, priya, john, sara]
    db.add_all([admin, librarian, *members])
    db.flush()

    # --------------------------- Room bookings -----------------------------
    tomorrow = (now + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    room_booking = RoomBooking(
        room_id=reading_room.id,
        member_id=member.id,
        start_time=tomorrow,
        end_time=tomorrow + timedelta(hours=2),
        status=BookingStatus.CONFIRMED,
        notes="Quiet study session",
        total_amount=0,
    )
    db.add(room_booking)
    db.flush()

    # ------------------------------- Loans --------------------------------
    by_title = {book.title: book for book in books}

    def make_loan(
        book: Book,
        borrower: User,
        borrowed_days_ago: int,
        returned_days_ago: int | None = None,
        status: LoanStatus = LoanStatus.ACTIVE,
    ) -> Loan:
        copy = db.scalar(
            select(BookCopy)
            .where(BookCopy.book_id == book.id, BookCopy.status == CopyStatus.AVAILABLE)
            .order_by(BookCopy.id)
        )
        borrowed_at = now - timedelta(days=borrowed_days_ago)
        loan = Loan(
            book_id=book.id,
            copy_id=copy.id if copy else None,
            member_id=borrower.id,
            branch_id=copy.branch_id if copy else central.id,
            issued_by_id=librarian.id,
            borrowed_at=borrowed_at,
            due_date=borrowed_at + timedelta(days=14),
            status=status,
            renewed_count=0,
        )
        if returned_days_ago is not None:
            loan.returned_at = now - timedelta(days=returned_days_ago)
            loan.status = LoanStatus.RETURNED
        elif copy is not None:
            copy.status = CopyStatus.ON_LOAN
            book.available_copies = max(0, book.available_copies - 1)
        db.add(loan)
        return loan

    loan_1984 = make_loan(by_title["1984"], member, 5)
    make_loan(
        by_title["Clean Code"],
        member,
        20,
        status=LoanStatus.OVERDUE,
    )
    make_loan(by_title["Sapiens: A Brief History of Humankind"], priya, 3)
    make_loan(by_title["Foundation"], john, 25, returned_days_ago=10)
    make_loan(by_title["The Hobbit"], sara, 30, returned_days_ago=5)

    # Historical loans for the analytics charts
    for month_offset in range(1, 6):
        for i in range(8):
            book = rng.choice(books)
            borrower = rng.choice(members)
            borrowed_days_ago = month_offset * 30 - i * 2
            returned_days_ago = max(1, borrowed_days_ago - rng.randint(6, 12))
            make_loan(book, borrower, borrowed_days_ago, returned_days_ago=returned_days_ago)

    db.flush()

    # --------------------------- Reading shelves ---------------------------
    # Give the demo account a lived-in reading life so the dashboard, shelves
    # and annual goal have something meaningful to show immediately.
    db.add_all(
        [
            ReadingShelf(
                user_id=member.id,
                book_id=by_title["The Hobbit"].id,
                status=ShelfStatus.WANT_TO_READ,
            ),
            ReadingShelf(
                user_id=member.id,
                book_id=by_title["The Alchemist"].id,
                status=ShelfStatus.WANT_TO_READ,
            ),
            ReadingShelf(
                user_id=member.id,
                book_id=by_title["Sapiens: A Brief History of Humankind"].id,
                status=ShelfStatus.READING,
                progress=42,
                started_at=now - timedelta(days=9),
            ),
            ReadingShelf(
                user_id=member.id,
                book_id=by_title["1984"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=38),
                finished_at=now - timedelta(days=21),
                note="Still thinking about the ending.",
            ),
            ReadingShelf(
                user_id=member.id,
                book_id=by_title["Pride and Prejudice"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=95),
                finished_at=now - timedelta(days=72),
            ),
            ReadingShelf(
                user_id=priya.id,
                book_id=by_title["1984"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=44),
                finished_at=now - timedelta(days=26),
            ),
            ReadingShelf(
                user_id=priya.id,
                book_id=by_title["The Great Gatsby"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=32),
                finished_at=now - timedelta(days=12),
            ),
            ReadingShelf(
                user_id=priya.id,
                book_id=by_title["Sapiens: A Brief History of Humankind"].id,
                status=ShelfStatus.READING,
                progress=68,
                started_at=now - timedelta(days=16),
            ),
            ReadingShelf(
                user_id=john.id,
                book_id=by_title["Clean Code"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=60),
                finished_at=now - timedelta(days=34),
            ),
            ReadingShelf(
                user_id=john.id,
                book_id=by_title["Deep Learning"].id,
                status=ShelfStatus.WANT_TO_READ,
            ),
            ReadingShelf(
                user_id=sara.id,
                book_id=by_title["The Hobbit"].id,
                status=ShelfStatus.FINISHED,
                progress=100,
                started_at=now - timedelta(days=48),
                finished_at=now - timedelta(days=18),
            ),
        ]
    )
    db.flush()

    # ------------------------------- Fines --------------------------------
    unpaid_fine = Fine(
        loan_id=None,
        member_id=sara.id,
        amount=1.25,
        reason="Overdue by 5 days",
        status=FineStatus.UNPAID,
    )
    paid_fine = Fine(
        loan_id=None,
        member_id=john.id,
        amount=2.50,
        reason="Overdue by 10 days",
        status=FineStatus.PAID,
        paid_at=now - timedelta(days=20),
    )
    db.add_all([unpaid_fine, paid_fine])
    db.flush()

    # --------------------------- Reservations ------------------------------
    db.add(
        Reservation(
            book_id=by_title["The Hobbit"].id,
            member_id=john.id,
            branch_id=central.id,
            status=ReservationStatus.READY,
            expires_at=now + timedelta(days=2),
            notified_at=now - timedelta(hours=4),
        )
    )

    # ----------------------------- Payments --------------------------------
    db.add_all(
        [
            Payment(
                member_id=priya.id,
                amount=9.99,
                payment_type=PaymentType.MEMBERSHIP,
                status=PaymentStatus.SUCCEEDED,
                description="Premium membership (monthly)",
                paid_at=now - timedelta(days=42),
                created_at=now - timedelta(days=42),
            ),
            Payment(
                member_id=john.id,
                amount=2.50,
                payment_type=PaymentType.FINE,
                status=PaymentStatus.SUCCEEDED,
                description=f"Fine #{paid_fine.id} paid at the desk",
                paid_at=now - timedelta(days=20),
                created_at=now - timedelta(days=20),
            ),
            Payment(
                member_id=member.id,
                amount=5.00,
                payment_type=PaymentType.EVENT,
                status=PaymentStatus.SUCCEEDED,
                description="Ticket: Author Talk — The Future of AI",
                paid_at=now - timedelta(days=9),
                created_at=now - timedelta(days=9),
            ),
            Payment(
                member_id=sara.id,
                amount=0.75,
                payment_type=PaymentType.FINE,
                status=PaymentStatus.SUCCEEDED,
                description="Overdue fine (previous month)",
                paid_at=now - timedelta(days=65),
                created_at=now - timedelta(days=65),
            ),
        ]
    )

    db.add(
        MembershipSubscription(
            member_id=priya.id,
            tier="premium",
            status=SubscriptionStatus.ACTIVE,
            amount=9.99,
            current_period_start=now - timedelta(days=12),
            current_period_end=now + timedelta(days=18),
        )
    )

    # ------------------------------ Reviews --------------------------------
    db.add_all(
        [
            Review(
                book_id=by_title["1984"].id,
                member_id=member.id,
                rating=5,
                comment="A chilling masterpiece. Every reread reveals something new.",
            ),
            Review(
                book_id=by_title["Sapiens: A Brief History of Humankind"].id,
                member_id=priya.id,
                rating=4,
                comment="Ambitious and thought-provoking, though it moves fast through millennia.",
            ),
            Review(
                book_id=by_title["Clean Code"].id,
                member_id=john.id,
                rating=5,
                comment="Changed the way I write software. A must-read for every developer.",
            ),
            Review(
                book_id=by_title["Pride and Prejudice"].id,
                member_id=sara.id,
                rating=5,
                comment="Witty, warm and still sharp after two centuries. Elizabeth is unforgettable.",
            ),
            Review(
                book_id=by_title["The Great Gatsby"].id,
                member_id=priya.id,
                rating=4,
                comment="Gorgeous prose and a haunting portrait of ambition. A perfect weekend read.",
            ),
        ]
    )

    # ------------------------------- Events --------------------------------
    story_start, story_end = _local_slot(3, 10, 30, 1)
    ai_start, ai_end = _local_slot(7, 18, 30, 2)
    book_club_start, book_club_end = _local_slot(10, 18, 0, 2)
    python_start, python_end = _local_slot(14, 10, 0, 3)
    db.add_all(
        [
            Event(
                title="Author Talk: The Future of AI",
                description=(
                    "Join leading researchers for a conversation about artificial "
                    "intelligence, creativity and the future of work."
                ),
                branch_id=central.id,
                start_time=ai_start,
                end_time=ai_end,
                capacity=80,
                ticket_price=5,
                created_by_id=librarian.id,
            ),
            Event(
                title="Children's Story Hour",
                description="Songs, stories and crafts for ages 3–8. Parents welcome!",
                branch_id=east.id,
                start_time=story_start,
                end_time=story_end,
                capacity=30,
                ticket_price=0,
                created_by_id=librarian.id,
            ),
            Event(
                title="Book Club: Sapiens",
                description=(
                    "This month we discuss Yuval Noah Harari's sweeping history "
                    "of humankind. New members always welcome."
                ),
                branch_id=central.id,
                start_time=book_club_start,
                end_time=book_club_end,
                capacity=25,
                ticket_price=0,
                created_by_id=librarian.id,
            ),
            Event(
                title="Python Crash Course Workshop",
                description=(
                    "A hands-on beginner workshop. Bring a laptop — we will build "
                    "your first web app together."
                ),
                branch_id=central.id,
                start_time=python_start,
                end_time=python_end,
                capacity=40,
                ticket_price=15,
                created_by_id=librarian.id,
            ),
        ]
    )

    # --------------------------- Notifications -----------------------------
    db.add_all(
        [
            Notification(
                user_id=member.id,
                type="loan",
                title="Book checked out",
                message=f"'{loan_1984.book.title if loan_1984.book else '1984'}' is due in 14 days.",
            ),
            Notification(
                user_id=member.id,
                type="loan",
                title="Book overdue",
                message="'Clean Code' is overdue. Return it to avoid an additional fine.",
            ),
            Notification(
                user_id=john.id,
                type="reservation",
                title="Reserved book is ready",
                message="'The Hobbit' is waiting for you. Pick it up within 3 days.",
            ),
        ]
    )

    # ------------------------------ Audit log ------------------------------
    db.add_all(
        [
            AuditLog(
                user_id=librarian.id,
                action="loan.checked_out",
                entity_type="loan",
                entity_id=str(loan_1984.id),
                details={
                    "book": "1984",
                    "member": member.full_name,
                    "due_date": loan_1984.due_date.isoformat(),
                },
                created_at=now - timedelta(days=5),
            ),
            AuditLog(
                user_id=admin.id,
                action="member.created",
                entity_type="member",
                entity_id=str(sara.id),
                details={
                    "name": sara.full_name,
                    "email": sara.email,
                    "role": "member",
                    "card": sara.library_card_number,
                },
                created_at=now - timedelta(days=120),
            ),
            AuditLog(
                user_id=librarian.id,
                action="book.created",
                entity_type="book",
                entity_id=str(by_title["Clean Code"].id),
                details={
                    "title": "Clean Code",
                    "isbn": "9780132350884",
                    "copies": 4,
                },
                created_at=now - timedelta(days=90),
            ),
            AuditLog(
                user_id=librarian.id,
                action="fine.paid",
                entity_type="fine",
                entity_id=str(paid_fine.id),
                details={
                    "member_id": john.id,
                    "amount": 2.5,
                    "channel": "desk",
                },
                created_at=now - timedelta(days=20),
            ),
            AuditLog(
                user_id=admin.id,
                action="membership.activated",
                entity_type="subscription",
                entity_id=str(priya.id),
                details={"tier": "premium", "amount": 9.99, "channel": "demo"},
                created_at=now - timedelta(days=42),
            ),
            AuditLog(
                user_id=librarian.id,
                action="event.created",
                entity_type="event",
                entity_id="1",
                details={
                    "title": "Author Talk: The Future of AI",
                    "capacity": 80,
                    "ticket_price": 5.0,
                },
                created_at=now - timedelta(days=28),
            ),
            AuditLog(
                user_id=member.id,
                action="room.booked",
                entity_type="room_booking",
                entity_id=str(room_booking.id),
                details={
                    "room": reading_room.name,
                    "member": member.full_name,
                    "start": room_booking.start_time.isoformat(),
                    "end": room_booking.end_time.isoformat(),
                    "total": 0,
                },
                created_at=now - timedelta(hours=6),
            ),
            AuditLog(
                user_id=admin.id,
                action="auth.login",
                entity_type="user",
                entity_id=str(admin.id),
                details={"email": admin.email, "role": "admin"},
                created_at=now - timedelta(hours=2),
            ),
        ]
    )

    db.commit()


if __name__ == "__main__":
    from database.session import SessionLocal, engine, Base
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        seed_database(session)
        print("Database seeded successfully.")
    finally:
        session.close()
