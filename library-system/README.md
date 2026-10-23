# Libra — Library OS

A complete, working library management system for the modern library: catalog and
inventory, circulation, personal reading shelves and annual goals, memberships, fines,
events, payments, analytics, audit logs and a responsive installable web app with
purposeful auth motion — all served by one FastAPI service.

Built with **Python 3.11+**, **FastAPI**, **SQLAlchemy 2**, **Pydantic v2**, and a
hand-crafted vanilla JavaScript single-page app. **SQLite is the zero-setup default**;
**PostgreSQL** is supported with one environment variable. Stripe is optional — without
keys, payments run in an instant development mode so every flow remains testable.

---

## Quick start (Windows)

```powershell
cd library-system
.\start.ps1
```

The script creates `backend\.venv`, installs dependencies, creates `backend\.env`
from the safe SQLite defaults, seeds a realistic demo library, and starts the server.

Open **http://localhost:8000** — interactive API docs live at
**http://localhost:8000/api/docs**.

### Manual start (any OS)

```bash
cd library-system/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional; SQLite defaults work without it
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The database file (`backend/library.db`) and demo data are created automatically on
first startup. Delete `backend/library.db` to reset to a pristine demo library.

### Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@library.com` | `Admin@123` |
| Librarian | `librarian@library.com` | `Librarian@123` |
| Member | `member@library.com` | `Member@123` |

Additional seeded readers: `priya@library.com`, `john@library.com`, `sara@library.com`
(all `Member@123`). The login screen also has one-tap demo chips for each role.

---

## What is implemented

### Catalog & inventory
- 20 seeded titles across fiction, history, science, technology, psychology and biography
- Search by title, author or ISBN; filter by category and format; sort by newest, title, rating or popularity
- Book detail view with cover, metadata, availability, reader reviews and ratings
- Multiple physical copies per title, each with a barcode, branch, condition, shelf location and status
- Add titles and copies from the staff UI; duplicate ISBN and barcode protection
- Digital-edition links for public-domain titles (Project Gutenberg), surfaced in the book detail modal

### Reading shelves & annual goal
- Private, member-owned shelves: **Want to read**, **Reading now** and **Finished**
- Save a title with one tap from any catalog card; manage the full shelf from the book modal
- Reading progress slider for titles in progress, plus one-click finish
- A dedicated **My shelves** view with shelf filters, counts and a personal goal ring
- Annual reading goal stored on the member profile and editable from the shelves page or the dashboard goal card
- Finished books count toward the goal automatically; no denormalized counter can drift
- Seeded shelves and goals make the member demo feel lived-in from the first login
- Reversible actions are recorded in the audit trail (`shelf.updated`, `shelf.removed`, `reading_goal.updated`)

### Circulation
- Checkout, renew and return with configurable loan periods and renewal limits
- Automatic overdue detection, daily fine calculation and fine records
- Availability accounting across copies and titles
- Reservations/holds with ready-for-pickup notification and expiry
- Member self-service borrowing and staff circulation desk workflows
- Belt-and-braces rules: active-loan limits, stock checks, outstanding-copy validation

### Members, roles & security
- Administrator, librarian and member roles with enforced API permissions
- Library cards, membership tiers (Basic, Student, Premium, Family), profiles
- Member creation/deactivation, role changes and tier changes by staff
- JWT access + refresh tokens, bcrypt password hashing (PBKDF2 fallback), password change flow
- Password show/hide controls with accessible labels and keyboard focus states
- Staggered login entrance, a signing-in progress state with spinner and success check, a book-cover transition into the app, and an animated “closing the cover” logout
- Enter submits the same animated flow as the Sign in button
- Reduced-motion alternatives for every auth animation, role-aware navigation and mobile layout

### Payments & memberships
- Hosted **Stripe Checkout** for fine payments, membership subscriptions and paid event tickets; Stripe handles cards and wallets such as Apple Pay and Google Pay when enabled on the account
- **Development mode** instantly settles payments when Stripe is not configured
- Return-page confirmation verifies a Checkout Session, so local test payments settle even before a webhook is configured
- Signed webhooks for `checkout.session.completed`, `checkout.session.expired`, `payment_intent.succeeded` and `invoice.paid`
- Subscription records, 30-day periods and first-invoice payment history in the finance view
- Full payment history for members and staff finance views

### Events, community & spaces
- Community calendar with capacity, ticket pricing, branch and registration tracking
- Free and paid event registration
- Staff event creation and registrations roster
- Study rooms, focus pods, a creative studio and a community room
- Member room booking with capacity, amenities, a four-hour limit and conflict protection
- Upcoming-booking list with cancellation for members and an all-member view for staff

