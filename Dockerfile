FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MALLOC_ARENA_MAX=2 \
    ANONYMIZED_TELEMETRY=False \
    CREWAI_DISABLE_TELEMETRY=true \
    OTEL_SDK_DISABLED=true

WORKDIR /app

# If pip ever fails with a "gcc" error, uncomment the next line:
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
# The vector database is built on your PC (scripts/ingest.py) and shipped inside the image
COPY chroma_store ./chroma_store

EXPOSE 8000
# Render gives the port in $PORT. One worker only: the free plan has 512 MB RAM.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
