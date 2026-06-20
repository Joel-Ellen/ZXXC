# -*- coding: utf-8 -*-
"""
EduAgent Vector Layer
=====================
Milvus 向量检索层 — 提供 Parent-Child 双层映射的高性能向量召回。

本包导出 MilvusClient，封装官方 pymilvus SDK 的全部操作，
实现子块高召回 + 父块完整上下文注入的检索策略。
"""

from .milvus_client import (
    MilvusClient,
    MilvusConfig,
    SearchResult,
    ParentChunk,
    ChildChunk,
    ChunkSearchResult,
)
from .elasticsearch_knowledge_base import (
    ElasticsearchKnowledgeBaseClient,
    ElasticsearchKnowledgeBaseConfig,
    ElasticsearchKnowledgeBasePipeline,
    HashingTextEmbedder,
    KnowledgeBaseChunk,
    MarkdownKnowledgeBaseChunker,
    SentenceTransformerEmbedder,
)

__all__ = [
    "MilvusClient",
    "MilvusConfig",
    "SearchResult",
    "ParentChunk",
    "ChildChunk",
    "ChunkSearchResult",
    "ElasticsearchKnowledgeBaseClient",
    "ElasticsearchKnowledgeBaseConfig",
    "ElasticsearchKnowledgeBasePipeline",
    "HashingTextEmbedder",
    "KnowledgeBaseChunk",
    "MarkdownKnowledgeBaseChunker",
    "SentenceTransformerEmbedder",
]
