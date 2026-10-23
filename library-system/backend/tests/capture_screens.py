"""Capture the documentation screenshot set from a fresh demo database.

Run this against a pristine seed (delete ``backend/library.db`` and restart the
API first). It deliberately keeps the main staff views untouched, then creates a
realistic member and room booking for the two action screenshots.

    .\\.venv\\Scripts\\python tests\\capture_screens.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def shot(page: Page, name: str, full_page: bool = True) -> None:
    """Capture a settled screenshot without transient toasts."""
    page.wait_for_timeout(600)
    page.evaluate("() => document.querySelector('#toast-root')?.replaceChildren()")
    page.wait_for_timeout(100)
    page.screenshot(path=str(SHOTS / name), full_page=full_page)
    print(f"[shot] {name}")


def visible(locator: Locator, label: str, timeout: int = 15000) -> None:
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report a useful failure
        raise AssertionError(f"expected {label} to be visible") from exc


def nudge_images(page: Page) -> None:
    """Give remote Open Library covers a chance to finish loading."""
    page.wait_for_timeout(900)
    page.evaluate(
        """() => Promise.all([...document.images].map((img) => {
            if (img.complete) return Promise.resolve();
            return new Promise((resolve) => {
                img.addEventListener('load', resolve, { once: true });
                img.addEventListener('error', resolve, { once: true });
                setTimeout(resolve, 2500);
            });
        }))"""
    )


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
        assert page.locator(".auth-metrics strong").first.inner_text() == "20"
        shot(page, "01-login.png")

        page.locator('[data-demo="admin"]').click()
        page.locator("#login-submit").click()
        visible(page.locator("#app-shell"), "application shell")
        page.wait_for_function(
            "() => document.querySelector('#view h1')?.textContent.includes('Library overview')"
        )
        page.wait_for_timeout(1200)
        assert page.locator("#view .stat-card").count() == 4
        shot(page, "02-admin-dashboard.png")

        page.locator("#theme-toggle").click()
        page.wait_for_timeout(400)
        shot(page, "03-dark-dashboard.png")
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(300)

        # ---------------------------- catalog -----------------------------
        page.locator(".sidebar .nav-item[data-nav='browse']").click()
        visible(page.locator("#books-grid .book-card"), "book cards")
        nudge_images(page)
        shot(page, "04-browse.png")

        page.fill("#browse-search", "Sapiens")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#books-grid .book-title')]"
            ".some(el => el.textContent.includes('Sapiens'))"
        )
        page.wait_for_timeout(500)
        nudge_images(page)
        shot(page, "05-search.png")

        page.fill("#browse-search", "Pride and Prejudice")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#books-grid .book-title')]"
            ".some(el => el.textContent.includes('Pride and Prejudice'))"
        )
        nudge_images(page)
        page.locator("#books-grid .book-card .cover").first.click()
        visible(page.locator("#modal-root .modal"), "book details modal")
        page.wait_for_timeout(800)
        assert page.locator("#modal-root a[href*='gutenberg.org']").count() == 1
        shot(page, "06-book-modal.png")
        page.keyboard.press("Escape")
        page.locator("#modal-root .modal").wait_for(state="detached")
        page.fill("#browse-search", "")
        page.wait_for_timeout(800)

        # --------------------- staff views, before writes -----------------
        page.locator(".sidebar .nav-item[data-nav='members']").click()
        visible(page.locator("#view table tbody tr"), "member rows")
        assert page.locator("#view table tbody tr").count() == 4
        shot(page, "07-members.png")

        page.locator(".sidebar .nav-item[data-nav='payments']").click()
        visible(page.locator("#view h1"), "finance view")
        page.wait_for_timeout(900)
        shot(page, "09-finance.png")

        page.locator(".sidebar .nav-item[data-nav='events']").click()
        visible(page.locator("#view .event-card"), "event cards")
        nudge_images(page)
        shot(page, "10-events.png")

        page.locator(".sidebar .nav-item[data-nav='spaces']").click()
        visible(page.locator("#view .space-card"), "room cards")
        assert page.locator("#view .space-card").count() == 4
        columns = page.locator(".space-grid").evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns"
        )
        assert len(columns.split()) == 2, columns
        shot(page, "11-spaces.png")

        page.locator(".sidebar .nav-item[data-nav='audit']").click()
        visible(page.locator(".audit-table tbody tr"), "audit rows")
        page.wait_for_function(
            "() => document.querySelector('#view h1')?.textContent.includes('Audit trail')"
        )
        shot(page, "13-audit.png")

        page.locator("#avatar-btn").click()
        visible(page.locator("#avatar-menu"), "avatar menu")
        page.locator("#avatar-menu [data-view='profile']").click()
        visible(page.locator("#profile-form"), "profile form")
        shot(page, "14-profile.png")

        # ---------------------- deliberate demo writes --------------------
        page.locator(".sidebar .nav-item[data-nav='members']").click()
        visible(page.locator("#view table tbody tr"), "member rows again")
        page.locator("[data-action='new-member']").click()
        visible(page.locator("#member-form"), "add member form")
        page.fill("#member-form input[name='full_name']", "Maya Iyer")
        page.fill("#member-form input[name='email']", "maya.iyer@library.com")
        page.fill("#member-form input[name='password']", "Member@123")
        page.fill("#member-form input[name='phone']", "+91 98450 12034")
        page.locator("#member-form button[type='submit']").click()
        page.locator("#modal-root .modal").wait_for(state="detached", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('Account created'))"
        )
        page.wait_for_timeout(700)
        shot(page, "08-member-created.png")

        page.locator(".sidebar .nav-item[data-nav='spaces']").click()
        visible(page.locator("#view .space-card"), "room cards after member")
        page.locator("[data-action='book-room']").first.click()
        visible(page.locator("#room-form"), "room booking form")
        start = (datetime.now().astimezone() + timedelta(days=31)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        page.fill("#room-form input[name='start_time']", start.strftime("%Y-%m-%dT%H:%M"))
        page.fill("#room-form input[name='end_time']", end.strftime("%Y-%m-%dT%H:%M"))
        page.fill("#room-form input[name='notes']", "Book club prep with Maya")
        page.locator("#room-form button[type='submit']").click()
        page.locator("#modal-root .modal").wait_for(state="detached", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#toast-root .toast')]"
            ".some(t => t.textContent.includes('space is booked'))"
        )
        page.wait_for_timeout(700)
        shot(page, "12-spaces-booked.png")

        # ----------------------------- logout ----------------------------
        page.locator("#sidebar-logout").click()
        visible(page.locator("#logout-overlay"), "logout overlay")
        shot(page, "15-logout.png", full_page=False)
        visible(page.locator("#auth-screen"), "login screen after logout")

        # ------------------------- member experience ---------------------
        page.locator('[data-demo="member"]').click()
        page.locator("#login-submit").click()
        visible(page.locator("#app-shell"), "member application")
        page.wait_for_function("() => document.querySelector('#view .hero')")
        page.wait_for_timeout(1100)
        shoot_member_books = page.locator("#view .hero h1").inner_text().lower()
        assert "read" in shoot_member_books
        shot(page, "16-member-dashboard.png")

        page.locator(".sidebar .nav-item[data-nav='shelves']").click()
        visible(page.locator("#view .shelf-entry"), "member shelves")
        assert page.locator("#view .goal-hero").is_visible()
        assert page.locator("#view .shelf-tab").count() == 4
        nudge_images(page)
        shot(page, "16b-member-shelves.png")

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(700)
        assert page.locator(".mobile-nav").is_visible()
        assert not page.locator(".sidebar").is_visible()
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 1, f"mobile horizontal overflow: {overflow}px"
        page.locator(".mobile-nav [data-nav='browse']").click()
        visible(page.locator("#books-grid .book-card"), "mobile book cards")
        nudge_images(page)
        shot(page, "17-mobile-browse.png", full_page=False)

        page.locator(".mobile-nav [data-nav='shelves']").click()
        visible(page.locator("#view .shelf-entry"), "mobile shelves")
        assert page.locator("#view .goal-hero").is_visible()
        nudge_images(page)
        shot(page, "17b-mobile-shelves.png", full_page=False)

        page.locator(".mobile-nav [data-nav='profile']").click()
        visible(page.locator("#profile-form"), "mobile profile")
        shot(page, "18-mobile-profile.png", full_page=False)

        context.close()
        browser.close()

    if page_errors:
        raise SystemExit("Uncaught JavaScript errors:\n- " + "\n- ".join(page_errors))
    if console_errors:
        raise SystemExit("Console errors:\n- " + "\n- ".join(console_errors))

    print("\nSCREENSHOT CAPTURE PASSED")


if __name__ == "__main__":
    main()
