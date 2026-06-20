# -*- coding: utf-8 -*-
"""
Neo4jClient — 知识图谱 CRUD 与拓扑数据查询引擎
================================================

基于官方 neo4j-driver (v5.x) 的工业级封装。

功能矩阵：
  1. 连接池管理与自动重连
  2. 知识节点 / 依赖关系 CRUD（支持批量）
  3. 拓扑排序查询（Cypher 端内执行 vs Python 端 PathPlanner）
  4. 子图提取 (subgraph extraction) — 以某个节点为根的 K 跳邻域
  5. 与 PathPlanner 的数据桥接 (export_nodes / export_edges)
  6. 事务管理 (读事务 / 写事务分离)

依赖声明：
  本模块使用 Neo4j 官方 Python Driver，遵循 Apache 2.0 开源协议。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Any, Iterator, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager

from pydantic import BaseModel, Field, field_validator

from ..infrastructure.path_planner import KnowledgeNode, KnowledgeEdge


# ============================================================================
# 配置模型
# ============================================================================

class Neo4jConfig(BaseModel):
    """Neo4j 连接配置。"""

    uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt 协议 URI")
    username: str = Field(default="neo4j", description="数据库用户名")
    password: str = Field(default="neo4j", min_length=1, description="数据库密码")
    database: str = Field(default="neo4j", description="目标数据库名称")
    max_connection_pool_size: int = Field(default=50, ge=1, le=400, description="最大连接池大小")
    connection_acquisition_timeout: float = Field(default=60.0, gt=0.0, description="获取连接超时 (秒)")
    connection_timeout: float = Field(default=30.0, gt=0.0, description="连接建立超时 (秒)")
    max_transaction_retry_time: float = Field(default=30.0, gt=0.0, description="事务重试最长时间 (秒)")


# ============================================================================
# 查询结果模型
# ============================================================================

class QueryResult(BaseModel):
    """Cypher 查询的标准化结果封装。"""

    records: List[Dict[str, Any]] = Field(default_factory=list, description="查询返回的记录列表")
    summary_counters: Dict[str, int] = Field(default_factory=dict, description="事务计数器 (nodes_created, etc.)")
    query: str = Field(default="", description="执行的 Cypher 语句")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="查询参数")


# ============================================================================
# Neo4j 客户端
# ============================================================================

class Neo4jClient:
    """Neo4j 图数据库客户端。

    封装官方 neo4j-driver 的全部常用操作，遵循最佳实践：
      - 读操作使用 execute_read (自动路由到 READ_REPLICA)
      - 写操作使用 execute_write (自动路由到 LEADER)
      - 连接池由 driver 内部管理
      - 异常统一转换为 Neo4jError 子类并向上传播

    使用示例:
        >>> config = Neo4jConfig(uri="bolt://localhost:7687")
        >>> client = Neo4jClient(config)
        >>> client.connect()
        >>> nodes = client.get_all_knowledge_nodes("CS101")
        >>> client.close()
    """

    # ------------------------------------------------------------------
    # 构造与生命周期
    # ------------------------------------------------------------------

    def __init__(self, config: Optional[Neo4jConfig] = None) -> None:
        """初始化 Neo4j 客户端。

        Args:
            config: 连接配置，若 None 则使用默认本地配置。
        """
        self._config = config or Neo4jConfig()
        self._driver: Any = None  # neo4j.Driver — 延迟导入以支持无 Neo4j 环境的测试

    @property
    def config(self) -> Neo4jConfig:
        return self._config

    def connect(self) -> None:
        """建立与 Neo4j 的连接（创建 Driver 实例）。

        幂等操作：如果已连接，先关闭旧连接再重新创建。
        """
        self.close()
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise ImportError(
                "neo4j-driver 未安装。请执行: pip install neo4j"
            )
        self._driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.username, self._config.password),
            max_connection_pool_size=self._config.max_connection_pool_size,
            connection_acquisition_timeout=self._config.connection_acquisition_timeout,
            connection_timeout=self._config.connection_timeout,
        )
        # 验证连接
        self._driver.verify_connectivity()

    def close(self) -> None:
        """关闭 Neo4j 连接，释放连接池资源。"""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def is_connected(self) -> bool:
        """检查驱动程序是否已实例化。"""
        return self._driver is not None

    def __enter__(self) -> "Neo4jClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 事务基础设施
    # ------------------------------------------------------------------

    def _ensure_driver(self) -> Any:
        """确保 Driver 已初始化，否则抛出异常。"""
        if self._driver is None:
            raise RuntimeError("Neo4jClient 未连接。请先调用 connect()。")
        return self._driver

    def execute_read(
        self, cypher: str, parameters: Optional[Dict[str, Any]] = None
    ) -> QueryResult:
        """执行只读 Cypher 查询。

        Args:
            cypher: Cypher 查询语句。
            parameters: 查询参数字典。

        Returns:
            QueryResult: 包含 records 与 summary 的标准结果。
        """
        driver = self._ensure_driver()
        params = parameters or {}

        def _txn(tx: Any) -> List[Dict[str, Any]]:
            result = tx.run(cypher, **params)
            return [record.data() for record in result]

        with driver.session(database=self._config.database) as session:
            records = session.execute_read(_txn)

        return QueryResult(
            records=records,
            query=cypher,
            parameters=params,
        )

    def execute_write(
        self, cypher: str, parameters: Optional[Dict[str, Any]] = None
    ) -> QueryResult:
        """执行写入 Cypher 查询。

        Args:
            cypher: Cypher 写入语句。
            parameters: 查询参数字典。

        Returns:
            QueryResult: 包含 records 与 summary 的标准结果。
        """
        driver = self._ensure_driver()
        params = parameters or {}

        def _txn(tx: Any) -> List[Dict[str, Any]]:
            result = tx.run(cypher, **params)
            records_list = [record.data() for record in result]
            summary = result.consume()
            return records_list

        with driver.session(database=self._config.database) as session:
            records = session.execute_write(_txn)

        return QueryResult(
            records=records,
            query=cypher,
            parameters=params,
        )

    # ==================================================================
    # 知识节点 CRUD
    # ==================================================================

    # ------------------------------------------------------------------
    # 创建节点
    # ------------------------------------------------------------------

    def create_knowledge_node(self, node: KnowledgeNode) -> str:
        """创建单个知识点节点。

        Args:
            node: 知识节点数据。

        Returns:
            创建的节点 ID (Neo4j 内部 ID 字符串形式)。
        """
        cypher = """
        CREATE (n:KnowledgeNode {
            node_id: $node_id,
            course_id: $course_id,
            title: $title,
            difficulty: $difficulty,
            estimated_hours: $estimated_hours,
            category: $category,
            metadata: $metadata
        })
        RETURN n.node_id AS node_id
        """
        result = self.execute_write(cypher, {
            "node_id": node.node_id,
            "course_id": node.course_id or "",
            "title": node.title,
            "difficulty": node.difficulty,
            "estimated_hours": node.estimated_hours,
            "category": node.category,
            "metadata": json.dumps(node.metadata) if isinstance(node.metadata, dict) else str(node.metadata or ""),
        })
        return result.records[0]["node_id"] if result.records else ""

    def create_knowledge_nodes_batch(self, nodes: List[KnowledgeNode]) -> int:
        """批量创建知识点节点。

        使用 UNWIND 批量操作以提高写入性能。

        Args:
            nodes: 知识节点列表。

        Returns:
            实际创建的节点数量。
        """
        if not nodes:
            return 0
        node_data = [
            {
                "node_id": n.node_id,
                "title": n.title,
                "difficulty": n.difficulty,
                "estimated_hours": n.estimated_hours,
                "category": n.category,
                "metadata": n.metadata,
            }
            for n in nodes
        ]
        cypher = """
        UNWIND $nodes AS node
        MERGE (n:KnowledgeNode {node_id: node.node_id})
        SET n.title = node.title,
            n.difficulty = node.difficulty,
            n.estimated_hours = node.estimated_hours,
            n.category = node.category,
            n.metadata = node.metadata
        RETURN count(n) AS created_count
        """
        result = self.execute_write(cypher, {"nodes": node_data})
        return result.records[0]["created_count"] if result.records else 0

    # ------------------------------------------------------------------
    # 创建依赖关系
    # ------------------------------------------------------------------

    def create_dependency_edge(self, edge: KnowledgeEdge) -> bool:
        """创建单条前置依赖关系。

        Args:
            edge: 依赖边数据。

        Returns:
            True 如果创建成功。
        """
        cypher = """
        MATCH (src:KnowledgeNode {node_id: $source_id})
        MATCH (tgt:KnowledgeNode {node_id: $target_id})
        MERGE (src)-[r:PREREQUISITE]->(tgt)
        SET r.dependency_type = $dep_type,
            r.weight = $weight
        RETURN src.node_id AS source, tgt.node_id AS target
        """
        result = self.execute_write(cypher, {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "dep_type": edge.dependency_type,
            "weight": edge.weight,
        })
        return len(result.records) > 0

    def create_dependency_edges_batch(self, edges: List[KnowledgeEdge]) -> int:
        """批量创建前置依赖关系。

        Args:
            edges: 依赖边列表。

        Returns:
            实际创建的边数量。
        """
        if not edges:
            return 0
        edge_data = [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "dep_type": e.dependency_type,
                "weight": e.weight,
            }
            for e in edges
        ]
        cypher = """
        UNWIND $edges AS edge
        MATCH (src:KnowledgeNode {node_id: edge.source_id})
        MATCH (tgt:KnowledgeNode {node_id: edge.target_id})
        MERGE (src)-[r:PREREQUISITE]->(tgt)
        SET r.dependency_type = edge.dep_type,
            r.weight = edge.weight
        RETURN count(r) AS created_count
        """
        result = self.execute_write(cypher, {"edges": edge_data})
        return result.records[0]["created_count"] if result.records else 0

    # ------------------------------------------------------------------
    # 查询节点
    # ------------------------------------------------------------------

    def get_all_knowledge_nodes(self, course_id: Optional[str] = None) -> List[KnowledgeNode]:
        """获取指定课程的全部知识点节点。

        Args:
            course_id: 课程 ID 过滤，None 表示不限课程。

        Returns:
            KnowledgeNode 列表。
        """
        if course_id:
            cypher = """
            MATCH (n:KnowledgeNode)
            WHERE n.course_id = $course_id
            RETURN n
            """
            params = {"course_id": course_id}
        else:
            cypher = "MATCH (n:KnowledgeNode) RETURN n"
            params = {}

        result = self.execute_read(cypher, params)
        nodes: List[KnowledgeNode] = []
        for record in result.records:
            n = record["n"]
            raw_meta = n.get("metadata", {})
            if isinstance(raw_meta, str):
                try:
                    raw_meta = json.loads(raw_meta)
                except Exception:
                    raw_meta = {}
            nodes.append(KnowledgeNode(
                node_id=n.get("node_id", ""),
                course_id=n.get("course_id", ""),
                title=n.get("title", ""),
                difficulty=n.get("difficulty", 0.5),
                estimated_hours=n.get("estimated_hours", 1.0),
                category=n.get("category", "concept"),
                metadata=raw_meta if isinstance(raw_meta, dict) else {},
            ))
        return nodes

    def get_knowledge_node_by_id(self, node_id: str) -> Optional[KnowledgeNode]:
        """按 ID 查询单个知识点节点。

        Args:
            node_id: 知识点 ID。

        Returns:
            KnowledgeNode if found, else None。
        """
        cypher = "MATCH (n:KnowledgeNode {node_id: $node_id}) RETURN n"
        result = self.execute_read(cypher, {"node_id": node_id})
        if not result.records:
            return None
        n = result.records[0]["n"]
        return KnowledgeNode(
            node_id=n.get("node_id", ""),
            title=n.get("title", ""),
            difficulty=n.get("difficulty", 0.5),
            estimated_hours=n.get("estimated_hours", 1.0),
            category=n.get("category", "concept"),
            metadata=n.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # 查询依赖关系
    # ------------------------------------------------------------------

    def get_all_edges(self, course_id: Optional[str] = None) -> List[KnowledgeEdge]:
        """获取所有前置依赖关系（可按课程筛选）。"""
        if course_id:
            cypher = """
            MATCH (src:KnowledgeNode {course_id: $course_id})-[r:PREREQUISITE]->(tgt:KnowledgeNode {course_id: $course_id})
            RETURN src.node_id AS source_id, tgt.node_id AS target_id,
                   r.dependency_type AS dep_type, r.weight AS weight
            """
            result = self.execute_read(cypher, {"course_id": course_id})
        else:
            cypher = """
            MATCH (src:KnowledgeNode)-[r:PREREQUISITE]->(tgt:KnowledgeNode)
            RETURN src.node_id AS source_id, tgt.node_id AS target_id,
                   r.dependency_type AS dep_type, r.weight AS weight
            """
            result = self.execute_read(cypher)
        edges: List[KnowledgeEdge] = []
        for record in result.records:
            edges.append(KnowledgeEdge(
                source_id=record["source_id"],
                target_id=record["target_id"],
                course_id=course_id or "",
                dependency_type=record.get("dep_type", "strict"),
                weight=record.get("weight", 1.0),
            ))
        return edges

    def get_prerequisites(self, node_id: str) -> List[KnowledgeEdge]:
        """查询某个节点的直接前置依赖。

        Args:
            node_id: 目标知识点 ID。

        Returns:
            以该节点为终点的边列表。
        """
        cypher = """
        MATCH (src:KnowledgeNode)-[r:PREREQUISITE]->(tgt:KnowledgeNode {node_id: $node_id})
        RETURN src.node_id AS source_id, tgt.node_id AS target_id,
               r.dependency_type AS dep_type, r.weight AS weight
        """
        result = self.execute_read(cypher, {"node_id": node_id})
        edges: List[KnowledgeEdge] = []
        for record in result.records:
            edges.append(KnowledgeEdge(
                source_id=record["source_id"],
                target_id=record["target_id"],
                dependency_type=record.get("dep_type", "strict"),
                weight=record.get("weight", 1.0),
            ))
        return edges

    def get_dependents(self, node_id: str) -> List[KnowledgeEdge]:
        """查询某个节点的直接后继。

        Args:
            node_id: 源知识点 ID。

        Returns:
            以该节点为起点的边列表。
        """
        cypher = """
        MATCH (src:KnowledgeNode {node_id: $node_id})-[r:PREREQUISITE]->(tgt:KnowledgeNode)
        RETURN src.node_id AS source_id, tgt.node_id AS target_id,
               r.dependency_type AS dep_type, r.weight AS weight
        """
        result = self.execute_read(cypher, {"node_id": node_id})
        edges: List[KnowledgeEdge] = []
        for record in result.records:
            edges.append(KnowledgeEdge(
                source_id=record["source_id"],
                target_id=record["target_id"],
                dependency_type=record.get("dep_type", "strict"),
                weight=record.get("weight", 1.0),
            ))
        return edges

    # ------------------------------------------------------------------
    # 子图提取（K 跳邻域）
    # ------------------------------------------------------------------

    def extract_subgraph_k_hop(
        self, root_node_id: str, k: int = 3, direction: str = "downstream"
    ) -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
        """提取以指定节点为根的 K 跳子图。

        Args:
            root_node_id: 根节点 ID。
            k: 最大跳数。
            direction: 'upstream' (前置依赖方向) | 'downstream' (后继方向) | 'both'。

        Returns:
            (nodes, edges) 元组。
        """
        if direction == "upstream":
            rel_pattern = "<-[r:PREREQUISITE*1..{k}]-"
        elif direction == "downstream":
            rel_pattern = "-[r:PREREQUISITE*1..{k}]->"
        else:
            rel_pattern = "-[r:PREREQUISITE*1..{k}]-"

        cypher = f"""
        MATCH path = (root:KnowledgeNode {{node_id: $root_id}}){rel_pattern}(neighbor:KnowledgeNode)
        WITH nodes(path) AS path_nodes, relationships(path) AS path_rels
        UNWIND path_nodes AS n
        WITH DISTINCT n, path_rels
        UNWIND path_rels AS r
        RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT r) AS rels
        """

        result = self.execute_read(cypher, {"root_id": root_node_id, "k": k})
        if not result.records:
            return [], []

        record = result.records[0]
        raw_nodes = record.get("nodes", [])
        raw_rels = record.get("rels", [])

        nodes = [
            KnowledgeNode(
                node_id=n.get("node_id", ""),
                title=n.get("title", ""),
                difficulty=n.get("difficulty", 0.5),
                estimated_hours=n.get("estimated_hours", 1.0),
                category=n.get("category", "concept"),
                metadata=n.get("metadata", {}),
            )
            for n in raw_nodes
        ]

        edges = [
            KnowledgeEdge(
                source_id=r.start_node.get("node_id", ""),
                target_id=r.end_node.get("node_id", ""),
                dependency_type=r.get("dependency_type", "strict"),
                weight=r.get("weight", 1.0),
            )
            for r in raw_rels
        ]

        return nodes, edges

    # ------------------------------------------------------------------
    # 与 PathPlanner 的数据桥接
    # ------------------------------------------------------------------

    def export_nodes_for_planner(
        self, course_id: Optional[str] = None
    ) -> List[KnowledgeNode]:
        """导出节点列表供 PathPlanner 初始化。

        Args:
            course_id: 课程 ID 过滤。

        Returns:
            KnowledgeNode 列表。
        """
        return self.get_all_knowledge_nodes(course_id)

    def export_edges_for_planner(
        self, course_id: Optional[str] = None
    ) -> List[KnowledgeEdge]:
        """导出边列表供 PathPlanner 初始化。

        Args:
            course_id: 课程 ID 过滤。

        Returns:
            KnowledgeEdge 列表。
        """
        return self.get_all_edges(course_id)

    # ------------------------------------------------------------------
    # 图统计
    # ------------------------------------------------------------------

    def get_graph_statistics(self) -> Dict[str, Any]:
        """获取知识图谱的宏观统计信息。"""
        cypher = """
        MATCH (n:KnowledgeNode)
        OPTIONAL MATCH (n)-[r:PREREQUISITE]->()
        RETURN
            count(DISTINCT n) AS total_nodes,
            count(DISTINCT r) AS total_edges,
            avg(n.difficulty) AS avg_difficulty,
            avg(n.estimated_hours) AS avg_hours,
            max(n.difficulty) AS max_difficulty,
            min(n.difficulty) AS min_difficulty
        """
        result = self.execute_read(cypher)
        if not result.records:
            return {}
        rec = result.records[0]
        return {
            "total_nodes": rec.get("total_nodes", 0),
            "total_edges": rec.get("total_edges", 0),
            "avg_difficulty": round(rec.get("avg_difficulty", 0.0) or 0.0, 4),
            "avg_hours": round(rec.get("avg_hours", 0.0) or 0.0, 2),
            "max_difficulty": rec.get("max_difficulty", 0.0),
            "min_difficulty": rec.get("min_difficulty", 0.0),
        }

    # ------------------------------------------------------------------
    # 用户掌握度管理
    # ------------------------------------------------------------------

    def set_user_mastery(
        self, user_id: str, node_id: str, mastery: float
    ) -> bool:
        """记录用户对某知识点的掌握度。

        使用 MERGE 保证幂等性，同时记录更新时间戳。

        Args:
            user_id: 用户 ID。
            node_id: 知识点 ID。
            mastery: 掌握度 (0.0-1.0)。

        Returns:
            True。
        """
        cypher = """
        MATCH (n:KnowledgeNode {node_id: $node_id})
        MERGE (u:User {user_id: $user_id})
        MERGE (u)-[r:MASTERED]->(n)
        SET r.mastery = $mastery,
            r.updated_at = datetime()
        RETURN r.mastery AS mastery
        """
        self.execute_write(cypher, {
            "user_id": user_id,
            "node_id": node_id,
            "mastery": mastery,
        })
        return True

    def get_user_mastery_map(self, user_id: str) -> Dict[str, float]:
        """获取用户对所有已交互知识点的掌握度映射。

        Args:
            user_id: 用户 ID。

        Returns:
            Dict[node_id → mastery]。
        """
        cypher = """
        MATCH (u:User {user_id: $user_id})-[r:MASTERED]->(n:KnowledgeNode)
        RETURN n.node_id AS node_id, r.mastery AS mastery
        """
        result = self.execute_read(cypher, {"user_id": user_id})
        mastery_map: Dict[str, float] = {}
        for record in result.records:
            mastery_map[record["node_id"]] = record.get("mastery", 0.0)
        return mastery_map

    # ------------------------------------------------------------------
    # 模式初始化（Schema Bootstrap）
    # ------------------------------------------------------------------

    def initialize_schema(self) -> None:
        """创建 Neo4j 约束与索引。

        包括：
          - KnowledgeNode.node_id 唯一性约束
          - User.user_id 唯一性约束
          - 难度 / 预估时长范围属性索引
        """
        # 删除旧单列唯一约束（如果存在）以避免冲突
        try:
            self.execute_write("DROP CONSTRAINT IF EXISTS FOR (n:KnowledgeNode) REQUIRE n.node_id IS UNIQUE")
        except Exception:
            pass

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:KnowledgeNode) REQUIRE (n.node_id, n.course_id) IS NODE KEY",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
        ]
        for cypher in constraints:
            try:
                self.execute_write(cypher)
            except Exception:
                pass

        indices = [
            "CREATE INDEX IF NOT EXISTS FOR (n:KnowledgeNode) ON (n.course_id)",
            "CREATE INDEX IF NOT EXISTS FOR (n:KnowledgeNode) ON (n.difficulty)",
            "CREATE INDEX IF NOT EXISTS FOR (n:KnowledgeNode) ON (n.category)",
        ]
        for cypher in indices:
            try:
                self.execute_write(cypher)
            except Exception:
                pass  # 索引可能已存在，静默忽略
