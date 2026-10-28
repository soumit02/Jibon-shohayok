"""Runs the Action Crew AFTER the user approved a proposed reminder."""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm import run_with_fallback
from app.core.timeutil import today_bd
from app.crews import action as action_crew_mod
from app.db.models import Document, Reminder
from app.tools.db_tools import create_reminder_row, reminder_to_dict

log = logging.getLogger("jibon.action")


class ActionError(ValueError):
    pass


def approve_reminder(db: Session, user_id: int, action: dict) -> dict:
    if action.get("type") != "set_reminder":
        raise ActionError("Unknown action type.")
    try:
        remind_on = date.fromisoformat(str(action.get("remind_on")))
    except ValueError:
        raise ActionError("remind_on must be YYYY-MM-DD.")
    if remind_on < today_bd():
        raise ActionError("The reminder date is in the past.")
    message = str(action.get("message") or "").strip()[:300]
    if not message:
        raise ActionError("The reminder message is empty.")
    document_id = int(action.get("document_id") or 0)
    if document_id:
        doc = db.get(Document, document_id)
        if not doc or doc.user_id != user_id:
            raise ActionError("Document not found.")

    before = {r.id for r in db.execute(select(Reminder).where(Reminder.user_id == user_id)).scalars().all()}

    def task(llm):
        crew, _ = action_crew_mod.build_action_crew(llm, user_id, message, remind_on.isoformat(), document_id)
        return str(crew.kickoff())

    confirmation, tier, created_by = "", "none", "agent"
    try:
        confirmation, tier = run_with_fallback(task, temperature=0.0, prefer_small=True)
    except Exception as exc:  # even if the AI is down, an approved reminder must not be lost
        log.warning("Action crew failed, creating the reminder directly: %s", exc)

    db.expire_all()
    rows = db.execute(select(Reminder).where(Reminder.user_id == user_id)).scalars().all()
    new_rows = [r for r in rows if r.id not in before]
    if new_rows:
        reminder = new_rows[-1]
    else:  # agent did not create it (or an identical one already existed) -> make sure it exists
        reminder, created = create_reminder_row(db, user_id, message, remind_on, document_id or None)
        created_by = "code" if created else "existing"
    return {"reminder": reminder_to_dict(reminder), "confirmation": confirmation or "Reminder saved.",
            "llm_tier": tier, "created_by": created_by, "agents_used": action_crew_mod.AGENTS_USED}
