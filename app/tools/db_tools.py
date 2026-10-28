"""Tools that read/write the database. User tools are built PER USER: the AI can never choose a different user_id."""
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.core.timeutil import BD_TZ, as_bd, now_bd, today_bd
from app.db.models import Document, Reminder, TravelCost
from app.db.session import SessionLocal

# how many days BEFORE the expiry we suggest a reminder
REMINDER_LEAD_DAYS = {"passport": 180, "driving_license": 30, "insurance": 14, "bill": 3, "nid": 30, "other": 14}


def days_left(expiry: date | None):
    return (expiry - today_bd()).days if expiry else None


def urgency(days: int | None) -> str:
    if days is None:
        return "none"
    if days < 0:
        return "expired"
    if days <= 30:
        return "red"
    if days <= 90:
        return "yellow"
    return "green"


def suggested_reminder_date(doc_type: str, expiry: date | None) -> str | None:
    if not expiry or expiry < today_bd():
        return None
    when = expiry - timedelta(days=REMINDER_LEAD_DAYS.get(doc_type, 14))
    if when <= today_bd():
        when = today_bd() + timedelta(days=1)
    return when.isoformat() if when <= expiry else None


def reminder_to_dict(r: Reminder) -> dict:
    due_at = as_bd(r.remind_at)
    return {
        "id": r.id, "message": r.message, "remind_at": due_at.isoformat(),
        "status": r.status, "document_id": r.document_id,
        "is_due": due_at <= now_bd(),
    }


def create_reminder_row(db, user_id: int, message: str, remind_on: date, document_id: int | None) -> tuple[Reminder, bool]:
    """Returns (reminder, created). If the same reminder already exists it is returned instead of a duplicate."""
    remind_at = datetime(remind_on.year, remind_on.month, remind_on.day, 9, 0, tzinfo=BD_TZ)
    existing = db.execute(
        select(Reminder).where(Reminder.user_id == user_id, Reminder.status == "pending", Reminder.document_id == document_id)
    ).scalars().all()
    for row in existing:
        if as_bd(row.remind_at).date() == remind_on:
            return row, False
    row = Reminder(user_id=user_id, document_id=document_id, message=message[:300], remind_at=remind_at, channel="in_app", status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True


def make_travel_cost_tool():
    from crewai.tools import tool

    @tool("lookup_travel_costs")
    def lookup_travel_costs(keyword: str) -> str:
        """Look up trusted cost data (bus, train, hotel, food...) from the cost table. Use a place or mode, e.g. 'Sylhet' or 'train'."""
        with SessionLocal() as db:
            rows = db.execute(select(TravelCost)).scalars().all()
        words = [w for w in keyword.lower().replace("-", " ").split() if w]
        hits = [r for r in rows if any(w in f"{r.route} {r.mode} {r.notes}".lower() for w in words)] if words else rows
        if not hits:
            return "NO_COST_DATA: nothing in the cost table. Ask the user for the price, or use web_search and clearly label it as an estimate. Never invent a price."
        return "\n".join(f"{r.route} | {r.mode} | {r.cost_bdt} BDT | {r.notes}" for r in hits[:15])

    return lookup_travel_costs


def make_documents_tool(user_id: int):
    from crewai.tools import tool

    # NOTE: this tool has ONE parameter on purpose. Groq rejects a tool whose JSON schema has no "properties"
    # ("'required' present but 'properties' is missing"), so a tool without any argument does not work.
    @tool("list_my_documents")
    def list_my_documents(doc_type: str) -> str:
        """List the user's own saved and confirmed documents with expiry date, days left and a suggested reminder date. Pass doc_type='all' to list every document, or one type: passport, driving_license, nid, insurance, bill, other."""
        wanted = (doc_type or "all").strip().lower()
        with SessionLocal() as db:
            query = select(Document).where(Document.user_id == user_id, Document.confirmed.is_(True)).order_by(Document.expiry_date)
            if wanted not in ("all", ""):
                query = query.where(Document.doc_type == wanted)
            docs = db.execute(query).scalars().all()
        if not docs:
            return "NO_DOCUMENTS: the user has not saved any confirmed document of this kind yet."
        out = []
        for d in docs:
            left = days_left(d.expiry_date)
            out.append({
                "document_id": d.id, "type": d.doc_type, "title": d.title, "holder": d.holder_name,
                "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
                "days_left": left, "status": urgency(left),
                "suggested_reminder_date": suggested_reminder_date(d.doc_type, d.expiry_date),
            })
        return json.dumps({"today": today_bd().isoformat(), "documents": out}, ensure_ascii=False)

    return list_my_documents


def make_reminder_tool(user_id: int):
    from crewai.tools import tool

    @tool("create_reminder")
    def create_reminder(message: str, remind_on: str, document_id: int = 0) -> str:
        """Create ONE reminder for the user. remind_on must be YYYY-MM-DD. document_id is 0 when the reminder is not about a document."""
        try:
            when = date.fromisoformat(remind_on.strip())
        except ValueError:
            return "ERROR: remind_on must look like 2027-03-15."
        if when < today_bd():
            return "ERROR: the date is in the past."
        with SessionLocal() as db:
            if document_id:
                doc = db.get(Document, document_id)
                if not doc or doc.user_id != user_id:
                    return "ERROR: document not found."
            row, created = create_reminder_row(db, user_id, message, when, document_id or None)
            return f"{'Created' if created else 'Already existed'}: reminder id {row.id} on {when.isoformat()}"

    return create_reminder
