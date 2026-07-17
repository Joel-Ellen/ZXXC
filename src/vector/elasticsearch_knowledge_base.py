# -*- coding: utf-8 -*-
"""
Elasticsearch-based knowledge base ingestion and hybrid retrieval.

This module is tailored for dense educational Markdown documents that contain:
1. Strong heading hierarchy (# / ## / ###).
2. High-density code blocks that must never be truncated.
3. LaTeX formulas and complexity expressions.
4. Rich metadata inheritance for downstream hybrid retrieval.
"""

from __future__ import annotations

import hashlib
import os
import re
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, field_validator

try:
    from elasticsearch import AuthorizationException, Elasticsearch, helpers
except ImportError:  # pragma: no cover - optional dependency
    AuthorizationException = None  # type: ignore[assignment]
    Elasticsearch = None  # type: ignore[assignment]
    helpers = None  # type: ignore[assignment]

try:
    from langchain_text_splitters import MarkdownHeaderTextSplitter
except ImportError:  # pragma: no cover - optional dependency
    MarkdownHeaderTextSplitter = None  # type: ignore[assignment]


CODE_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
LATEX_INLINE_RE = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$")
LATEX_BLOCK_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|\\\[(.+?)\\\]", re.DOTALL)
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_+#.-]+")
DEFAULT_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


class ElasticsearchKnowledgeBaseConfig(BaseModel):
    """Configuration for ES-backed Markdown knowledge base indexing."""

    hosts: List[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:9200"],
        description="Elasticsearch hosts.",
    )
    index_name: str = Field(default="eduagent_knowledge_base", min_length=1)
    vector_dims: int = Field(default=1024, ge=64, le=8192)
    chunk_size_chars: int = Field(default=1000, ge=800, le=1200)
    chunk_overlap_chars: int = Field(default=150, ge=0, le=400)
    headers_to_split_on: List[Tuple[str, str]] = Field(
        default_factory=lambda: list(DEFAULT_HEADERS)
    )
    language_tag_normalization: Dict[str, str] = Field(
        default_factory=lambda: {
            "cpp": "C++",
            "c++": "C++",
            "c": "C",
            "python": "Python",
            "py": "Python",
            "java": "Java",
            "javascript": "JavaScript",
            "js": "JavaScript",
            "typescript": "TypeScript",
            "ts": "TypeScript",
            "go": "Go",
            "rust": "Rust",
        }
    )
    rrf_rank_constant: int = Field(default=60, ge=1, le=500)
    rrf_rank_window_size: int = Field(default=50, ge=5, le=500)
    request_timeout: int = Field(default=30, ge=1, le=300)
    verify_certs: bool = Field(default=True)
    ca_certs: Optional[str] = Field(default=None)
    basic_auth_user: Optional[str] = Field(default=None)
    basic_auth_password: Optional[str] = Field(default=None)

    @field_validator("headers_to_split_on")
    @classmethod
    def _validate_headers(cls, value: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        if not value:
            raise ValueError("headers_to_split_on cannot be empty")
        return value


class KnowledgeBaseChunk(BaseModel):
    """Final ES document for a single chunk."""

    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    course_id: str = Field(default="")
    node_ids: List[str] = Field(default_factory=list)
    content_kind: str = Field(default="explanation")
    locale: str = Field(default="zh-CN")
    content_version: str = Field(default="1")
    source_path: str = Field(..., min_length=1)
    chunk_index: int = Field(default=0, ge=0)
    content: str = Field(..., min_length=1)
    content_length: int = Field(..., ge=1)
    chapter: str = Field(default="")
    section: str = Field(default="")
    knowledge_point: str = Field(default="")
    title_path: str = Field(default="")
    heading_hierarchy: List[str] = Field(default_factory=list)
    language_tags: List[str] = Field(default_factory=list)
    has_code_block: bool = Field(default=False)
    has_latex: bool = Field(default=False)
    code_block_count: int = Field(default=0, ge=0)
    latex_formula_count: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = Field(default=None)


class HashingTextEmbedder:
    """Deterministic local embedder for smoke tests and offline indexing.

    It is intentionally dependency-free. For production retrieval quality, replace it
    with a real embedding model through set_embedding_function().
    """

    def __init__(self, dims: int = 1024) -> None:
        if dims < 64:
            raise ValueError("dims must be at least 64")
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self._dims
        for token in self._tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self._dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]

    def _tokens(self, text: str) -> Iterable[str]:
        lowered = text.lower()
        for match in TOKEN_RE.finditer(lowered):
            token = match.group(0).strip()
            if token:
                yield token


