"""Central settings. Everything comes from environment variables / .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# Stop CrewAI from asking "Share this execution trace?" and from sending telemetry (these are defaults, .env can override)
for _name, _value in {"CREWAI_TRACING_ENABLED": "false", "CREWAI_DISABLE_TELEMETRY": "true", "OTEL_SDK_DISABLED": "true"}.items():
    os.environ.setdefault(_name, _value)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip().strip('"') if isinstance(value, str) else value


class Settings:
    # ---- LLM (primary + fallback, same idea as Leo) ----
    PRIMARY_API_KEY = _env("GROQ_API_KEY")
    PRIMARY_BASE_URL = _env("BASE_URL", "https://api.groq.com/openai/v1")
    PRIMARY_MODEL = _env("MODEL_NAME", "openai/gpt-oss-120b")

    FALLBACK_API_KEY = _env("FALLBACK_API_KEY") or PRIMARY_API_KEY
    FALLBACK_BASE_URL = _env("FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
    FALLBACK_MODEL = _env("FALLBACK_MODEL_NAME", "openai/gpt-oss-20b")

    # ---- Embeddings ----
    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    EMBED_MODEL = _env("EMBED_MODEL", "gemini-embedding-001")
    EMBED_DIM = int(_env("EMBED_DIM", "768"))
    EMBED_TPM_BUDGET = int(_env("EMBED_TPM_BUDGET", "20000"))

    # ---- RAG ----
    CHROMA_DIR = str(BASE_DIR / "chroma_store")
    RAG_COLLECTION = _env("RAG_COLLECTION", "gov_procedures")
    RAG_TOP_K = int(_env("RAG_TOP_K", "5"))
    RAG_MIN_SCORE = float(_env("RAG_MIN_SCORE", "0.45"))
    GOV_DOCS_DIR = BASE_DIR / "data" / "gov_docs"

    # ---- DB / API ----
    DATABASE_URL = _env("DATABASE_URL", "sqlite:///./local.db")
    ALLOWED_ORIGINS = [o.strip() for o in (_env("ALLOWED_ORIGINS", "*") or "*").split(",") if o.strip()]

    # ---- Login ----
    JWT_SECRET = _env("JWT_SECRET", "dev-secret-change-me")
    JWT_EXPIRE_HOURS = int(_env("JWT_EXPIRE_HOURS", "72"))

    # ---- Behaviour ----
    MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "3"))
    MAX_REPLANS = int(_env("MAX_REPLANS", "1"))
    CHAT_HISTORY_TURNS = int(_env("CHAT_HISTORY_TURNS", "6"))


settings = Settings()
