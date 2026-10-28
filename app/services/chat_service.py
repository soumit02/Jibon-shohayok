"""Chat: Router -> the right crew -> reply. Also keeps short-term memory (history) and long-term memory (profile)."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import run_with_fallback
from app.core.timeutil import today_bd
from app.crews import action as action_crew_mod
from app.crews import documents as documents_crew_mod
from app.crews import planning as planning_crew_mod
from app.crews import procedure as procedure_crew_mod
from app.crews.router import route
from app.crews.utils import get_text
from app.db.models import ChatMessage, Document, SavedPlan, User, UserProfile
from app.services.documents_service import parse_date

CREW_NAMES = {
    "planning": "Planning Crew", "my_documents": "Document Crew", "procedure": "Procedure Guide Crew", "general": "Router",
}

GENERAL_PROMPT = """You are Jibon Shohayok, a friendly personal life-admin assistant for people in Bangladesh.
You can: keep the user's documents (passport, licence, NID, insurance, bills) and warn before they expire; explain official procedures
(passport, driving licence, tax) from official documents; plan trips and events inside a budget; and set reminders after the user approves.
Answer briefly in the same language as the user (Bangla if the user writes Bangla). If the user asks for something you cannot do, say so honestly.

User context:
{context}

User message: {message}"""


def _clean_reply(text: str) -> str:
    """Some models add marks like 【1†source】 to the text. We show real sources separately, so remove the marks."""
    return re.sub(r"\s*【[^】]*】", "", text).strip()


def build_user_context(db: Session, user: User) -> str:
    profile = db.get(UserProfile, user.id)
    lines = [f"Today (Bangladesh): {today_bd().isoformat()}"]
    if profile:
        if profile.full_name:
            lines.append(f"Name: {profile.full_name}")
        if profile.family_size:
            lines.append(f"Family size: {profile.family_size}")
        if profile.occupation:
            lines.append(f"Occupation: {profile.occupation}")
        if profile.memory_summary:
            lines.append(f"Notes: {profile.memory_summary[:500]}")
    history = db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(settings.CHAT_HISTORY_TURNS * 2)
    ).scalars().all()
    if history:
        lines.append("Recent conversation:")
        for m in reversed(history):
            lines.append(f"- {m.role}: {m.content[:250]}")
    return "\n".join(lines)


def _extract_reminder_proposals(db: Session, user_id: int, text: str) -> tuple[str, list[dict]]:
    """Moves 'PROPOSE_REMINDER: id | date | message' lines out of the text into proposed_actions."""
    actions, kept = [], []
    for line in text.splitlines():
        m = re.match(r"\s*PROPOSE_REMINDER:\s*(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)", line)
        if not m:
            kept.append(line)
            continue
        doc_id, when, message = int(m.group(1)), parse_date(m.group(2)), m.group(3).strip()
        doc = db.get(Document, doc_id)
        if when and when >= today_bd() and doc and doc.user_id == user_id:
            actions.append({"type": "set_reminder", "document_id": doc_id, "remind_on": when.isoformat(), "message": message[:300]})
    return "\n".join(kept).strip(), actions


def _plan_status(text: str) -> str:
    m = re.search(r"FINAL_STATUS:\s*(WITHIN_BUDGET|OVER_BUDGET)", text)
    if m:
        return m.group(1)
    return "OVER_BUDGET" if "RE-PLAN NEEDED" in text.upper() else "WITHIN_BUDGET"


def _strip_machine_lines(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not re.match(r"\s*(FINAL_STATUS|BEST_FIT_TOTAL_BDT):", l)).strip()


def _answer_planning(db: Session, user: User, message: str, ctx: str) -> dict:
    note, replans, tier = "", 0, "primary"
    while True:
        def task(llm, note=note):
            crew, cost_task = planning_crew_mod.build_planning_crew(llm, message, ctx, note)
            return get_text(crew.kickoff(), cost_task)

        text, tier = run_with_fallback(task, temperature=0.4)
        if _plan_status(text) == "OVER_BUDGET" and replans < settings.MAX_REPLANS:
            replans += 1  # like Leo's reteach_count
            note = ("NOTE: the previous plan was OVER BUDGET. Re-plan with cheaper choices "
                    "(cheaper transport, shorter stay, simpler food) and still give three options.")
            continue
        break

    total = re.search(r"BEST_FIT_TOTAL_BDT:\s*([\d,]+)", text)
    estimated = int(total.group(1).replace(",", "")) if total and total.group(1).replace(",", "") else None
    clean = _strip_machine_lines(text)
    plan = SavedPlan(user_id=user.id, title=message[:80], request_text=message, plan_text=clean, estimated_cost=estimated or None)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"reply": clean, "agents_used": planning_crew_mod.AGENTS_USED, "llm_tier": tier,
            "plan_id": plan.id, "replans": replans, "proposed_actions": [], "sources": []}


def _answer_documents(db: Session, user: User, message: str, ctx: str) -> dict:
    def task(llm):
        crew, t = documents_crew_mod.build_deadline_crew(llm, message, ctx, user.id)
        return get_text(crew.kickoff(), t)

    text, tier = run_with_fallback(task, temperature=0.3)
    clean, actions = _extract_reminder_proposals(db, user.id, text)
    return {"reply": clean, "agents_used": documents_crew_mod.DEADLINE_AGENTS, "llm_tier": tier,
            "proposed_actions": actions, "sources": []}


def _answer_procedure(db: Session, user: User, message: str, ctx: str) -> dict:
    sink: list = []

    def task(llm):
        sink.clear()
        crew, t = procedure_crew_mod.build_procedure_crew(llm, message, ctx, user.id, sink)
        return get_text(crew.kickoff(), t)

    text, tier = run_with_fallback(task, temperature=0.2)
    unique, seen = [], set()
    for s in sink:
        key = (s["title"], s["page"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return {"reply": text, "agents_used": procedure_crew_mod.AGENTS_USED, "llm_tier": tier,
            "proposed_actions": [], "sources": unique[:5]}


def _answer_general(message: str, ctx: str) -> dict:
    text, tier = run_with_fallback(lambda llm: str(llm.call(GENERAL_PROMPT.format(context=ctx, message=message))),
                                   temperature=0.5, prefer_small=True)
    return {"reply": text, "agents_used": [], "llm_tier": tier, "proposed_actions": [], "sources": []}


def handle_chat(db: Session, user: User, message: str) -> dict:
    ctx = build_user_context(db, user)  # built BEFORE saving the new message
    category, _ = route(message)

    if category == "planning":
        result = _answer_planning(db, user, message, ctx)
    elif category == "my_documents":
        result = _answer_documents(db, user, message, ctx)
    elif category == "procedure":
        result = _answer_procedure(db, user, message, ctx)
    else:
        result = _answer_general(message, ctx)

    result["reply"] = _clean_reply(result["reply"])
    result["crew"] = CREW_NAMES[category]
    db.add(ChatMessage(user_id=user.id, role="user", content=message))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=result["reply"], crew=result["crew"]))
    db.commit()
    return result
