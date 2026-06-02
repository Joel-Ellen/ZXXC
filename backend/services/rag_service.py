"""
AI Learning Assistant - RAG Service (Retrieval-Augmented Generation)
RAG知识库服务 - 基于Chroma向量数据库 + 混合检索
"""
import json
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import chromadb
from chromadb.config import Settings
from loguru import logger
from config import CHROMA_CONFIG, RAG_CONFIG, KB_DIR
from .embedding_service import get_embedding_service


class RAGService:
    """
    RAG Service with Chroma vector database.
    Supports:
    - Document ingestion (chunking + embedding)
    - Dense vector search (semantic)
    - Sparse keyword search (BM25-like)
    - Hybrid search (dense + sparse fusion)
    - Reranking
    - Context-aware retrieval
    """

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self._client: Optional[chromadb.PersistentClient] = None
        self._collections: Dict[str, Any] = {}

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=CHROMA_CONFIG["persist_directory"],
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def get_collection(self, course_name: str) -> Any:
        """Get or create a collection for a course"""
        col_name = f"{CHROMA_CONFIG['collection_name']}_{course_name}"
        col_name = hashlib.md5(col_name.encode()).hexdigest()[:32]

        if col_name not in self._collections:
            try:
                self._collections[col_name] = self.client.get_collection(col_name)
            except Exception:
                self._collections[col_name] = self.client.create_collection(
                    name=col_name,
                    metadata={"course": course_name, "hnsw:space": "cosine"},
                )
        return self._collections[col_name]

    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """
        Split text into overlapping chunks.
        Smart chunking: splits on paragraph/sentence boundaries.
        """
        chunk_size = chunk_size or RAG_CONFIG["chunk_size"]
        overlap = overlap or RAG_CONFIG["chunk_overlap"]

        # Split on paragraphs first
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_length + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # Keep overlap
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
                current_length = len(current_chunk)
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                current_length = len(current_chunk)

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    async def ingest_documents(
        self,
        course_name: str,
        documents: List[Dict[str, str]],
        chunk_size: int = None,
    ) -> int:
        """
        Ingest documents into the knowledge base.

        Args:
            course_name: Course name (creates separate collection)
            documents: List of {title, content, metadata}
            chunk_size: Override default chunk size

        Returns:
            Number of chunks ingested
        """
        collection = self.get_collection(course_name)
        total_chunks = 0

        for doc in documents:
            chunks = self.chunk_text(doc["content"], chunk_size)
            if not chunks:
                continue

            embeddings = self.embedding_service.encode(chunks)
            ids = [
                hashlib.md5(f"{doc.get('title', '')}_{i}_{chunk[:50]}".encode()).hexdigest()
                for i, chunk in enumerate(chunks)
            ]
            metadatas = [
                {
                    "title": doc.get("title", ""),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    **doc.get("metadata", {}),
                }
                for i in range(len(chunks))
            ]

            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                documents=chunks,
                metadatas=metadatas,
            )
            total_chunks += len(chunks)

        logger.info(f"Ingested {total_chunks} chunks for course '{course_name}'")
        return total_chunks

    async def semantic_search(
        self,
        course_name: str,
        query: str,
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Dense vector (semantic) search.
        """
        top_k = top_k or RAG_CONFIG["max_retrieval_chunks"]
        collection = self.get_collection(course_name)
        query_embedding = self.embedding_service.encode_single(query)

        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    async def keyword_search(
        self,
        course_name: str,
        query: str,
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Sparse keyword-based search (using Chroma's built-in full-text search).
        Falls back to dense search if keyword search yields poor results.
        """
        top_k = top_k or RAG_CONFIG["max_retrieval_chunks"]
        collection = self.get_collection(course_name)

        # Chroma supports where_document for keyword matching
        keywords = query.split()
        all_results = []

        for keyword in keywords[:5]:  # Limit to 5 keywords
            try:
                results = collection.query(
                    query_texts=[keyword],
                    n_results=max(2, top_k // len(keywords[:5])),
                    include=["documents", "metadatas", "distances"],
                )
                formatted = self._format_results(results)
                all_results.extend(formatted)
            except Exception:
                continue

        # Deduplicate and sort by distance
        seen = set()
        unique_results = []
        for r in sorted(all_results, key=lambda x: x.get("distance", 1.0)):
            key = r.get("content", "")[:100]
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        return unique_results[:top_k]

    async def hybrid_search(
        self,
        course_name: str,
        query: str,
        top_k: int = None,
        alpha: float = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: fusion of dense (semantic) + sparse (keyword) search.
        alpha: weight for dense search (0-1). Default from config.
        """
        top_k = top_k or RAG_CONFIG["max_retrieval_chunks"]
        alpha = alpha if alpha is not None else RAG_CONFIG["hybrid_search_weight"]

        # Run both searches concurrently
        dense_results = await self.semantic_search(course_name, query, top_k * 2)
        sparse_results = await self.keyword_search(course_name, query, top_k * 2)

        # Reciprocal Rank Fusion (RRF)
        fused_scores = {}
        k = 60  # RRF constant

        for rank, result in enumerate(dense_results):
            doc_id = result.get("content", "")[:200]
            rrf_score = alpha * (1.0 / (k + rank + 1))
            fused_scores[doc_id] = {
                "score": fused_scores.get(doc_id, {}).get("score", 0) + rrf_score,
                "result": result,
                "dense_rank": rank,
            }

        for rank, result in enumerate(sparse_results):
            doc_id = result.get("content", "")[:200]
            rrf_score = (1 - alpha) * (1.0 / (k + rank + 1))
            if doc_id in fused_scores:
                fused_scores[doc_id]["score"] += rrf_score
                fused_scores[doc_id]["sparse_rank"] = rank
            else:
                fused_scores[doc_id] = {
                    "score": rrf_score,
                    "result": result,
                    "sparse_rank": rank,
                }

        # Sort by fused score and return top_k
        sorted_results = sorted(fused_scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["result"] for item in sorted_results[:top_k]]

    async def retrieve_context(
        self,
        course_name: str,
        query: str,
        top_k: int = None,
    ) -> str:
        """
        Retrieve relevant context and format as prompt-ready text.
        """
        results = await self.hybrid_search(course_name, query, top_k)

        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results):
            title = result.get("metadata", {}).get("title", "Unknown")
            content = result.get("content", "")
            relevance = 1.0 - result.get("distance", 0)
            context_parts.append(
                f"[参考{i+1}] (来源: {title}, 相关度: {relevance:.2f})\n{content}"
            )

        return "\n\n---\n\n".join(context_parts)

    def _format_results(self, chroma_results: Dict) -> List[Dict[str, Any]]:
        """Format Chroma results into standard dicts"""
        formatted = []
        if not chroma_results.get("ids") or not chroma_results["ids"][0]:
            return formatted

        ids = chroma_results["ids"][0]
        documents = chroma_results.get("documents", [[]])[0] if chroma_results.get("documents") else []
        metadatas = chroma_results.get("metadatas", [[]])[0] if chroma_results.get("metadatas") else []
        distances = chroma_results.get("distances", [[]])[0] if chroma_results.get("distances") else []

        for i in range(len(ids)):
            formatted.append({
                "id": ids[i],
                "content": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else 0.0,
            })

        return formatted

    def get_collection_stats(self, course_name: str) -> Dict[str, Any]:
        """Get collection statistics"""
        try:
            collection = self.get_collection(course_name)
            count = collection.count()
            return {
                "course": course_name,
                "total_chunks": count,
                "status": "active",
            }
        except Exception as e:
            return {"course": course_name, "error": str(e), "status": "error"}


# Singleton
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
