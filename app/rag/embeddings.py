import logging
from functools import cached_property

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Wraps sentence-transformers for text embedding.

    The model is loaded lazily on first use so that importing this module
    does not trigger a heavyweight download at startup.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.embedding_model

    @cached_property
    def _model(self):
        from sentence_transformers import SentenceTransformer  # lazy import

        logger.info("Loading embedding model: %s", self._model_name)
        return SentenceTransformer(self._model_name)

    def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of text strings."""
        if not texts:
            return []
        vectors = self._model.encode(texts, convert_to_numpy=True, batch_size=32)
        return [v.tolist() for v in vectors]
