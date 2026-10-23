"""Browser smoke test for the Libra single-page app.

Requires Playwright (dev-only dependency) and Microsoft Edge or Google Chrome:

    .\\.venv\\Scripts\\python -m pip install playwright
    .\\.venv\\Scripts\\python tests\\ui_test.py

The script drives the real UI, checks responsive behaviour, saves regression
screenshots to docs/test-screenshots, and fails on uncaught JavaScript errors.
Documentation images are produced separately by tests/capture_screens.py.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parents[2] / "docs" / "test-screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def shot(page: Page, name: str, full_page: bool = True) -> None:
    """Capture a settled screenshot without transient toasts."""
    page.wait_for_timeout(550)
    page.evaluate("() => document.querySelector('#toast-root')?.replaceChildren()")
    page.wait_for_timeout(100)
    page.screenshot(path=str(SHOTS / name), full_page=full_page)
    print(f"[shot] {name}")


def visible(locator: Locator, label: str, timeout: int = 15000) -> None:
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report a useful failure
        raise AssertionError(f"expected {label} to be visible") from exc


def main() -> None:
    page_errors: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        def on_page_error(error) -> None:  # noqa: ANN001
            page_errors.append(str(error))

        def on_console(message) -> None:  # noqa: ANN001
            if message.type != "error":
                return
            text = message.text
            if "Failed to load resource" in text or "ERR_" in text:
                return  # remote fonts / book covers may be unavailable offline
            console_errors.append(text)

        page.on("pageerror", on_page_error)
        page.on("console", on_console)

        # ----------------------------- login ------------------------------
        page.goto(BASE, wait_until="domcontentloaded")
        visible(page.locator("#auth-screen"), "login screen")
        page.wait_for_timeout(1500)
        assert page.locator("#login-form").is_visible()
        assert page.locator(".auth-tab").count() == 2
        assert page.evaluate(
            "() => document.querySelector('#auth-screen').classList.contains('auth-visible')"
        )
        assert "authCardIn" in page.evaluate(
            "() => getComputedStyle(document.querySelector('#auth-card')).animationName"
        )
        shot(page, "01-login.png")

        page.locator('[data-demo="admin"]').click()
        assert page.input_value("#login-email") == "admin@library.com"
        assert page.input_value("#login-password") == "Admin@123"
        page.locator("#login-password").press("Enter")
        page.locator("#auth-card.is-success").wait_for(state="visible", timeout=5000)
        visible(page.locator("#auth-transition"), "login transition")
        visible(page.locator("#app-shell"), "application shell")
        page.wait_for_function(
            "() => document.querySelector('#view h1')?.textContent.includes('Library overview')"
        )
        page.wait_for_timeout(1200)
        assert page.locator("#view .stat-card").count() == 4
        assert page.locator("#view .chart-col").count() == 6
        assert page.locator("#view table tbody tr").count() >= 1
        assert page.locator(".sidebar .nav-item[data-nav='members']").is_visible()
        assert page.locator(".sidebar .nav-item[data-nav='audit']").is_visible()
        shot(page, "02-admin-dashboard.png")
        print("[ok] staff login + dashboard")

        # -------------------------- PWA installability --------------------
        manifest = page.evaluate(
            """async () => {
                const response = await fetch('/manifest.webmanifest');
                return {
                    type: response.headers.get('content-type') || '',
                    body: await response.json(),
                };
            }"""
        )
        assert "manifest" in manifest["type"].lower(), manifest["type"]
        assert manifest["body"]["name"].startswith("Libra")
        assert manifest["body"]["icons"] and manifest["body"]["shortcuts"]

        worker_source = page.evaluate(
            "async () => (await fetch('/service-worker.js')).text()"
        )
        assert "libra-shell" in worker_source

        scope = None
        for _ in range(30):
            scope = page.evaluate(
                """async () => {
                    if (!('serviceWorker' in navigator)) return null;
                    const registration = await navigator.serviceWorker.getRegistration();
                    return registration ? registration.scope : null;
                }"""
            )
            if scope:
                break
            page.wait_for_timeout(250)
        assert scope, "service worker did not register"

        shortcut_page = context.new_page()
        shortcut_page.goto(f"{BASE}/?view=browse", wait_until="domcontentloaded")
        visible(shortcut_page.locator("#books-grid .book-card"), "PWA shortcut browse view")
        shortcut_page.close()
        print("[ok] PWA manifest, service worker and shortcut entry")

        # -------------------------- theme toggle --------------------------
        before = page.get_attribute("html", "data-theme")
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(400)
        after = page.get_attribute("html", "data-theme")
        assert after and after != before
        shot(page, "03-dark-dashboard.png")
        page.locator("#theme-toggle").click()
        print("[ok] light/dark theme")

        # ------------------------- notifications -------------------------
        page.locator("#notif-btn").click()
        visible(page.locator("#notif-panel"), "notification panel")
        assert page.locator("#notif-panel").inner_text().strip()
        if page.locator("[data-action='mark-all-notifs']").count():
            page.locator("[data-action='mark-all-notifs']").click()
            page.wait_for_timeout(800)
        page.mouse.click(20, 240)
        print("[ok] notifications panel")

        # ---------------------------- browse -----------------------------
        page.locator(".sidebar .nav-item[data-nav='browse']").click()
        visible(page.locator("#books-grid .book-card"), "book cards")
        assert page.locator("#books-grid .book-card").count() >= 8
        assert "titles" in page.locator("#browse-meta").inner_text()
        shot(page, "04-browse.png")
        print("[ok] catalog browse")

        page.fill("#browse-search", "Sapiens")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#books-grid .book-title')]"
            ".some(el => el.textContent.includes('Sapiens'))"
        )
        page.wait_for_timeout(500)
        shot(page, "05-search.png")

        page.fill("#browse-search", "Pride and Prejudice")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#books-grid .book-title')]"
            ".some(el => el.textContent.includes('Pride and Prejudice'))"
        )
        page.locator("#books-grid .book-card .cover").first.click()
        visible(page.locator("#modal-root .modal"), "book details modal")
        page.wait_for_timeout(700)
        assert page.locator("#modal-root .modal h2").inner_text().strip()
        assert page.locator("#modal-root a[href*='gutenberg.org']").count() == 1
        shot(page, "06-book-modal.png")
        page.keyboard.press("Escape")
        page.locator("#modal-root .modal").wait_for(state="detached")
        page.fill("#browse-search", "")
        page.wait_for_timeout(800)
        print("[ok] book details modal + digital edition")

        # ------------------------- reading shelves ------------------------
        page.fill("#browse-search", "Pride and Prejudice")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#books-grid .book-title')]"
            ".some(el => el.textContent.includes('Pride and Prejudice'))"
        )
        page.wait_for_timeout(350)
        page.locator("#books-grid .book-card .shelf-pin").first.click()
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('Want to read'))"
        )
        page.locator(".sidebar .nav-item[data-nav='shelves']").click()
        visible(page.locator("#view .shelf-entry"), "saved shelf entry")
        assert "Pride and Prejudice" in page.locator("#view .shelf-entry").first.inner_text()
        page.locator("#view .shelf-entry [data-action='set-shelf'][data-shelf='reading']").first.click()
        page.wait_for_function(
            "() => document.querySelector('#view .shelf-entry')?.classList.contains('reading')"
        )
        page.wait_for_timeout(500)
        assert page.locator("#view .goal-hero").is_visible()
        page.locator("[data-action='edit-goal']").first.click()
        visible(page.locator("#goal-form"), "reading goal form")
        page.keyboard.press("Escape")
        page.locator("#modal-root .modal").wait_for(state="detached")
        shot(page, "06b-shelves.png")
        print("[ok] personal shelves, progress and reading goal UI")

        # ---------------------------- members ----------------------------
        page.locator(".sidebar .nav-item[data-nav='members']").click()
        visible(page.locator("#view table tbody tr"), "member rows")
        assert page.locator("#view table tbody tr").count() >= 4
        shot(page, "07-members.png")

        page.locator("[data-action='new-member']").click()
        visible(page.locator("#member-form"), "add member form")
        suffix = uuid.uuid4().hex[:6]
        page.fill("#member-form input[name='full_name']", f"UI Tester {suffix}")
        page.fill("#member-form input[name='email']", f"ui.{suffix}@library.com")
        page.fill("#member-form input[name='password']", "UITest@123")
        page.locator("#member-form button[type='submit']").click()
        page.locator("#modal-root .modal").wait_for(state="detached", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('Account created'))"
        )
        page.wait_for_timeout(600)
        shot(page, "08-member-created.png")
        print("[ok] create member through the UI")

        # ---------------------- smart catalog assist ----------------------
        page.locator(".sidebar .nav-item[data-nav='browse']").click()
        visible(page.locator("#books-grid .book-card"), "book cards before adding")
        page.locator("[data-action='new-book']").click()
        visible(page.locator("#book-form"), "add book form")
        page.fill("#book-form input[name='title']", "Artificial Intelligence for Libraries")
        page.locator("[data-action='suggest-book']").click()
        page.wait_for_function(
            "() => document.querySelector('#book-form [name=tags]').value.includes('technology')"
        )
        suggested_tags = page.input_value("#book-form [name='tags']")
        suggested_category = page.input_value("#book-form [name='category_id']")
        assert suggested_tags and suggested_category
        page.keyboard.press("Escape")
        page.locator("#modal-root .modal").wait_for(state="detached")
        print("[ok] smart catalog suggestion fills metadata")

        # --------------------------- finance/events ----------------------
        page.locator(".sidebar .nav-item[data-nav='payments']").click()
        visible(page.locator("#view h1"), "finance view")
        page.wait_for_timeout(900)
        shot(page, "09-finance.png")

        page.locator(".sidebar .nav-item[data-nav='events']").click()
        visible(page.locator("#view .event-card"), "event cards")
        assert page.locator("#view .event-card").count() >= 1
        shot(page, "10-events.png")
        print("[ok] finance + events views")

        # ----------------------------- spaces -----------------------------
        page.locator(".sidebar .nav-item[data-nav='spaces']").click()
        visible(page.locator("#view .space-card"), "room cards")
        assert page.locator("#view .space-card").count() >= 4
        shot(page, "11-spaces.png")

        page.locator("[data-action='book-room']").first.click()
        visible(page.locator("#room-form"), "room booking form")
        start = (datetime.now().astimezone() + timedelta(days=31)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        page.fill("#room-form input[name='start_time']", start.strftime("%Y-%m-%dT%H:%M"))
        page.fill("#room-form input[name='end_time']", end.strftime("%Y-%m-%dT%H:%M"))
        page.fill("#room-form input[name='notes']", "UI test booking")
        page.locator("#room-form button[type='submit']").click()
        page.locator("#modal-root .modal").wait_for(state="detached", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('space is booked'))"
        )
        page.wait_for_timeout(700)
        shot(page, "12-spaces-booked.png")

        booking_row = page.locator(".booking-row", has_text="UI test booking").first
        booking_row.wait_for(state="visible")
        booking_row.locator("[data-action='cancel-room-booking']").click()
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('Booking cancelled'))"
        )
        print("[ok] room booking + cancellation")

        # ----------------------------- audit ------------------------------
        page.locator(".sidebar .nav-item[data-nav='audit']").click()
        visible(page.locator("#view h1"), "audit view")
        page.wait_for_function(
            "() => document.querySelector('#view h1')?.textContent.includes('Audit trail')"
        )
        visible(page.locator(".audit-table tbody tr"), "audit rows")
        assert page.locator(".audit-table tbody tr").count() >= 1
        audit_text = page.locator(".audit-table").inner_text().lower()
        assert "login" in audit_text or "created" in audit_text
        shot(page, "13-audit.png")
        print("[ok] audit trail view")

        # ---------------------------- profile ----------------------------
        page.locator("#avatar-btn").click()
        visible(page.locator("#avatar-menu"), "avatar menu")
        page.locator("#avatar-menu [data-view='profile']").click()
        visible(page.locator("#profile-form"), "profile form")
        shot(page, "14-profile.png")
        print("[ok] profile view")

        # ----------------------------- logout ----------------------------
        page.locator("#sidebar-logout").click()
        visible(page.locator("#logout-overlay"), "logout overlay")
        shot(page, "15-logout.png", full_page=False)
        visible(page.locator("#auth-screen"), "login screen after logout")
        assert page.locator("#login-form").is_visible()
        print("[ok] animated logout")

        # ------------------------- member experience ---------------------
        page.locator('[data-demo="member"]').click()
        page.locator("#login-submit").click()
        visible(page.locator("#app-shell"), "member application")
        page.wait_for_function("() => document.querySelector('#view .hero')")
        page.wait_for_timeout(1100)
        assert "read" in page.locator("#view .hero h1").inner_text().lower()
        assert not page.locator(".sidebar .nav-item[data-nav='members']").is_visible()
        shot(page, "16-member-dashboard.png")
        print("[ok] member dashboard + role-based navigation")

        # --------------------------- responsive --------------------------
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(700)
        assert page.locator(".mobile-nav").is_visible()
        assert not page.locator(".sidebar").is_visible()
        assert page.locator(".mobile-nav [data-nav='spaces']").is_visible()
        page.locator(".mobile-nav [data-nav='browse']").click()
        visible(page.locator("#books-grid .book-card"), "mobile book cards")
        columns = page.locator("#books-grid").evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns"
        )
        assert len(columns.split()) == 2, columns
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 1, f"mobile horizontal overflow: {overflow}px"
        shot(page, "17-mobile-browse.png", full_page=False)

        page.locator(".mobile-nav [data-nav='shelves']").click()
        visible(page.locator("#view .shelf-entry"), "mobile shelves")
        assert page.locator("#view .goal-hero").is_visible()
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 1, f"mobile shelves overflow: {overflow}px"
        shot(page, "17b-mobile-shelves.png", full_page=False)

        page.locator(".mobile-nav [data-nav='profile']").click()
        visible(page.locator("#profile-form"), "mobile profile")
        shot(page, "18-mobile-profile.png", full_page=False)
        print("[ok] mobile layout + bottom navigation")

        context.close()
        browser.close()

    if page_errors:
        print("Uncaught JavaScript errors:")
        for item in page_errors:
            print("  -", item)
        sys.exit(1)
    if console_errors:
        print("Console errors:")
        for item in console_errors:
            print("  -", item)
        sys.exit(1)

    print("\nUI TEST PASSED")


if __name__ == "__main__":
    main()
