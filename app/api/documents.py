from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.llm import LLMUnavailableError
from app.db.models import Document, User
from app.db.session import get_db
from app.services.documents_service import (DOC_TYPES, UnreadableFileError, doc_to_dict, process_upload)

router = APIRouter(prefix="/api", tags=["documents"])


class DocumentFields(BaseModel):
    doc_type: str | None = None
    title: str | None = None
    holder_name: str | None = None
    doc_number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None


def _own_document(db: Session, user: User, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.post("/documents/upload")
def upload_document(file: UploadFile = File(...), doc_type: str = Form(""),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Step 1: upload. The AI reads the file and returns the values it found. They are NOT final until you call /confirm."""
    data = file.file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is too big (max {settings.MAX_UPLOAD_MB} MB).")
    try:
        doc, tier = process_upload(db, user.id, file.filename or "document", file.content_type or "", data, doc_type)
    except UnreadableFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"document": doc_to_dict(doc), "needs_confirmation": True, "llm_tier": tier,
            "agents_used": ["Document Vault Agent"],
            "message": "Please check these values. If something is wrong, correct it when you confirm."}


@router.post("/documents/{doc_id}/confirm")
def confirm_document(doc_id: int, fields: DocumentFields | None = None,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Step 2: you confirm (optionally with corrected values). Only confirmed documents are used by the assistant."""
    doc = _own_document(db, user, doc_id)
    if fields:
        updates = fields.model_dump(exclude_unset=True)
        if "doc_type" in updates and updates["doc_type"] not in DOC_TYPES:
            raise HTTPException(status_code=422, detail=f"doc_type must be one of {sorted(DOC_TYPES)}")
        for key, value in updates.items():
            setattr(doc, key, value)
    doc.confirmed = True
    db.commit()
    db.refresh(doc)
    return doc_to_dict(doc)


@router.post("/documents/manual")
def add_document_manually(fields: DocumentFields, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc_type = fields.doc_type if fields.doc_type in DOC_TYPES else "other"
    doc = Document(user_id=user.id, doc_type=doc_type, title=(fields.title or doc_type.title())[:150],
                   holder_name=fields.holder_name, doc_number=fields.doc_number,
                   issue_date=fields.issue_date, expiry_date=fields.expiry_date,
                   file_name="manual-entry", mime_type="none", file_data=b"", confirmed=True)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc_to_dict(doc)


@router.get("/documents")
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = db.execute(select(Document).where(Document.user_id == user.id).order_by(Document.id.desc())).scalars().all()
    return [doc_to_dict(d) for d in docs]


@router.get("/documents/{doc_id}/file")
def download_file(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = _own_document(db, user, doc_id)
    if not doc.file_data:
        raise HTTPException(status_code=404, detail="This document was added manually, so there is no file.")
    return Response(content=doc.file_data, media_type=doc.mime_type,
                    headers={"Content-Disposition": f'inline; filename="{doc.file_name}"'})


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own_document(db, user, doc_id))
    db.commit()
    return {"deleted": doc_id}


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deadlines dashboard: red = 30 days or less, yellow = 90 days or less, green = more."""
    docs = db.execute(
        select(Document).where(Document.user_id == user.id, Document.confirmed.is_(True), Document.expiry_date.is_not(None))
        .order_by(Document.expiry_date)
    ).scalars().all()
    items = [doc_to_dict(d) for d in docs]
    counts = {"expired": 0, "red": 0, "yellow": 0, "green": 0}
    for it in items:
        counts[it["urgency"]] += 1
    return {"counts": counts, "items": items}
