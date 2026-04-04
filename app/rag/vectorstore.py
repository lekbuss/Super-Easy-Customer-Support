import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)

COLLECTION_NAME = "docuware_kb"


class VectorStore:
    """ChromaDB-backed vector store for the DocuWare knowledge base.

    Documents are stored with their embeddings in a persistent local
    collection so that data survives process restarts.
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
        """Index a list of document chunks.

        Each dict must contain:
            text       (str)  – chunk content
            metadata   (dict) – keys: source_url, title, kba_id, category
        """
        if not docs:
            return

        texts = [d["text"] for d in docs]
        embeddings = self._embedder.embed_batch(texts)

        ids = [str(uuid.uuid4()) for _ in docs]
        metadatas = [
            {
                "source_url": d["metadata"].get("source_url", ""),
                "title": d["metadata"].get("title", ""),
                "kba_id": d["metadata"].get("kba_id", ""),
                "category": d["metadata"].get("category", ""),
            }
            for d in docs
        ]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.debug("Added %d chunks to collection '%s'", len(docs), COLLECTION_NAME)

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

    def count(self) -> int:
        return self._collection.count()
