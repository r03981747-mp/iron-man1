"""Helpers for writing the audit trail.

The caller owns the transaction: record_audit() adds a row to the session and
the surrounding endpoint commits it together with the business change. That
keeps the audit log consistent with the data it describes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.audit import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
