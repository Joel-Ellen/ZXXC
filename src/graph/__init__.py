# -*- coding: utf-8 -*-
"""
EduAgent Graph Layer
====================
Neo4j 图谱基座层 — 提供知识图谱的 CRUD、拓扑查询与 Path Planner 数据源。

本包导出 Neo4jClient，封装官方 neo4j-driver 的全部操作，
同时提供与 PathPlanner 的数据桥接接口。
"""

from .neo4j_client import Neo4jClient, Neo4jConfig, QueryResult

__all__ = [
    "Neo4jClient",
    "Neo4jConfig",
    "QueryResult",
]
