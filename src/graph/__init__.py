# -*- coding: utf-8 -*-
"""
EduAgent Graph Layer
====================
Neo4j 图谱基座层 — 提供知识图谱的 CRUD、拓扑查询与 Path Planner 数据源。

本包导出:
  - Neo4jClient: 官方 neo4j-driver 工业级封装
  - KnowledgeGraphManager: 知识图谱统一管理层 (Neo4j + 内存回退 + 种子数据)
"""

# Lazy imports to avoid circular imports with infrastructure.graph_builder
def __getattr__(name):
    if name in ("Neo4jClient", "Neo4jConfig", "QueryResult"):
        from .neo4j_client import Neo4jClient, Neo4jConfig, QueryResult
        return locals()[name]
    if name in ("KnowledgeGraphManager", "get_kg_manager",
                "SEED_NODES", "SEED_EDGES", "SEED_KNOWLEDGE_MASTERY"):
        from .knowledge_graph_manager import (
            KnowledgeGraphManager, get_kg_manager,
            SEED_NODES, SEED_EDGES, SEED_KNOWLEDGE_MASTERY,
        )
        return locals()[name]
    raise AttributeError(f"module 'src.graph' has no attribute {name!r}")

__all__ = [
    "Neo4jClient", "Neo4jConfig", "QueryResult",
    "KnowledgeGraphManager", "get_kg_manager",
    "SEED_NODES", "SEED_EDGES", "SEED_KNOWLEDGE_MASTERY",
]
