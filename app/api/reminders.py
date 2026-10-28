from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Reminder, User, UserProfile
from app.db.session import get_db
from app.services.action_service import ActionError, approve_reminder
from app.tools.db_tools import reminder_to_dict

router = APIRouter(prefix="/api", tags=["reminders and profile"])


class ApproveIn(BaseModel):
    action: dict  # exactly one item of "proposed_actions" from /api/chat


@router.post("/actions/approve")
def approve(body: ApproveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The user pressed 'Yes'. Only now the Action Crew creates the reminder."""
    try:
        return approve_reminder(db, user.id, body.action)
    except ActionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/reminders")
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at)).scalars().all()
    changed = False
    out = []
    for r in rows:
        item = reminder_to_dict(r)
        if item["is_due"] and r.status == "pending":  # mark as delivered when it is read (works even if the server slept)
            r.status, changed = "sent", True
            item["status"] = "sent"
        out.append(item)
    if changed:
        db.commit()
    return out


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Reminder, reminder_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    db.delete(row)
    db.commit()
    return {"deleted": reminder_id}


class ProfileIn(BaseModel):
    full_name: str | None = None
    family_size: int | None = None
    occupation: str | None = None
    memory_summary: str | None = None


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(UserProfile, user.id)
    return {"full_name": p.full_name, "family_size": p.family_size, "occupation": p.occupation,
            "memory_summary": p.memory_summary} if p else {}


@router.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Long-term memory: the assistant uses these facts in every chat (family size, occupation...)."""
    p = db.get(UserProfile, user.id) or UserProfile(user_id=user.id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    db.add(p)
    db.commit()
    return {"saved": True}