### Smart catalog assist
- Staff-only “Suggest details” action in the add-book form
- Suggests a category, tags and a starter description from the title, author and description
- Runs as a transparent local keyword heuristic — no external AI provider, no hidden data sharing
- Every suggestion is editable before the record is saved

### Analytics & insight
- Staff dashboard: titles, copies, members, active/overdue loans, holds, revenue
- Six-month circulation and revenue charts
- Popular titles, revenue summary and recent activity
- Member dashboard: active loans, books finished this year, fines, reservations and recommendations
- Reading-goal progress and an “Up next” shelf preview sit alongside loans
- Recommendations are derived from ratings, availability and reading history (no external AI service required)

### Audit trail
- Staff-only audit ledger for authentication, member, catalog, circulation, fine, payment, event and room-booking actions
- Entries are written in the **same transaction** as the action they describe
- Actor, action, target, structured details and timestamp
- Sidebar “Audit log” view and a dashboard quick action

### Responsive, installable UI
- Desktop sidebar + mobile bottom navigation
- Light and dark themes, remembered per device
- Installable PWA: web manifest, icons and an offline app-shell service worker
- Personal shelves and the goal ring are fully responsive, including the seven-item mobile nav
- Accessible focus states, keyboard Escape handling and reduced-motion support
- No Node build step — the UI is plain HTML/CSS/JS served by FastAPI

### Operations
- Health endpoint at `/api/health`
- SQLite by default; PostgreSQL via `DATABASE_URL`
- Docker + Docker Compose setup (API + PostgreSQL)
- Automatic demo seeding, safe local defaults, no secrets in the repository
- API smoke test, offline Stripe Checkout test, browser UI test and screenshot capture script included

---

## Architecture

```text
library-system/
├─ backend/
│  ├─ api/
│  │  ├─ main.py              FastAPI app, static web mount, startup seeding
│  │  ├─ deps.py              JWT auth dependencies and role guards
│  │  └─ routes/              auth, books, catalog, members, loans, shelves,
│  │                           payments, events, spaces, analytics, audit,
│  │                           notifications
│  ├─ auth/                   password hashing and JWT helpers
│  ├─ config/                 pydantic-settings configuration
│  ├─ database/               engine/session + realistic demo seed
│  ├─ models/                 SQLAlchemy 2 models
│  ├─ schemas/                Pydantic v2 request/response schemas
│  ├─ scripts/                asset generator for PWA icons
│  ├─ tests/                  API smoke test, offline Stripe test, UI test and capture
│  ├─ requirements.txt
│  ├─ Dockerfile
│  └─ .env.example
├─ web/
│  ├─ index.html              accessible app shell
│  ├─ styles.css              responsive design system, animations, dark mode
│  ├─ app.js                  SPA router, API client, renderers, interactions
│  ├─ manifest.webmanifest    installable PWA metadata
│  ├─ service-worker.js       app-shell offline cache
│  └─ icon*.png / icon.svg    brand icons
├─ docs/screenshots/          UI screenshots
├─ docker-compose.yml
├─ start.ps1
└─ README.md
```

The FastAPI app mounts `web/` at `/` after registering the API routes, so the SPA and
API share a single origin (no CORS issues in production). API routes live under
`/api/v1`; OpenAPI docs are at `/api/docs`.

### Data model highlights

- `User` — roles, membership tier, library card, annual reading goal, authentication state
- `ReadingShelf` — one row per member/book with shelf status, progress and finish date
- `Book` / `BookCopy` / `Author` / `Publisher` / `Category` / `Branch`
- `Loan` / `Reservation` / `Fine`
- `Payment` / `MembershipSubscription`
- `Event` / `EventRegistration`
- `Room` / `RoomBooking`
- `Review` / `Notification` / `AuditLog`

All models use SQLAlchemy 2 typed mappings with timestamps, enums and relationships.

---

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust as needed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./library.db` | SQLite locally; set a PostgreSQL DSN in production |
| `APP_BASE_URL` | `http://localhost:8000` | Public app URL used in Stripe Checkout return links |
| `SECRET_KEY` | development value | **Change in production** — signs JWTs |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `STRIPE_SECRET_KEY` | *(blank)* | Enables real Stripe payments when set |
| `STRIPE_WEBHOOK_SECRET` | *(blank)* | Verifies Stripe webhook signatures |
| `DEFAULT_CURRENCY` | `USD` | Payment currency |
| `DEFAULT_LOAN_DAYS` | `14` | Standard loan period |
| `MAX_RENEWALS` | `2` | Renewals allowed per loan |
| `FINE_PER_DAY` | `0.25` | Overdue fine per day |
| `MAX_ACTIVE_LOANS` | `10` | Borrowing limit per member |

