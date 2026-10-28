"""The RAG tool used by the Procedure Guide agent."""
from app.core.config import settings
from app.rag import retriever
from app.rag.embeddings import EmbeddingError


def make_rag_tool(sources_sink: list):
    """sources_sink is a list we fill with the sources used, so the API can show them to the user."""
    from crewai.tools import tool

    @tool("search_official_docs")
    def search_official_docs(query: str) -> str:
        """Search the official procedure documents (passport, driving licence, tax) saved by the project owner. The query can be Bangla or English. Returns passages with their source."""
        try:
            results = retriever.search(query, settings.RAG_TOP_K)
        except FileNotFoundError:
            return "SEARCH_ERROR: the knowledge base is not built yet."
        except EmbeddingError as exc:
            return f"SEARCH_ERROR: {exc}"

        if not retriever.is_confident(results):
            best = results[0]["score"] if results else 0
            return (f"NO_RELIABLE_INFO: the best match score was {best}. Tell the user you do not have reliable "
                    "information about this and point them to the official government website.")

        blocks = []
        for i, item in enumerate(results, start=1):
            meta = item["metadata"]
            if item["score"] < settings.RAG_MIN_SCORE * 0.8:
                continue
            sources_sink.append({
                "title": meta.get("title", ""), "url": meta.get("url", ""), "page": meta.get("page"),
                "year": meta.get("year", ""), "score": item["score"],
            })
            blocks.append(f"[{i}] source: {meta.get('title')} | page {meta.get('page')} | year {meta.get('year')} | {meta.get('url')}\n{item['text'][:700]}")
        return "\n\n".join(blocks)

    return search_official_docs
