from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.deps import staff_required
from database.session import get_db
from models.audit import AuditLog
from models.user import User

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("")
def list_audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(staff_required),
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    entries = db.scalars(stmt).all()
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "details": entry.details or {},
            "ip_address": entry.ip_address,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "user_id": entry.user_id,
            "user_name": entry.user.full_name if entry.user else None,
            "user_email": entry.user.email if entry.user else None,
            "user_role": entry.user.role.value if entry.user else None,
        }
        for entry in entries
    ]
