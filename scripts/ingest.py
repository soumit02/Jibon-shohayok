"""
Builds chroma_store/ from your official documents (run on YOUR PC, not on the server).

Put files here:   data/gov_docs/<topic>/<file>.pdf|txt|md      e.g. data/gov_docs/passport/renewal_guide.pdf
Optional file:    data/gov_docs/sources.json
    { "renewal_guide.pdf": {"title": "Passport renewal guide", "url": "https://...", "year": "2026"} }

Run from the project root:   python scripts/ingest.py
Afterwards commit/copy the whole chroma_store/ folder - it is shipped inside the Docker image.
(Same chunking idea as your Bangla RAG project: size 500, overlap 100, Bangla danda separators.)
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.rag.embeddings import get_embedder

CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_CHARS = 500, 100, 40


def clean_text(text: str) -> str:
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_pages(path: Path) -> list[tuple[int, str]]:
    """Returns [(page_number, text)]"""
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as pdf:
            return [(i + 1, clean_text(page.get_text())) for i, page in enumerate(pdf)]
    return [(1, clean_text(path.read_text(encoding="utf-8")))]


def main():
    docs_dir = settings.GOV_DOCS_DIR
    files = [p for p in docs_dir.rglob("*") if p.suffix.lower() in {".pdf", ".txt", ".md"}]
    if not files:
        print(f"No documents found in {docs_dir}. Add PDFs (e.g. data/gov_docs/passport/guide.pdf) and run again.")
        return

    sources = {}
    sources_file = docs_dir / "sources.json"
    if sources_file.exists():
        sources = json.loads(sources_file.read_text(encoding="utf-8"))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "। ", "।", "? ", "! ", ". ", " ", ""],
    )

    texts, metas = [], []
    for path in sorted(files):
        topic = path.parent.name if path.parent != docs_dir else "general"
        info = sources.get(path.name, {})
        print(f"Reading {path.relative_to(docs_dir)} ...")
        for page_no, page_text in read_pages(path):
            for chunk in splitter.split_text(page_text):
                if len(chunk.strip()) < MIN_CHUNK_CHARS:
                    continue
                texts.append(chunk)
                metas.append({
                    "topic": topic,
                    "source_file": path.name,
                    "title": info.get("title", path.stem),
                    "url": info.get("url", ""),
                    "year": str(info.get("year", "unknown")),
                    "page": page_no,
                    "chunk_index": len(texts),
                })

    print(f"\n{len(texts)} chunks from {len(files)} files. Embedding with Gemini (this can take a few minutes on the free tier)...")
    vectors = get_embedder().embed_documents(texts)

    if Path(settings.CHROMA_DIR).exists():
        shutil.rmtree(settings.CHROMA_DIR)  # never mix old and new vectors
    client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
    collection = client.create_collection(
        settings.RAG_COLLECTION, embedding_function=None, metadata={"hnsw:space": "cosine"}
    )
    for start in range(0, len(texts), 100):
        end = start + 100
        collection.add(
            ids=[f"chunk-{i}" for i in range(start, min(end, len(texts)))],
            documents=texts[start:end],
            embeddings=vectors[start:end],
            metadatas=metas[start:end],
        )
    print(f"Done. Stored {collection.count()} chunks in '{settings.CHROMA_DIR}'.")


if __name__ == "__main__":
    main()
