import hashlib
import logging
from pathlib import Path

from app.core.config import settings
from app.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)

COLLECTION_NAME = "docuware_kb"


class VectorStore:
    """ChromaDB-backed vector store for the DocuWare knowledge base.

    Documents are stored with their embeddings in a persistent local
    collection so that data survives process restarts.

    Document IDs are deterministic (md5 of source_url + chunk index),
    so re-indexing the same article overwrites rather than duplicates.
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        import chromadb  # lazy import

        self._persist_dir = persist_dir or settings.chroma_persist_dir
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = embedding_service or EmbeddingService()
        logger.info(
            "VectorStore ready — collection '%s', %d existing docs",
            COLLECTION_NAME,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def add_documents(self, docs: list[dict]) -> None:
        """Index a list of document chunks (upsert — same URL+index overwrites).

        Each dict must contain:
            text       (str)  – chunk content
            metadata   (dict) – keys: source_url, title, kba_id, category
        """
        if not docs:
            return

        texts = [d["text"] for d in docs]
        embeddings = self._embedder.embed_batch(texts)

        # Deterministic IDs: md5(source_url::chunk_index)
        ids = [
            hashlib.md5(
                f"{d['metadata'].get('source_url', '')}::{i}".encode()
            ).hexdigest()
            for i, d in enumerate(docs)
        ]
        metadatas = [
            {
                "source_url": d["metadata"].get("source_url", ""),
                "title": d["metadata"].get("title", ""),
                "kba_id": d["metadata"].get("kba_id", ""),
                "category": d["metadata"].get("category", ""),
            }
            for d in docs
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.debug("Upserted %d chunks to collection '%s'", len(docs), COLLECTION_NAME)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """Return the top-k most relevant chunks for the query.

        Each result dict contains:
            text       – chunk content
            score      – cosine similarity (higher is better)
            metadata   – source_url, title, kba_id, category
        """
        k = top_k if top_k is not None else settings.rag_top_k
        query_embedding = self._embedder.embed_text(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, max(self._collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]

        for text, meta, dist in zip(documents[0], metadatas[0], distances[0]):
            hits.append(
                {
                    "text": text,
                    "score": round(1.0 - dist, 4),  # cosine distance → similarity
                    "metadata": meta,
                }
            )
        return hits

    def has_url(self, source_url: str) -> bool:
        """Return True if any chunk for this source_url already exists."""
        results = self._collection.get(
            where={"source_url": source_url},
            limit=1,
            include=[],
        )
        return len(results["ids"]) > 0

    def clear(self) -> None:
        """Delete all documents by recreating the collection."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("VectorStore cleared — collection '%s' recreated", COLLECTION_NAME)

    def count(self) -> int:
        return self._collection.count()