class SentenceTransformerEmbedder:
    """Real local embedding backend based on sentence-transformers."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        *,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "sentence-transformers is required for real local embeddings. "
                "Install it with: pip install sentence-transformers"
            ) from exc

        kwargs: Dict[str, Any] = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(model_name, **kwargs)
        self._model_name = model_name
        self._normalize_embeddings = normalize_embeddings
        if hasattr(self._model, "get_embedding_dimension"):
            dims = self._model.get_embedding_dimension()
        else:
            dims = self._model.get_sentence_embedding_dimension()
        if dims is None:
            raise RuntimeError(f"Cannot determine embedding dimension for model {model_name!r}.")
        self._dims = int(dims)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dims(self) -> int:
        return self._dims

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=self._normalize_embeddings,
            show_progress_bar=False,
        )
        return [vector.astype(float).tolist() for vector in vectors]


@dataclass
class _PhysicalSection:
    """Intermediate section generated from Markdown headers."""

    content: str
    metadata: Dict[str, str]


@dataclass
class _HeaderSplitDocument:
    """Minimal fallback document compatible with LangChain splitter output."""

    page_content: str
    metadata: Dict[str, str]


class MarkdownKnowledgeBaseChunker:
    """Header-aware chunker with code-fence protection and metadata inheritance."""

    def __init__(self, config: Optional[ElasticsearchKnowledgeBaseConfig] = None) -> None:
        self._config = config or ElasticsearchKnowledgeBaseConfig()
        self._header_splitter = self._build_header_splitter()

    @property
    def config(self) -> ElasticsearchKnowledgeBaseConfig:
        return self._config

    def chunk_markdown(
        self,
        markdown_text: str,
        *,
        document_id: str,
        source_path: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeBaseChunk]:
        """Split a Markdown document into ES-ready chunks."""
        extra_metadata = extra_metadata or {}
        physical_sections = self._split_by_headers(markdown_text)
        chunks: List[KnowledgeBaseChunk] = []

        for section in physical_sections:
            section_chunks = self._split_section_with_protection(section.content)
            inherited = self._build_context_metadata(section.metadata)
            for chunk_text in section_chunks:
                normalized = chunk_text.strip()
                if not normalized:
                    continue
                chunk_index = len(chunks)
                chunk_id = self._make_chunk_id(document_id, chunk_index, normalized)
                language_tags = self._extract_language_tags(normalized)
                has_latex = bool(LATEX_BLOCK_RE.search(normalized) or LATEX_INLINE_RE.search(normalized))
                code_block_count = len(CODE_FENCE_RE.findall(normalized))
                latex_formula_count = len(LATEX_BLOCK_RE.findall(normalized)) + len(LATEX_INLINE_RE.findall(normalized))

                chunk_metadata = {
                    **extra_metadata,
                    **inherited,
                    "source_path": source_path,
                }

                chunks.append(
                    KnowledgeBaseChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        course_id=str(extra_metadata.get("course_id") or ""),
                        node_ids=[
                            str(value)
                            for value in extra_metadata.get("node_ids", [])
                            if str(value).strip()
                        ],
                        content_kind=str(
                            extra_metadata.get("content_kind") or "explanation"
                        ),
                        locale=str(extra_metadata.get("locale") or "zh-CN"),
                        content_version=str(
                            extra_metadata.get("content_version") or "1"
                        ),
                        source_path=source_path,
                        chunk_index=chunk_index,
                        content=normalized,
                        content_length=len(normalized),
                        chapter=inherited["chapter"],
                        section=inherited["section"],
                        knowledge_point=inherited["knowledge_point"],
                        title_path=inherited["title_path"],
                        heading_hierarchy=inherited["heading_hierarchy"],
                        language_tags=language_tags,
                        has_code_block=code_block_count > 0,
                        has_latex=has_latex,
                        code_block_count=code_block_count,
                        latex_formula_count=latex_formula_count,
                        metadata=chunk_metadata,
                    )
                )

        return chunks

    def _build_header_splitter(self) -> Any:
        if MarkdownHeaderTextSplitter is None:
            return None
        return MarkdownHeaderTextSplitter(
            headers_to_split_on=self._config.headers_to_split_on,
            strip_headers=False,
        )

    def _split_by_headers(self, markdown_text: str) -> List[_PhysicalSection]:
        if self._header_splitter is None:
            documents = self._fallback_split_by_headers(markdown_text)
        else:
            documents = self._header_splitter.split_text(markdown_text)
        sections: List[_PhysicalSection] = []
        for doc in documents:
            content = getattr(doc, "page_content", "") or ""
            metadata = dict(getattr(doc, "metadata", {}) or {})
            if content.strip():
                sections.append(_PhysicalSection(content=content, metadata=metadata))
        return sections

    def _fallback_split_by_headers(self, markdown_text: str) -> List[_HeaderSplitDocument]:
        """Dependency-free header splitter used when LangChain is unavailable."""
        lines = markdown_text.splitlines(keepends=True)
        sections: List[_HeaderSplitDocument] = []
        current_lines: List[str] = []
        current_metadata: Dict[str, str] = {}

        for line in lines:
            stripped = line.lstrip()
            matched_header = False
            for prefix, key in sorted(
                self._config.headers_to_split_on,
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                if stripped.startswith(f"{prefix} "):
                    if current_lines and self._section_has_meaningful_body(current_lines):
                        sections.append(
                            _HeaderSplitDocument(
                                page_content="".join(current_lines),
                                metadata=dict(current_metadata),
                            )
                        )
                    current_lines = [line]
                    current_metadata = self._updated_heading_metadata(
                        current_metadata,
                        key,
                        stripped[len(prefix):].strip(),
                    )
                    matched_header = True
                    break

            if not matched_header:
                current_lines.append(line)

        if current_lines and self._section_has_meaningful_body(current_lines):
            sections.append(
                _HeaderSplitDocument(
                    page_content="".join(current_lines),
                    metadata=dict(current_metadata),
                )
            )

        return sections

    def _section_has_meaningful_body(self, lines: List[str]) -> bool:
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if any(
                stripped.startswith(f"{prefix} ")
                for prefix, _key in self._config.headers_to_split_on
            ):
                continue
            return True
        return False

    def _updated_heading_metadata(
        self,
        metadata: Dict[str, str],
        header_key: str,
        header_value: str,
    ) -> Dict[str, str]:
        updated = dict(metadata)
        updated[header_key] = header_value

        # Clear lower-level headings when a higher-level heading changes.
        header_order = [name for _prefix, name in self._config.headers_to_split_on]
        try:
            idx = header_order.index(header_key)
        except ValueError:
            return updated

        for lower_key in header_order[idx + 1:]:
            updated.pop(lower_key, None)

        return updated

    def _split_section_with_protection(self, text: str) -> List[str]:
        """Character-window chunking that never slices through code fences."""
        max_size = self._config.chunk_size_chars
        overlap = self._config.chunk_overlap_chars
        if len(text) <= max_size:
            return [text]

        chunks: List[str] = []
        start = 0
        text_len = len(text)
        previous_start = -1

        while start < text_len:
            end = min(start + max_size, text_len)
            adjusted_end = self._adjust_split_end(text, start, end)
            if adjusted_end <= start:
                adjusted_end = min(text_len, start + max_size)
                if adjusted_end <= start:
                    break

            chunk = text[start:adjusted_end].strip()
            if chunk:
                chunks.append(chunk)

            if adjusted_end >= text_len:
                break

            next_start = max(0, adjusted_end - overlap)
            next_start = self._adjust_split_start(text, next_start)
            if next_start <= start:
                next_start = adjusted_end
            if next_start == previous_start:
                next_start = adjusted_end
            previous_start = start
            start = next_start

        return chunks

    def _adjust_split_end(self, text: str, start: int, end: int) -> int:
        """Prefer semantic boundaries, but extend when split lands inside a code fence."""
        candidate = self._prefer_natural_boundary(text, start, end)
        if self._is_inside_code_fence(text, candidate):
            fence_close = text.find("```", candidate)
            if fence_close != -1:
                candidate = min(len(text), fence_close + 3)
        return candidate

    def _adjust_split_start(self, text: str, start: int) -> int:
        """Avoid starting inside a fenced code block."""
        if not self._is_inside_code_fence(text, start):
            return start
        fence_open = text.rfind("```", 0, start)
        return fence_open if fence_open != -1 else start

    def _prefer_natural_boundary(self, text: str, start: int, end: int) -> int:
        if end >= len(text):
            return len(text)

        window = text[start:end]
        candidates = [
            window.rfind("\n### "),
            window.rfind("\n## "),
            window.rfind("\n# "),
            window.rfind("\n```"),
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind("。"),
            window.rfind("；"),
            window.rfind("，"),
            window.rfind(" "),
        ]
        best_offset = max(candidates)
        if best_offset <= int(len(window) * 0.55):
            return end
        return start + best_offset + 1

    def _is_inside_code_fence(self, text: str, pos: int) -> bool:
        return text[:pos].count("```") % 2 == 1

    def _build_context_metadata(self, metadata: Dict[str, str]) -> Dict[str, Any]:
        headings = [metadata.get("h1", "").strip(), metadata.get("h2", "").strip(), metadata.get("h3", "").strip()]
        headings = [item for item in headings if item]
        chapter = metadata.get("h1", "").strip()
        section = metadata.get("h2", "").strip()
        knowledge_point = metadata.get("h3", "").strip()

        title_path_items = ["数据结构"]
        title_path_items.extend(headings)

        return {
            "chapter": chapter,
            "section": section,
            "knowledge_point": knowledge_point,
            "heading_hierarchy": headings,
            "title_path": " > ".join(title_path_items),
        }

    def _extract_language_tags(self, text: str) -> List[str]:
        tags: List[str] = []
        seen = set()
        for raw_language, _code in CODE_FENCE_RE.findall(text):
            normalized = self._normalize_language_tag(raw_language.strip())
            if normalized and normalized not in seen:
                tags.append(normalized)
                seen.add(normalized)
        return tags

    def _normalize_language_tag(self, language: str) -> str:
        if not language:
            return ""
        normalized = language.lower()
        return self._config.language_tag_normalization.get(normalized, language)

    def _make_chunk_id(self, document_id: str, chunk_index: int, content: str) -> str:
        digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:10]
        return f"{document_id}_chunk_{chunk_index:05d}_{digest}"


class ElasticsearchKnowledgeBaseClient:
    """Thin Elasticsearch client wrapper for indexing and hybrid retrieval."""

    def __init__(self, config: Optional[ElasticsearchKnowledgeBaseConfig] = None) -> None:
        self._config = config or ElasticsearchKnowledgeBaseConfig()
        self._client: Optional[Any] = None
        self._embed_fn: Optional[Callable[[str], List[float]]] = None
        self._batch_embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None

    @property
    def config(self) -> ElasticsearchKnowledgeBaseConfig:
        return self._config

    def connect(self) -> None:
        if Elasticsearch is None:
            raise ImportError(
                "elasticsearch is required. Install it with: pip install elasticsearch"
            )
        kwargs: Dict[str, Any] = {
            "hosts": self._config.hosts,
            "request_timeout": self._config.request_timeout,
            "verify_certs": self._config.verify_certs,
        }
        if self._config.basic_auth_user and self._config.basic_auth_password:
            kwargs["basic_auth"] = (
                self._config.basic_auth_user,
                self._config.basic_auth_password,
            )
        if self._config.ca_certs:
            kwargs["ca_certs"] = self._config.ca_certs
        self._client = Elasticsearch(**kwargs)

    def is_connected(self) -> bool:
        return self._client is not None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def set_embedding_function(
        self,
        embed_fn: Callable[[str], List[float]],
        batch_embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None,
    ) -> None:
        self._embed_fn = embed_fn
        self._batch_embed_fn = batch_embed_fn

    def create_index(self, recreate: bool = False) -> None:
        client = self._ensure_client()
        index_name = self._config.index_name

        if recreate and client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)

        if client.indices.exists(index=index_name):
            return

        client.indices.create(
            index=index_name,
            mappings=self._build_index_mappings(),
            settings=self._build_index_settings(),
        )

    def switch_aliases(
        self,
        physical_index: str,
        *,
        read_alias: str = "resource-kb-v4-read",
        write_alias: str = "resource-kb-v4-write",
    ) -> None:
        """Atomically move the v4 read/write aliases to a validated index."""
        client = self._ensure_client()
        actions: List[Dict[str, Any]] = []
        for alias in (read_alias, write_alias):
            try:
                current = client.indices.get_alias(name=alias)
            except Exception:
                current = {}
            for index_name in current:
                actions.append(
                    {"remove": {"index": index_name, "alias": alias}}
                )
        actions.extend([
            {"add": {"index": physical_index, "alias": read_alias}},
            {
                "add": {
                    "index": physical_index,
                    "alias": write_alias,
                    "is_write_index": True,
                }
            },
        ])
        client.indices.update_aliases(actions=actions)

    def rollback_read_alias(
        self,
        previous_index: str,
        *,
        read_alias: str = "resource-kb-v4-read",
    ) -> None:
        """Roll back readers without changing the active ingestion target."""
        client = self._ensure_client()
        actions: List[Dict[str, Any]] = []
        try:
            current = client.indices.get_alias(name=read_alias)
        except Exception:
            current = {}
        for index_name in current:
            actions.append(
                {"remove": {"index": index_name, "alias": read_alias}}
            )
        actions.append(
            {"add": {"index": previous_index, "alias": read_alias}}
        )
        client.indices.update_aliases(actions=actions)

    def bulk_index_chunks(self, chunks: Sequence[KnowledgeBaseChunk]) -> int:
        if not chunks:
            return 0
        client = self._ensure_client()
        prepared_chunks = self._attach_embeddings(list(chunks))

        actions = []
        for chunk in prepared_chunks:
            actions.append(
                {
                    "_index": self._config.index_name,
                    "_id": chunk.chunk_id,
                    "_source": chunk.model_dump(),
                }
            )

        if helpers is None:
            raise ImportError(
                "elasticsearch.helpers is unavailable. Reinstall the elasticsearch package."
            )

        helpers.bulk(client, actions)
        client.indices.refresh(index=self._config.index_name)
        return len(actions)

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute hybrid retrieval.

        ES-native RRF is attempted first. Some Basic-license clusters reject it,
        so we transparently fall back to client-side RRF over separate BM25 and
        HNSW searches.
        """
        client = self._ensure_client()
        vector = self._embed_query(query)
        request_body = self.build_rrf_search_body(
            query=query,
            query_vector=vector,
            top_k=top_k,
            filters=filters,
        )
        try:
            return client.search(index=self._config.index_name, **request_body)
        except Exception as exc:
            if self._is_rrf_license_error(exc):
                return self.hybrid_search_client_rrf(
                    query=query,
                    query_vector=vector,
                    top_k=top_k,
                    filters=filters,
                )
            raise

    def lexical_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Retrieve text chunks without requiring an embedding runtime.

        Worker-side resource generation must be able to use the course KB even
        when a local sentence-transformer is intentionally not loaded.  This
        bounded BM25 path is also the safe fallback for an index whose vector
        dimensions are not known to the application process.
        """
        client = self._ensure_client()
        return client.search(
            index=self._config.index_name,
            size=top_k,
            query={
                "bool": {
                    "must": [{
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "content^4",
                                "title_path^3",
                                "chapter^2",
                                "section^2",
                                "knowledge_point^2",
                                "language_tags",
                            ],
                        }
                    }],
                    "filter": self._build_filter_clauses(filters or {}),
                }
            },
        )

    def hybrid_search_client_rrf(
        self,
        *,
        query: str,
        query_vector: Sequence[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Client-side RRF fallback for clusters without native RRF license."""
        client = self._ensure_client()
        filter_clauses = self._build_filter_clauses(filters or {})
        rank_window_size = max(top_k, self._config.rrf_rank_window_size)

        bm25_result = client.search(
            index=self._config.index_name,
            size=rank_window_size,
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "content^4",
                                    "title_path^3",
                                    "chapter^2",
                                    "section^2",
                                    "knowledge_point^2",
                                    "language_tags",
                                ],
                            }
                        }
                    ],
                    "filter": filter_clauses,
                }
            },
        )

        knn_result = client.search(
            index=self._config.index_name,
            size=rank_window_size,
            knn={
                "field": "embedding",
                "query_vector": list(query_vector),
                "k": rank_window_size,
                "num_candidates": max(rank_window_size * 4, 100),
                "filter": filter_clauses,
            },
        )

        fused_hits = self._fuse_hits_with_rrf(
            bm25_result["hits"]["hits"],
            knn_result["hits"]["hits"],
            top_k=top_k,
        )
        return {
            "took": bm25_result.get("took", 0) + knn_result.get("took", 0),
            "timed_out": bm25_result.get("timed_out", False) or knn_result.get("timed_out", False),
            "_shards": bm25_result.get("_shards", knn_result.get("_shards", {})),
            "hits": {
                "total": {"value": len(fused_hits), "relation": "eq"},
                "max_score": fused_hits[0]["_score"] if fused_hits else None,
                "hits": fused_hits,
            },
            "retrieval_mode": "client_side_rrf",
        }

    def build_rrf_search_body(
        self,
        *,
        query: str,
        query_vector: Sequence[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        filter_clauses = self._build_filter_clauses(filters or {})
        body: Dict[str, Any] = {
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {
                            "standard": {
                                "query": {
                                    "bool": {
                                        "must": [
                                            {
                                                "multi_match": {
                                                    "query": query,
                                                    "fields": [
                                                        "content^4",
                                                        "title_path^3",
                                                        "chapter^2",
                                                        "section^2",
                                                        "knowledge_point^2",
                                                        "language_tags",
                                                    ],
                                                }
                                            }
                                        ],
                                        "filter": filter_clauses,
                                    }
                                }
                            }
                        },
                        {
                            "knn": {
                                "field": "embedding",
                                "query_vector": list(query_vector),
                                "k": top_k,
                                "num_candidates": max(top_k * 4, 20),
                                "filter": filter_clauses,
                            }
                        },
                    ],
                    "rank_constant": self._config.rrf_rank_constant,
                    "rank_window_size": max(top_k, self._config.rrf_rank_window_size),
                }
            },
            "size": top_k,
        }
        return body

    def _build_index_settings(self) -> Dict[str, Any]:
        return {
            "analysis": {
                "analyzer": {
                    "eduagent_default": {
                        "type": "standard",
                    }
                }
            }
        }

    def _build_index_mappings(self) -> Dict[str, Any]:
        dims = self._config.vector_dims
        return {
            "dynamic": True,
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "course_id": {"type": "keyword"},
                "node_ids": {"type": "keyword"},
                "content_kind": {"type": "keyword"},
                "locale": {"type": "keyword"},
                "content_version": {"type": "keyword"},
                "source_path": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "content": {"type": "text", "analyzer": "eduagent_default"},
                "content_length": {"type": "integer"},
                "chapter": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "section": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "knowledge_point": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "title_path": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "heading_hierarchy": {"type": "keyword"},
                "language_tags": {"type": "keyword"},
                "has_code_block": {"type": "boolean"},
                "has_latex": {"type": "boolean"},
                "code_block_count": {"type": "integer"},
                "latex_formula_count": {"type": "integer"},
                "metadata": {"type": "object", "enabled": True},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                    "index_options": {
                        "type": "hnsw",
                        "m": 16,
                        "ef_construction": 100,
                    },
                },
            },
        }

    def _attach_embeddings(self, chunks: List[KnowledgeBaseChunk]) -> List[KnowledgeBaseChunk]:
        missing = [idx for idx, chunk in enumerate(chunks) if chunk.embedding is None]
        if not missing:
            return chunks

        if self._batch_embed_fn is not None:
            texts = [chunks[idx].content for idx in missing]
            embeddings = self._batch_embed_fn(texts)
            for idx, embedding in zip(missing, embeddings):
                chunks[idx].embedding = embedding
            return chunks

        if self._embed_fn is not None:
            for idx in missing:
                chunks[idx].embedding = self._embed_fn(chunks[idx].content)
            return chunks

        raise RuntimeError("Embedding function not configured. Call set_embedding_function().")

    def _embed_query(self, query: str) -> List[float]:
        if self._embed_fn is None:
            raise RuntimeError("Embedding function not configured. Call set_embedding_function().")
        return self._embed_fn(query)

    def _build_filter_clauses(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        clauses: List[Dict[str, Any]] = []
        for field, value in filters.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                clauses.append({"terms": {field: list(value)}})
            else:
                clauses.append({"term": {field: value}})
        return clauses

    def _fuse_hits_with_rrf(
        self,
        bm25_hits: List[Dict[str, Any]],
        knn_hits: List[Dict[str, Any]],
        *,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        scores: Dict[str, float] = {}
        hits_by_id: Dict[str, Dict[str, Any]] = {}
        rank_constant = self._config.rrf_rank_constant

        for hit_list in (bm25_hits, knn_hits):
            for rank, hit in enumerate(hit_list, start=1):
                doc_id = hit["_id"]
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rank_constant + rank)
                hits_by_id.setdefault(doc_id, dict(hit))

        ranked_ids = sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)[:top_k]
        fused_hits: List[Dict[str, Any]] = []
        for doc_id in ranked_ids:
            hit = dict(hits_by_id[doc_id])
            hit["_score"] = scores[doc_id]
            fused_hits.append(hit)
        return fused_hits

    def _is_rrf_license_error(self, exc: Exception) -> bool:
        if AuthorizationException is not None and isinstance(exc, AuthorizationException):
            return "Reciprocal Rank Fusion" in str(exc) or "RRF" in str(exc)
        return False

    def _ensure_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Elasticsearch client is not connected. Call connect() first.")
        return self._client


