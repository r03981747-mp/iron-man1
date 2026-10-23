"""End-to-end smoke test for the Libra API.

Run the API first, then execute this file from the backend directory:

    .\\.venv\\Scripts\\python tests\\smoke_test.py

The script exercises the real HTTP API with the seeded demo accounts. It is
idempotent for reads, and uses unique emails/ISBNs for write tests so it can be
run repeatedly against the same database.
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

ROOT = "http://127.0.0.1:8000"
BASE = f"{ROOT}/api/v1"
client = httpx.Client(timeout=30.0)


def fail(message: str) -> None:
    print(f"\n[FAIL] {message}")
    sys.exit(1)


def expect(response: httpx.Response, code: int = 200, label: str = ""):
    if response.status_code != code:
        fail(
            f"{label or response.request.method + ' ' + str(response.request.url)} "
            f"returned {response.status_code}\n{response.text[:1500]}"
        )
    return response.json() if response.content else None


def login(email: str, password: str) -> dict:
    return expect(
        client.post(f"{BASE}/auth/login", json={"email": email, "password": password}),
        label=f"login {email}",
    )


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def run() -> None:
    health = expect(httpx.get(f"{ROOT}/api/health", timeout=10), label="health")
    assert health["status"] == "ok"
    assert "libra" in health["service"].lower()
    print("[ok] health", health)

    # ------------------------------ staff ---------------------------------
    admin = login("admin@library.com", "Admin@123")
    staff = auth_headers(admin["access_token"])
    me = expect(client.get(f"{BASE}/auth/me", headers=staff), label="admin me")
    assert me["role"] == "admin" and me["email"] == "admin@library.com"
    print("[ok] admin login", me["full_name"], me["role"])

    books = expect(client.get(f"{BASE}/books", params={"page_size": 100}))
    assert books["total"] >= 20, books["total"]
    print("[ok] catalog", books["total"], "books")

    categories = expect(client.get(f"{BASE}/catalog/categories"))
    authors = expect(client.get(f"{BASE}/catalog/authors"))
    branches = expect(client.get(f"{BASE}/catalog/branches"))
    publishers = expect(client.get(f"{BASE}/catalog/publishers"))
    assert categories and authors and branches and publishers
    print(
        "[ok] reference data",
        len(categories),
        "categories,",
        len(authors),
        "authors,",
        len(branches),
        "branches",
    )

    dashboard = expect(client.get(f"{BASE}/analytics/dashboard", headers=staff))
    totals = dashboard["totals"]
    for key in ("books", "members", "active_loans"):
        assert key in totals, key
    assert len(dashboard["monthly"]) == 6
    print(
        "[ok] dashboard",
        totals["books"],
        "books,",
        totals["members"],
        "members,",
        totals["active_loans"],
        "active loans",
    )

    revenue = expect(client.get(f"{BASE}/analytics/revenue", headers=staff))
    popular = expect(client.get(f"{BASE}/analytics/popular-books", headers=staff))
    assert isinstance(revenue, dict) and isinstance(popular, list)
    print("[ok] analytics revenue + popular books")

    members = expect(
        client.get(f"{BASE}/members", params={"role": "member", "limit": 200}, headers=staff)
    )
    assert len(members) >= 4
    member_stats = expect(client.get(f"{BASE}/members/stats/summary", headers=staff))
    assert member_stats["total_members"] >= 4
    print("[ok] members", len(members), "listed; summary", member_stats)

    audit = expect(
        client.get(f"{BASE}/audit", params={"limit": 50}, headers=staff),
        label="audit list",
    )
    assert audit and any(entry["action"] == "auth.login" for entry in audit)
    print("[ok] audit ledger", len(audit), "entries; staff access")

    loans = expect(client.get(f"{BASE}/loans", headers=staff))
    reservations = expect(client.get(f"{BASE}/reservations", headers=staff))
    fines = expect(client.get(f"{BASE}/fines", headers=staff))
    events = expect(client.get(f"{BASE}/events"))
    assert events["total"] >= 4
    print(
        "[ok] circulation",
        loans["total"],
        "loans,",
        len(reservations),
        "reservations,",
        len(fines),
        "fines,",
        events["total"],
        "events",
    )

    # ------------------------- create member ------------------------------
    suffix = uuid.uuid4().hex[:8]
    email = f"smoke.{suffix}@library.com"
    member = expect(
        client.post(
            f"{BASE}/members",
            headers=staff,
            json={
                "full_name": "Smoke Tester",
                "email": email,
                "password": "Smoke@12345",
                "phone": "+91 90000 00000",
                "role": "member",
            },
        ),
        201,
        "create member",
    )
    assert member["library_card_number"]
    duplicate = client.post(
        f"{BASE}/members",
        headers=staff,
        json={
            "full_name": "Smoke Tester",
            "email": email,
            "password": "Smoke@12345",
            "role": "member",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    print("[ok] member created", member["full_name"], member["library_card_number"])

    member_audit = expect(
        client.get(
            f"{BASE}/audit",
            params={"action": "member.created", "limit": 50},
            headers=staff,
        ),
        label="member audit entry",
    )
    assert any(entry["entity_id"] == str(member["id"]) for entry in member_audit)
    print("[ok] member creation recorded in the audit trail")

    # --------------------------- create book ------------------------------
    isbn = f"978{random.randint(1000000000, 9999999999)}"
    book = expect(
        client.post(
            f"{BASE}/books",
            headers=staff,
            json={
                "title": f"Smoke Test Book {suffix}",
                "isbn": isbn,
                "author_id": authors[0]["id"],
                "category_id": categories[0]["id"],
                "publication_year": 2026,
                "total_copies": 2,
                "book_format": "paperback",
                "description": "A temporary title created by the smoke test.",
            },
        ),
        201,
        "create book",
    )
    assert book["available_copies"] == 2
    copies = expect(client.get(f"{BASE}/books/{book['id']}/copies"))
    assert len(copies) == 2, f"expected 2 auto-created copies, got {len(copies)}"
    duplicate_book = client.post(
        f"{BASE}/books",
        headers=staff,
        json={
            "title": "Duplicate ISBN",
            "isbn": isbn,
            "total_copies": 1,
        },
    )
    assert duplicate_book.status_code == 409, duplicate_book.text
    print("[ok] book created with", len(copies), "copies; duplicate ISBN rejected")

    suggestion = expect(
        client.post(
            f"{BASE}/books/suggest",
            headers=staff,
            json={
                "title": "Artificial Intelligence for Libraries",
                "author_name": "Ada Example",
                "description": "A practical guide to algorithms, data and software.",
            },
        ),
        label="catalog suggestion",
    )
    assert suggestion["category"] == "Technology", suggestion
    assert suggestion["confidence"] >= 80 and suggestion["tags"]
    print("[ok] smart catalog suggestion", suggestion["category"], suggestion["tags"])

    # ------------------------- checkout & return --------------------------
    loan = expect(
        client.post(
            f"{BASE}/loans",
            headers=staff,
            json={"book_id": book["id"], "member_id": member["id"], "days": 14},
        ),
        201,
        "checkout",
    )
    assert loan["status"] == "active" and loan["copy_barcode"]
    reference = expect(client.get(f"{BASE}/books/{book['id']}"))
    assert reference["available_copies"] == 1

    renewed = expect(
        client.post(f"{BASE}/loans/{loan['id']}/renew", headers=staff), label="renew"
    )
    assert renewed["renewed_count"] == 1
    returned = expect(
        client.post(f"{BASE}/loans/{loan['id']}/return", headers=staff), label="return"
    )
    assert returned["loan"]["status"] == "returned"
    reference = expect(client.get(f"{BASE}/books/{book['id']}"))
    assert reference["available_copies"] == 2
    print("[ok] checkout, renew and return all work")

    # ---------------------------- member flow -----------------------------
    member_tokens = login("member@library.com", "Member@123")
    member_headers = auth_headers(member_tokens["access_token"])
    member_me = expect(client.get(f"{BASE}/auth/me", headers=member_headers))
    assert member_me["role"] == "member"

    review = expect(
        client.post(
            f"{BASE}/books/{book['id']}/reviews",
            headers=member_headers,
            json={"rating": 5, "comment": "A concise smoke-test review."},
        ),
        201,
        "create review",
    )
    assert review["rating"] == 5
    reviewed = expect(client.get(f"{BASE}/books/{book['id']}"))
    assert reviewed["review_count"] == 1 and reviewed["average_rating"] == 5.0
    updated_review = expect(
        client.post(
            f"{BASE}/books/{book['id']}/reviews",
            headers=member_headers,
            json={"rating": 4, "comment": "Updated smoke-test review."},
        ),
        201,
        "update review",
    )
    assert updated_review["rating"] == 4
    reviewed = expect(client.get(f"{BASE}/books/{book['id']}"))
    assert reviewed["review_count"] == 1 and reviewed["average_rating"] == 4.0
    print("[ok] reviews create and update with aggregate counts")
    my_dashboard = expect(client.get(f"{BASE}/analytics/me", headers=member_headers))
    assert "current_loans" in my_dashboard
    notifications = expect(client.get(f"{BASE}/notifications", headers=member_headers))
    print(
        "[ok] member login",
        member_me["full_name"],
        "| notifications:",
        len(notifications),
    )

    # ------------------------- reading shelves ----------------------------
    shelves = expect(client.get(f"{BASE}/shelves/me", headers=member_headers))
    assert set(shelves["counts"]) == {"want_to_read", "reading", "finished"}
    assert shelves["goal"]["target"] >= 1
    original_goal = shelves["goal"]["target"]
    original_finished = shelves["goal"]["finished"]
    print("[ok] shelves loaded", shelves["counts"], "goal", shelves["goal"])

    saved = expect(
        client.put(
            f"{BASE}/shelves/me/{book['id']}",
            headers=member_headers,
            json={"status": "want_to_read"},
        ),
        label="save shelf",
    )
    assert saved["status"] == "want_to_read" and saved["progress"] == 0

    reading = expect(
        client.put(
            f"{BASE}/shelves/me/{book['id']}",
            headers=member_headers,
            json={"status": "reading", "progress": 42},
        ),
        label="reading shelf",
    )
    assert reading["status"] == "reading" and reading["progress"] == 42

    finished = expect(
        client.put(
            f"{BASE}/shelves/me/{book['id']}",
            headers=member_headers,
            json={"status": "finished"},
        ),
        label="finished shelf",
    )
    assert finished["status"] == "finished" and finished["progress"] == 100
    updated_goal = expect(client.get(f"{BASE}/shelves/me", headers=member_headers))
    assert updated_goal["goal"]["finished"] == original_finished + 1

    goal = expect(
        client.put(
            f"{BASE}/shelves/me/goal",
            headers=member_headers,
            json={"target": original_goal + 3},
        ),
        label="update reading goal",
    )
    assert goal["target"] == original_goal + 3
    expect(
        client.put(
            f"{BASE}/shelves/me/goal",
            headers=member_headers,
            json={"target": original_goal},
        ),
        label="restore reading goal",
    )

    removed = expect(
        client.delete(f"{BASE}/shelves/me/{book['id']}", headers=member_headers),
        label="remove shelf",
    )
    assert "removed" in removed["message"].lower()
    assert client.delete(
        f"{BASE}/shelves/me/{book['id']}", headers=member_headers
    ).status_code == 404
    print("[ok] shelf save, progress, finish, goal and removal")

    my_loans = expect(client.get(f"{BASE}/loans", headers=member_headers))
    overdue = [item for item in my_loans["items"] if item["status"] == "overdue"]
    fine_amount = 0.0
    if overdue:
        result = expect(
            client.post(f"{BASE}/loans/{overdue[0]['id']}/return", headers=member_headers),
            label="overdue return",
        )
        fine_amount = result["fine_amount"]
        assert fine_amount > 0
        print("[ok] overdue return generated a", f"${fine_amount:.2f}", "fine")

    my_fines = expect(client.get(f"{BASE}/fines", headers=member_headers))
    unpaid = [fine for fine in my_fines if fine["status"] == "unpaid"]
    if unpaid:
        payment = expect(
            client.post(
                f"{BASE}/payments/fines/checkout",
                headers=member_headers,
                json={
                    "fine_ids": [unpaid[0]["id"]],
                    "description": "Smoke test fine payment",
                },
            ),
            label="pay fine",
        )
        assert payment["mock"] is True and not payment["url"]
        my_fines = expect(client.get(f"{BASE}/fines", headers=member_headers))
        assert all(fine["status"] != "unpaid" for fine in my_fines if fine["id"] == unpaid[0]["id"])
        print("[ok] fine paid in development mode")

    subscription = expect(
        client.post(
            f"{BASE}/payments/subscribe",
            headers=member_headers,
            json={"tier": "premium"},
        ),
        label="subscribe",
    )
    assert subscription["mock"] is True
    upgraded = expect(client.get(f"{BASE}/auth/me", headers=member_headers))
    assert upgraded["membership_tier"] == "premium"
    subscriptions = expect(
        client.get(f"{BASE}/payments/subscriptions/me", headers=member_headers)
    )
    assert any(item["status"] == "active" for item in subscriptions)
    print("[ok] premium membership activated in development mode")

    my_payments = expect(client.get(f"{BASE}/payments", headers=member_headers))
    assert any(item["status"] == "succeeded" for item in my_payments)
    print("[ok] payment history", len(my_payments), "records")

    # --------------------------- event tickets ----------------------------
    # Use the freshly created member so repeated smoke runs never collide with
    # registrations left behind by earlier runs.
    event_tokens = login(email, "Smoke@12345")
    event_headers = auth_headers(event_tokens["access_token"])
    fresh_events = expect(client.get(f"{BASE}/events"))
    free_event = next(
        (
            item
            for item in fresh_events["items"]
            if item["ticket_price"] == 0 and item["registered_count"] < item["capacity"]
        ),
        None,
    )
    registered_ids = set()
    if free_event:
        registration = expect(
            client.post(
                f"{BASE}/events/{free_event['id']}/register", headers=event_headers
            ),
            label="free event registration",
        )
        assert registration["registration"]["event_id"] == free_event["id"]
        registered_ids.add(free_event["id"])
        print("[ok] free event registration")

    paid_event = next(
        (
            item
            for item in fresh_events["items"]
            if item["ticket_price"] > 0 and item["id"] not in registered_ids
        ),
        None,
    )
    if paid_event:
        registration = expect(
            client.post(
                f"{BASE}/events/{paid_event['id']}/register", headers=event_headers
            ),
            label="paid event registration",
        )
        assert registration["mock"] is True
        assert registration["payment_id"]
        print("[ok] paid event ticket created in development mode")

    # ----------------------------- profile --------------------------------
    profile = expect(
        client.put(
            f"{BASE}/auth/me",
            headers=member_headers,
            json={"phone": member_me.get("phone") or "+91 90000 11111"},
        ),
        label="profile update",
    )
    assert profile["full_name"] == member_me["full_name"]
    print("[ok] profile update")

    # --------------------------- spaces / rooms ---------------------------
    rooms = expect(client.get(f"{BASE}/rooms", headers=member_headers), label="rooms")
    assert len(rooms) >= 4 and all(room["amenities"] for room in rooms)
    room = rooms[1]
    slot_start = (
        datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        + timedelta(days=random.randint(40, 90), hours=random.randint(0, 6))
    )
    slot_end = slot_start + timedelta(hours=1)
    room_booking = expect(
        client.post(
            f"{BASE}/rooms/{room['id']}/bookings",
            headers=member_headers,
            json={
                "start_time": slot_start.isoformat(),
                "end_time": slot_end.isoformat(),
                "notes": "Smoke test study session",
            },
        ),
        201,
        "book room",
    )
    assert room_booking["room_name"] == room["name"]
    duplicate_booking = client.post(
        f"{BASE}/rooms/{room['id']}/bookings",
        headers=member_headers,
        json={
            "start_time": slot_start.isoformat(),
            "end_time": slot_end.isoformat(),
        },
    )
    assert duplicate_booking.status_code == 409, duplicate_booking.text
    my_room_bookings = expect(
        client.get(f"{BASE}/rooms/bookings", headers=member_headers),
        label="room bookings",
    )
    assert any(item["id"] == room_booking["id"] for item in my_room_bookings)
    cancelled = expect(
        client.post(
            f"{BASE}/rooms/bookings/{room_booking['id']}/cancel",
            headers=member_headers,
        ),
        label="cancel room booking",
    )
    assert cancelled["status"] == "cancelled"
    print("[ok] room booking, conflict protection and cancellation")

    # --------------------------- access control ---------------------------
    unauthorized = client.get(f"{BASE}/members")
    assert unauthorized.status_code == 401, unauthorized.text
    forbidden = client.get(f"{BASE}/analytics/dashboard", headers=member_headers)
    assert forbidden.status_code == 403, forbidden.text
    denied_audit = client.get(f"{BASE}/audit", headers=member_headers)
    assert denied_audit.status_code == 403, denied_audit.text
    print("[ok] access control enforced (members, analytics, audit)")

    # --------------------------- frontend shell ---------------------------
    page = client.get(f"{ROOT}/")
    assert page.status_code == 200 and "Libra" in page.text
    script = client.get(f"{ROOT}/app.js")
    assert script.status_code == 200 and "RENDERERS" in script.text

    manifest = client.get(f"{ROOT}/manifest.webmanifest")
    assert manifest.status_code == 200 and "Libra" in manifest.text
    assert "manifest" in manifest.headers.get("content-type", "")
    worker = client.get(f"{ROOT}/service-worker.js")
    assert worker.status_code == 200 and "libra-shell" in worker.text
    icon = client.get(f"{ROOT}/icon-192.png")
    assert icon.status_code == 200 and icon.headers.get("content-type", "").startswith("image/png")
    shortcut = client.get(f"{ROOT}/?view=browse")
    assert shortcut.status_code == 200 and "Libra" in shortcut.text

    digital = next((item for item in books["items"] if item.get("digital_file_url")), None)
    assert digital is not None, "expected at least one seeded public-domain digital edition"
    print("[ok] frontend, PWA assets, shortcut entry and digital editions served")

    expect(client.post(f"{BASE}/auth/logout", headers=member_headers), label="logout")
    expect(client.post(f"{BASE}/auth/logout", headers=staff), label="admin logout")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as exc:
        fail(f"assertion failed: {exc}")
    except httpx.HTTPError as exc:
        fail(f"HTTP error: {exc}")
