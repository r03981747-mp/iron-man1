from contextlib import asynccontextmanager
from pathlib import Path
import mimetypes

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

import models  # noqa: F401  (registers all SQLAlchemy models)
from api.routes import (
    analytics,
    audit,
    auth,
    books,
    catalog,
    events,
    loans,
    members,
    notifications,
    payments,
    shelves,
    spaces,
)
from config.settings import settings
from database.seed import seed_database
from database.session import Base, SessionLocal, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Libra — Library OS: circulation, catalog, members, events, analytics, "
        "audit logs and optional Stripe payments."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    books.router,
    catalog.router,
    members.router,
    loans.router,
    payments.router,
    shelves.router,
    spaces.router,
    events.router,
    analytics.router,
    audit.router,
    notifications.router,
):
    app.include_router(router, prefix=settings.API_V1_STR)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={"detail": "The request conflicts with existing data."},
    )


@app.get("/api/health", tags=["Health"])
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "stripe": "configured" if settings.stripe_enabled else "development-mode",
    }


WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
if WEB_DIR.exists():
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
