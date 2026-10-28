import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.llm import LLMUnavailableError
from app.db.models import ChatMessage, SavedPlan, User
from app.db.session import get_db
from app.services.chat_service import handle_chat

router = APIRouter(prefix="/api", tags=["chat"])
log = logging.getLogger("jibon.chat")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1500)


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The main endpoint. The Router picks the crew. If the reply contains proposed_actions, ask the user and call /api/actions/approve."""
    try:
        return handle_chat(db, user, body.message.strip())
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        log.exception("Chat failed")
        db.rollback()
        raise HTTPException(status_code=500, detail="The agents could not finish this request. Please try again in a minute.")


@router.get("/chat/history")
def history(limit: int = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(min(limit, 200))).scalars().all()
    return [{"role": m.role, "content": m.content, "crew": m.crew, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in reversed(rows)]


@router.get("/plans")
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(SavedPlan).where(SavedPlan.user_id == user.id).order_by(SavedPlan.id.desc())).scalars().all()
    return [{"id": p.id, "title": p.title, "estimated_cost": p.estimated_cost,
             "created_at": p.created_at.isoformat() if p.created_at else None} for p in rows]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.get(SavedPlan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return {"id": plan.id, "title": plan.title, "request": plan.request_text, "plan": plan.plan_text,
            "estimated_cost": plan.estimated_cost}
