"""RAG administration helpers."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

COLLECTION_NAME = "docuware_kb"


def get_stats() -> dict:
    """Return ChromaDB collection statistics."""
    try:
        from app.rag.vectorstore import VectorStore
        store = VectorStore()
        return {
            "collection": COLLECTION_NAME,
            "document_count": store.count(),
            "status": "ok",
        }
    except Exception as exc:
        logger.warning("RAG get_stats failed: %s", exc)
        return {
            "collection": COLLECTION_NAME,
            "document_count": 0,
            "status": f"error: {exc}",
        }


def clear_collection() -> dict:
    """Delete and recreate the ChromaDB collection."""
    try:
        from app.rag.vectorstore import VectorStore
        store = VectorStore()
        store.clear()
        logger.info("RAG collection '%s' cleared", COLLECTION_NAME)
        return {"collection": COLLECTION_NAME, "status": "cleared"}
    except Exception as exc:
        logger.warning("RAG clear_collection failed: %s", exc)
        return {"collection": COLLECTION_NAME, "status": f"error: {exc}"}
