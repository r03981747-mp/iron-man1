"""Offline test for the hosted Stripe Checkout return path.

This monkeypatches the Stripe SDK, so it never contacts Stripe and never needs
real keys. It exercises the same endpoint the browser uses for fine payments:

1. create a hosted Checkout Session for an unpaid fine,
2. retrieve/confirm the session on return, and
3. verify the fine and payment are settled exactly once.

Run from ``backend/``:

    .\\.venv\\Scripts\\python tests\\stripe_flow_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_FILE = BACKEND / "stripe_flow_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_offline_fake"
os.environ["ENVIRONMENT"] = "development"

if DB_FILE.exists():
    DB_FILE.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import api.routes.payments as payments  # noqa: E402
from api.main import app  # noqa: E402

BASE = "/api/v1"


class FakeSession:
    def __init__(self, **kwargs) -> None:
        self._data = {
            "id": "cs_test_offline_123",
            "url": "https://checkout.stripe.test/cs_test_offline_123",
            "status": "complete",
            "payment_status": "paid",
            "mode": "payment",
            "amount_total": 175,
            "currency": "usd",
            "metadata": kwargs.get("metadata", {}),
        }

    def to_dict(self) -> dict:
        return self._data

    def __getattr__(self, name: str):
        try:
            return self._data[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc


def main() -> None:
    with TestClient(app) as client:
        # Find a demo reader who actually has an unpaid fine in the seed.
        member = None
        login = None
        for email in (
            "sara@library.com",
            "priya@library.com",
            "john@library.com",
            "member@library.com",
        ):
            response = client.post(
                f"{BASE}/auth/login",
                json={"email": email, "password": "Member@123"},
            )
            if response.status_code != 200:
                continue
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            fines = client.get(f"{BASE}/fines", headers=headers).json()
            unpaid = [fine for fine in fines if fine["status"] == "unpaid"]
            if unpaid:
                member = (email, headers, unpaid[0])
                login = response
                break
        assert member, "seed did not provide an unpaid member fine"
        email, headers, fine = member

        me = client.get(f"{BASE}/auth/me", headers=headers).json()
        payment_id = None
        original_stripe = payments.stripe
        original_configure = payments._configure_stripe

        def fake_create(**kwargs):
            nonlocal payment_id
            # The route creates the DB row first; read its id from the metadata.
            payment_id = int(kwargs["metadata"]["payment_id"])
            return FakeSession(**kwargs)

        def fake_retrieve(session_id: str):
            return FakeSession(
                metadata={
                    "payment_id": str(payment_id),
                    "member_id": str(me["id"]),
                    "type": "fine",
                }
            )

        class FakeStripe:
            checkout = SimpleNamespace(
                Session=SimpleNamespace(
                    create=fake_create,
                    retrieve=fake_retrieve,
                )
            )

        payments.stripe = FakeStripe()
        payments._configure_stripe = lambda: True
        try:
            checkout = client.post(
                f"{BASE}/payments/fines/checkout",
                headers=headers,
                json={
                    "fine_ids": [fine["id"]],
                    "description": "Offline Stripe fine test",
                },
            )
            assert checkout.status_code == 200, checkout.text
            payload = checkout.json()
            assert payload["mock"] is False and payload["url"].startswith("https://")
            assert payment_id, "checkout did not create a payment"

            confirmed = client.post(
                f"{BASE}/payments/checkout/{payload['session_id']}/confirm",
                headers=headers,
            )
            assert confirmed.status_code == 200, confirmed.text
            assert "confirmed" in confirmed.json()["message"].lower()

            fines = client.get(f"{BASE}/fines", headers=headers).json()
            settled = next(item for item in fines if item["id"] == fine["id"])
            assert settled["status"] == "paid", settled

            payments_list = client.get(f"{BASE}/payments", headers=headers).json()
            payment = next(item for item in payments_list if item["id"] == payment_id)
            assert payment["status"] == "succeeded", payment

            # A duplicate return/webhook must not produce a second audit or error.
            duplicate = client.post(
                f"{BASE}/payments/checkout/{payload['session_id']}/confirm",
                headers=headers,
            )
            assert duplicate.status_code == 200, duplicate.text
            print(
                "[ok] Stripe Checkout fine flow:",
                email,
                f"paid ${float(fine['amount']):.2f}",
                "| payment",
                payment_id,
            )
        finally:
            payments.stripe = original_stripe
            payments._configure_stripe = original_configure

    from database.session import engine

    engine.dispose()
    if DB_FILE.exists():
        DB_FILE.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if DB_FILE.exists():
            DB_FILE.unlink()
        raise
