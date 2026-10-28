# Jibon Shohayok: Personal Life-Admin Assistant (Capstone, Track A)

Multi-agent personal assistant: CrewAI + FastAPI + Chroma (RAG) + PostgreSQL + Docker. Frontend: Lovable.

## Run locally (Windows PowerShell)
```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then fill in the keys
python scripts/test_embedding.py   # Gemini + Bangla check
python scripts/test_llm.py         # Groq primary + fallback check
python scripts/ingest.py           # builds chroma_store/ from data/gov_docs/
uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs
```

## Run with Docker
```
docker compose up --build          # API on http://localhost:8000, PostgreSQL included
```

## Deploy (Render + Neon)
1. Neon: create a project, copy the connection string -> `DATABASE_URL` on Render.
2. Push this folder to GitHub (keep `chroma_store/` committed).
3. Render: New > Web Service > Docker > connect the repo. Health check path: `/health`.
4. Environment variables on Render: everything from `.env.example`.
5. Open `/health`, `/health/memory` and `/api/rag/search?q=...` on the live URL.

Free Render services sleep after 15 minutes; the first request afterwards takes about a minute.

## Day 2: the four crews, login, documents, reminders
Test everything in the terminal first (no frontend needed):
```
python scripts/seed_travel_costs.py   # after replacing the 0 values in data/travel_costs.csv
python scripts/try_chat.py
```
Then start the API (`uvicorn app.main:app --reload`), open `/docs`, register at `POST /api/auth/register`,
press **Authorize** (email in the "username" box) and try `POST /api/chat`.

Flow for documents: `POST /api/documents/upload` -> check the values -> `POST /api/documents/{id}/confirm`.
Flow for reminders: `POST /api/chat` returns `proposed_actions` -> user presses Yes -> `POST /api/actions/approve`.
