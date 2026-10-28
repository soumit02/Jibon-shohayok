"""Reading uploaded files and saving documents."""
import json
import re
from datetime import date

from sqlalchemy.orm import Session

from app.core.llm import run_with_fallback
from app.crews.documents import build_vault_crew
from app.crews.utils import get_text
from app.db.models import Document
from app.tools.db_tools import days_left, suggested_reminder_date, urgency

DOC_TYPES = {"passport", "driving_license", "nid", "insurance", "bill", "other"}


class UnreadableFileError(ValueError):
    """The file has no readable text (image, scanned PDF)."""


def parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def doc_to_dict(doc: Document) -> dict:
    left = days_left(doc.expiry_date)
    return {
        "id": doc.id, "doc_type": doc.doc_type, "title": doc.title, "holder_name": doc.holder_name,
        "doc_number": doc.doc_number,
        "issue_date": doc.issue_date.isoformat() if doc.issue_date else None,
        "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
        "days_left": left, "urgency": urgency(left),
        "suggested_reminder_date": suggested_reminder_date(doc.doc_type, doc.expiry_date),
        "confirmed": doc.confirmed, "file_name": doc.file_name,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def extract_text(data: bytes, filename: str) -> str:
    """Text-based PDF or .txt only (MVP). Images / scanned PDFs raise UnreadableFileError."""
    name = filename.lower()
    text = ""
    if name.endswith(".pdf"):
        import fitz  # PyMuPDF
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in list(pdf)[:3])  # first 3 pages are enough (saves tokens)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    if len(text.strip()) < 20:
        raise UnreadableFileError(
            "I could not read text from this file. In this version please upload a text-based PDF, "
            "or use 'Add manually' to type the dates yourself."
        )
    return text


def parse_vault_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    data = json.loads(match.group(0)) if match else {}
    doc_type = data.get("doc_type") if data.get("doc_type") in DOC_TYPES else "other"
    return {
        "doc_type": doc_type,
        "title": (data.get("title") or doc_type.replace("_", " ").title())[:150],
        "holder_name": data.get("holder_name") or None,
        "doc_number": data.get("doc_number") or None,
        "issue_date": parse_date(data.get("issue_date")),
        "expiry_date": parse_date(data.get("expiry_date")),
    }


def process_upload(db: Session, user_id: int, filename: str, mime: str, data: bytes, type_hint: str = "") -> tuple[Document, str]:
    text = extract_text(data, filename)

    def task(llm):
        crew, vault_task = build_vault_crew(llm, text, type_hint)
        return get_text(crew.kickoff(), vault_task)

    raw, tier = run_with_fallback(task, temperature=0.0)
    try:
        fields = parse_vault_json(raw)
    except (json.JSONDecodeError, ValueError):
        fields = {"doc_type": type_hint if type_hint in DOC_TYPES else "other", "title": filename[:150],
                  "holder_name": None, "doc_number": None, "issue_date": None, "expiry_date": None}

    doc = Document(user_id=user_id, file_name=filename[:250], mime_type=mime or "application/octet-stream",
                   file_data=data, confirmed=False, **fields)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc, tier
