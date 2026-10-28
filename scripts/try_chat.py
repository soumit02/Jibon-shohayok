"""
Test the whole assistant in the terminal (like you tested Leo), before using the API / frontend.

    python scripts/try_chat.py

Type a normal message to chat. Special commands:
    /upload path\\to\\file.pdf   upload a document (text-based PDF or .txt)
    /confirm 3                 confirm document number 3 (the values you saw are correct)
    /docs                      list your documents
    /approve 1                 approve proposed action number 1 from the last answer
    /reminders                 show reminders
    /quit
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Document, User, UserProfile
from app.db.session import SessionLocal, init_db
from app.services.action_service import approve_reminder
from app.services.chat_service import handle_chat
from app.services.documents_service import doc_to_dict, process_upload
from app.tools.db_tools import reminder_to_dict

EMAIL = "demo@jibon.test"

init_db()
db = SessionLocal()
user = db.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
if not user:
    user = User(email=EMAIL, password_hash=hash_password("demo1234"))
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id, full_name="Demo User", family_size=3, occupation="salaried"))
    db.commit()
print(f"Logged in as {EMAIL}. Type /quit to stop.\n")

last_actions: list[dict] = []
while True:
    line = input("you> ").strip()
    if not line:
        continue
    try:
        if line == "/quit":
            break
        elif line.startswith("/upload "):
            path = Path(line[8:].strip().strip('"'))
            doc, tier = process_upload(db, user.id, path.name, "application/pdf", path.read_bytes())
            print("AI read this (model:", tier + "):", doc_to_dict(doc))
            print(f"If correct, type: /confirm {doc.id}")
        elif line.startswith("/confirm "):
            doc = db.get(Document, int(line[9:]))
            doc.confirmed = True
            db.commit()
            print("Confirmed:", doc_to_dict(doc))
        elif line == "/docs":
            for d in db.execute(select(Document).where(Document.user_id == user.id)).scalars():
                print(doc_to_dict(d))
        elif line == "/reminders":
            from app.db.models import Reminder
            for r in db.execute(select(Reminder).where(Reminder.user_id == user.id)).scalars():
                print(reminder_to_dict(r))
        elif line.startswith("/approve "):
            result = approve_reminder(db, user.id, last_actions[int(line[9:]) - 1])
            print(result)
        else:
            result = handle_chat(db, user, line)
            print(f"\n[{result['crew']} | agents: {', '.join(result['agents_used']) or '-'} | model: {result['llm_tier']}]")
            print(result["reply"])
            if result.get("sources"):
                print("\nSources:", *[f"- {s['title']} (page {s['page']}) {s['url']}" for s in result["sources"]], sep="\n")
            last_actions = result.get("proposed_actions", [])
            for i, a in enumerate(last_actions, start=1):
                print(f"\nProposed action {i}: {a}   -> type /approve {i} to allow it")
            print()
    except Exception as exc:
        db.rollback()
        print("ERROR:", exc.__class__.__name__, exc)
        if exc.__cause__ is not None:  # the real reason behind "AI service is busy"
            print("   real reason:", exc.__cause__.__class__.__name__, str(exc.__cause__)[:400])