class ElasticsearchKnowledgeBasePipeline:
    """End-to-end Markdown ingestion pipeline for Elasticsearch."""

    def __init__(
        self,
        es_client: ElasticsearchKnowledgeBaseClient,
        chunker: Optional[MarkdownKnowledgeBaseChunker] = None,
    ) -> None:
        self._es_client = es_client
        self._chunker = chunker or MarkdownKnowledgeBaseChunker(es_client._config)

    @property
    def chunker(self) -> MarkdownKnowledgeBaseChunker:
        return self._chunker

    def ingest_markdown_file(
        self,
        file_path: str,
        *,
        document_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        recreate_index: bool = False,
    ) -> List[KnowledgeBaseChunk]:
        with open(file_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        final_document_id = document_id or self._derive_document_id(file_path)
        chunks = self._chunker.chunk_markdown(
            markdown_text,
            document_id=final_document_id,
            source_path=os.path.abspath(file_path),
            extra_metadata=extra_metadata,
        )

        self._es_client.create_index(recreate=recreate_index)
        self._es_client.bulk_index_chunks(chunks)
        return chunks

    def _derive_document_id(self, file_path: str) -> str:
        base = os.path.splitext(os.path.basename(file_path))[0]
        normalized = re.sub(r"\W+", "_", base, flags=re.UNICODE).strip("_")
        return normalized or "document"
