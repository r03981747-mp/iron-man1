from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp used consistently across the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize aware datetimes (e.g. from PostgreSQL) to naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
