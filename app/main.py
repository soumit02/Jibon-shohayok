import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, text

from app.api import auth, chat, documents, reminders
from app.core.config import settings
from app.core.timeutil import as_bd, now_bd
from app.db.models import Reminder
from app.db.session import IS_SQLITE, SessionLocal, engine, init_db
from app.rag import retriever
from app.rag.embeddings import EmbeddingError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jibon")


def mark_due_reminders() -> None:
    """Scheduler job: pending reminders whose time has come become 'sent' (shown as due in the app). No LLM involved."""
    with SessionLocal() as db:
        rows = db.execute(select(Reminder).where(Reminder.status == "pending")).scalars().all()
        changed = False
        for r in rows:
            if as_bd(r.remind_at) <= now_bd():
                r.status, changed = "sent", True
        if changed:
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    try:
        init_db()  # creates the tables if they do not exist
    except Exception as exc:  # the API must still start so that /health can explain the problem
        log.error("Database init failed: %s", exc)
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(timezone="Asia/Dhaka")
        scheduler.add_job(mark_due_reminders, "interval", minutes=5, id="due_reminders")
        scheduler.start()
    except Exception as exc:
        log.error("Scheduler did not start: %s", exc)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Jibon Shohayok API", version="0.2.0", lifespan=lifespan)

# Lovable (a different domain) calls this API from the browser => CORS is required
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials="*" not in settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(reminders.router)


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/", include_in_schema=False)
def home():
    """The web page (app/static/index.html). The API docs stay at /docs."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/info")
def info():
    return {"app": "Jibon Shohayok: Personal Life-Admin Assistant", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        log.error("DB health check failed: %s", exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "down",
        "database_backend": "sqlite (temporary!)" if IS_SQLITE else "postgres",
        "rag_chunks": retriever.count_chunks(),
        "embedding_key_set": bool(settings.GEMINI_API_KEY),
        "llm_key_set": bool(settings.PRIMARY_API_KEY),
        "jwt_secret_is_default": settings.JWT_SECRET.startswith("dev-secret") or settings.JWT_SECRET.startswith("change-this"),
    }


@app.get("/health/memory")
def memory():
    """Use this on Render to check that CrewAI + Chroma fit inside the free 512 MB."""
    rss_mb = None
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    rss_mb = round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return {"current_rss_mb": rss_mb, "pid": os.getpid()}


@app.get("/api/rag/search")
def rag_search(q: str = Query(..., min_length=2), k: int = Query(5, ge=1, le=10)):
    """Test endpoint: proves Chroma (inside the image) + Gemini query embedding work on the live server."""
    try:
        results = retriever.search(q, k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "query": q,
        "confident": retriever.is_confident(results),
        "min_score": settings.RAG_MIN_SCORE,
        "results": results,
    }
