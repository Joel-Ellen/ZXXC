"""
AI Learning Assistant - Embedding Service
文本向量化服务 - 使用sentence-transformers
"""
import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from loguru import logger
from config import EMBEDDING_CONFIG


class EmbeddingService:
    """Text embedding service with sentence-transformers"""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or EMBEDDING_CONFIG["model_name"]
        self.dimension = EMBEDDING_CONFIG["dimension"]
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded. Dimension: {self.dimension}")
        return self._model

    def encode(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Encode text to embeddings.
        Returns numpy array of shape (len(texts), dimension)
        """
        if isinstance(texts, str):
            texts = [texts]
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size or EMBEDDING_CONFIG["batch_size"],
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings)

    def encode_single(self, text: str) -> np.ndarray:
        """Encode a single text"""
        return self.encode([text])[0]

    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

    def batch_similarity(self, query_vec: np.ndarray, corpus_vecs: np.ndarray) -> np.ndarray:
        """Compute similarities between query and corpus"""
        query_norm = query_vec / np.linalg.norm(query_vec)
        corpus_norms = corpus_vecs / np.linalg.norm(corpus_vecs, axis=1, keepdims=True)
        return np.dot(corpus_norms, query_norm)


# Singleton
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