### PostgreSQL

```env
DATABASE_URL=postgresql+psycopg://library:library@localhost:5432/library_system
```

Install the driver with `pip install "psycopg[binary]"`. Tables are created on startup;
for production use a migration tool such as Alembic to evolve the schema.

### Stripe

Leave the Stripe values blank for instant local payments. To use real test payments:

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
APP_BASE_URL=http://localhost:8000
```

Hosted Checkout does not need a publishable key in the server. Fine payments call
`POST /api/v1/payments/fines/checkout`; memberships call `POST /api/v1/payments/subscribe`;
paid event tickets create a Checkout Session inside the registration endpoint. On return,
the SPA sends the `session_id` to `POST /api/v1/payments/checkout/{session_id}/confirm`,
which verifies the session with Stripe and settles the payment, activates the membership,
or records the event ticket. This makes local test payments work without a public webhook.

For production, configure a signed webhook at `POST /api/v1/payments/webhook` and set
`STRIPE_WEBHOOK_SECRET`. The handler covers `checkout.session.completed`,
`checkout.session.expired`, `payment_intent.succeeded` and `invoice.paid`. Expired
Checkout Sessions mark pending payments failed and release abandoned paid-event seats.
`APP_BASE_URL` must be the browser-accessible URL of this app so Stripe can redirect back.
The lower-level `POST /api/v1/payments/intent` endpoint is also available for API clients
that want a raw PaymentIntent and Stripe.js; the bundled UI uses hosted Checkout.

---

## API overview

| Area | Representative endpoints |
| --- | --- |
| Authentication | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET/PUT /auth/me` |
| Books | `GET/POST /books`, `GET/PUT/DELETE /books/{id}`, copies and reviews, `POST /books/suggest` |
| Catalog | `/catalog/authors`, `/categories`, `/publishers`, `/branches` |
| Shelves | `GET /shelves/me`, `PUT/DELETE /shelves/me/{book_id}`, `PUT /shelves/me/goal` |
| Members | `GET/POST /members`, stats, role/tier/activation changes |
| Circulation | `POST /loans`, renew, return, `/loans/overdue`, reservations |
| Fines | `GET /fines`, pay at desk, waive |
| Payments | `/payments/fines/checkout`, `/payments/checkout/{session_id}/confirm`, `/payments/intent`, subscriptions, Stripe webhook |
| Events | list/create/update events, register/cancel, registrations roster |
| Spaces | `/rooms`, `/rooms/bookings`, book/cancel a room, conflict checks |
| Analytics | `/analytics/dashboard`, `/analytics/me`, revenue, popular books |
| Audit | `GET /audit` (staff only), filterable by action/entity |
| Notifications | list, unread count, mark read |
| System | `/api/health`, `/api/docs` |

All money values are returned as floats with an explicit currency code; all timestamps
are UTC in the database and localized by the browser.

---

## Testing

Start the API first, then run:

```powershell
cd backend
.\.venv\Scripts\python tests\smoke_test.py
```

The smoke test covers health, authentication, catalog, analytics, members,
book/copy creation, smart-catalog suggestions, checkout/renew/return, reviews,
reading shelves (save, progress, finish, goal update, remove), overdue fines and
payments, subscriptions, event tickets, room booking/conflict/cancellation,
profile updates, role-based access, PWA assets and static frontend serving.

The offline Stripe test uses a fake Stripe SDK and a temporary database. It never
contacts Stripe and verifies the hosted-checkout fine flow end to end:

```powershell
.\.venv\Scripts\python tests\stripe_flow_test.py
```

For the browser test, install the dev-only Playwright package (Microsoft Edge or
Chrome must be installed):

```powershell
.\.venv\Scripts\python -m pip install playwright pillow
.\.venv\Scripts\python tests\ui_test.py
```

The UI test drives the real app in headless Edge, checks desktop and mobile layouts,
personal shelves, goal dialogs, auth animations, PWA behavior and role-based
navigation, then writes a regression screenshot set to `docs/test-screenshots/`. It
intentionally creates test data, so reset the database before capturing documentation
images.

### Screenshots

`tests/capture_screens.py` creates the documentation set from a pristine demo seed. It
creates one realistic member and one room booking for the action screenshots, then
leaves the database ready to reset. Run it from `backend/` after deleting
`library.db` and restarting the API. The set contains 20 reviewed views, including:

