from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.deps import get_current_user
from database.session import get_db
from models.notification import Notification
from models.user import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[dict]:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in notifications
    ]


@router.get("/unread-count")
def unread_count(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    count = len(
        db.scalars(
            select(Notification.id).where(
                Notification.user_id == current_user.id,
                Notification.is_read.is_(False),
            )
        ).all()
    )
    return {"unread": count}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.post("/read-all")
def mark_all_read(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    db.commit()
    return {"message": "All notifications marked as read"}