- `docs/screenshots/01-login.png` (staggered auth entrance)
- `docs/screenshots/02-admin-dashboard.png`
- `docs/screenshots/04-browse.png` (shelf bookmark pins)
- `docs/screenshots/06-book-modal.png` (digital edition + shelf controls)
- `docs/screenshots/09-finance.png`
- `docs/screenshots/11-spaces.png`
- `docs/screenshots/13-audit.png`
- `docs/screenshots/15-logout.png` (closing-book transition)
- `docs/screenshots/16-member-dashboard.png` (goal + up-next shelves)
- `docs/screenshots/16b-member-shelves.png`
- `docs/screenshots/17-mobile-browse.png`
- `docs/screenshots/17b-mobile-shelves.png`
- `docs/screenshots/18-mobile-profile.png`

---

## Docker

```bash
docker compose up --build
```

This starts PostgreSQL and the API at http://localhost:8000. The web frontend is
served by the same container. Set a strong `SECRET_KEY`, a public `APP_BASE_URL` and
Stripe keys through the environment before using this in production.

---

## Research & design references (2025–26)

The shelf-and-goal work is intentionally small, legible and library-specific rather
than a generic social network. These references shaped the product decisions:

- **Public library app expectations:** the ALA/PLA 2026 public-library services
  landscape and the Seattle Public Library’s 2026 mobile-app launch both emphasise
  mobile-first access, personal account tools and helping patrons find their next
  item. Libra keeps shelves, due dates and goals reachable from the bottom navigation.
  <https://www.ala.org/sites/default/files/2026-06/PLA_Services_Report_2026.pdf> ·
  <https://www.spl.org/about-us/news-releases/the-seattle-public-library-launches-new-mobile-app-for-patrons>
- **Three-shelf mental model:** Libby’s tags/reading history and the Literal reading
  tracker both use familiar “want to read / reading / finished” states and a yearly
  reading goal with stats. Libra adopts that model directly instead of inventing
  library-specific jargon. <https://play.google.com/store/apps/details?id=com.overdrive.mobile.android.libby> ·
  <https://apps.apple.com/us/app/literal-discover-books/id1566119883>
- **Discovery and reading history:** Aspen Discovery's reading-history controls show
  that saved and finished reading data is a core discovery tool, not an advanced
  setting. Libra surfaces a shelf preview on the dashboard so saved titles stay visible.
  <https://bywatersolutions.com/education/patron-reading-history-in-aspen-discovery-and-koha>
- **Motion with restraint:** NN/g’s guidance recommends roughly 100–500 ms for most UI
  animations and a reduced-motion alternative. The login stagger, cover transition and
  logout book run for a fraction of a second, and
  `prefers-reduced-motion` removes them entirely.
  <https://www.nngroup.com/articles/animation-duration/>

---

## Design notes & honest boundaries

- **Payments:** without Stripe keys, payments are intentionally simulated and clearly
  labelled “development mode”. Real charges require live/test Stripe credentials and a
  publicly reachable `APP_BASE_URL`. Checkout returns are verified by the app; production
  should also configure the signed webhook so fulfilment is reliable if the browser tab
  closes. Paid event seats are held during checkout and released by
  `checkout.session.expired` (24 hours) or by the member cancelling the registration.
- **Recommendations & catalog assist:** both are transparent local heuristics based on
  ratings, availability, category affinity, borrowing history and catalog keywords — not
  hosted AI models. The UI labels the suggestion action “Smart catalog assist” rather
  than claiming generative AI.
- **Digital content:** the catalog stores `digital_file_url` and links to
  public-domain editions. DRM-protected e-lending/loan expiry is outside this demo.
- **Reading goals:** the annual count is calculated from shelf records with a
  `finished_at` timestamp in the current calendar year. It is intentionally not a
  stored counter, so moving a book between shelves or deleting it always leaves the
  number accurate. Goals are personal; staff cannot edit another member’s shelves.
- **Audit trail:** covers sensitive mutations listed above. Background jobs and reads
  are not audited.
- **Email/SMS:** configuration fields exist, but no external delivery provider is wired
  up; in-app notifications are fully functional.
- **Multi-branch & multi-tenant:** branches, per-copy branch assignment, branch-aware
  events and room spaces are modelled. Branch-scoped staff permissions, cross-branch
  transfers and hard tenant isolation are a next step; run one deployment per tenant.
- **Internationalisation:** timestamps are stored in UTC and localised by the browser,
  currency is configurable, phone/card fields accept international values, and copy is
  written in plain language. Full translated catalogues/right-to-left layouts are not
  included.
- **Production readiness:** use PostgreSQL, a strong secret, HTTPS, a reverse proxy,
  migrations, backups, rate limiting and Stripe webhook signatures. The included setup
  is designed to be complete and runnable locally, not a hardened SaaS deployment.

---

## License

MIT-style demo project. Book covers are fetched from Open Library; all seeded titles and
metadata are used for demonstration. Digital edition links point to Project Gutenberg.
