# -*- coding: utf-8 -*-
"""
KnowledgeGraphManager — 知识图谱统一管理层
============================================
封装 Neo4j 查询 + 内存回退，提供初始化种子数据的能力。
前端 Server / Planner 通过此单例获取图谱数据，不再依赖硬编码 Mock。

用法:
    >>> mgr = KnowledgeGraphManager()                # 尝试 Neo4j，失败回退内存
    >>> nodes = mgr.get_all_nodes()
    >>> edges = mgr.get_all_edges()
    >>> path_planner = mgr.create_path_planner()
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from ..infrastructure.path_planner import KnowledgeNode, KnowledgeEdge


# ============================================================================
# 初始种子数据 (原 MOCK_KNOWLEDGE_NODES / MOCK_KNOWLEDGE_EDGES)
# ============================================================================

SEED_NODES = [
    KnowledgeNode(node_id="N01", title="算法复杂度分析", difficulty=0.25, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N02", title="线性表与顺序存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N03", title="链表与链式存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N04", title="栈及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N05", title="队列及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N06", title="树与二叉树基础", difficulty=0.45, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N07", title="二叉搜索树", difficulty=0.50, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N08", title="AVL 平衡树", difficulty=0.60, estimated_hours=3.5, category="concept"),
    KnowledgeNode(node_id="N09", title="散列表与哈希", difficulty=0.55, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N10", title="图的基本概念与存储", difficulty=0.50, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N11", title="图的遍历 DFS/BFS", difficulty=0.55, estimated_hours=3.0, category="skill"),
    KnowledgeNode(node_id="N12", title="最小生成树", difficulty=0.65, estimated_hours=3.5, category="skill"),
    KnowledgeNode(node_id="N13", title="最短路径算法", difficulty=0.70, estimated_hours=4.0, category="skill"),
    KnowledgeNode(node_id="N14", title="拓扑排序与关键路径", difficulty=0.70, estimated_hours=3.5, category="skill"),
    KnowledgeNode(node_id="N15", title="排序算法基础", difficulty=0.55, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N16", title="高级排序算法", difficulty=0.65, estimated_hours=4.0, category="skill"),
    KnowledgeNode(node_id="N17", title="查找与索引技术", difficulty=0.60, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N18", title="动态规划入门", difficulty=0.75, estimated_hours=5.0, category="skill"),
    KnowledgeNode(node_id="N19", title="贪心算法与回溯", difficulty=0.70, estimated_hours=4.5, category="skill"),
    KnowledgeNode(node_id="N20", title="数据结构综合应用", difficulty=0.80, estimated_hours=6.0, category="project"),
]

SEED_EDGES = [
    KnowledgeEdge(source_id="N01", target_id="N02", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N03", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N06", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N15", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N02", target_id="N04", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N02", target_id="N05", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N03", target_id="N04", dependency_type="recommended", weight=0.5),
    KnowledgeEdge(source_id="N03", target_id="N05", dependency_type="recommended", weight=0.5),
    KnowledgeEdge(source_id="N06", target_id="N07", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N07", target_id="N08", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N03", target_id="N09", dependency_type="recommended", weight=0.7),
    KnowledgeEdge(source_id="N06", target_id="N09", dependency_type="recommended", weight=0.5),
    KnowledgeEdge(source_id="N06", target_id="N10", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N10", target_id="N11", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N11", target_id="N12", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N11", target_id="N13", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N13", target_id="N14", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N15", target_id="N16", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N16", target_id="N17", dependency_type="recommended", weight=0.8),
    KnowledgeEdge(source_id="N13", target_id="N18", dependency_type="strict", weight=1.5),
    KnowledgeEdge(source_id="N14", target_id="N18", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N16", target_id="N19", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N18", target_id="N19", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N08", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N09", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N12", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N19", target_id="N20", dependency_type="strict", weight=1.5),
]

# 知识基础 → 节点初始掌握度映射
SEED_KNOWLEDGE_MASTERY: Dict[str, Dict[str, float]] = {
    "python_basics": {"N02": 0.75, "N03": 0.70, "N04": 0.65, "N05": 0.65},
    "data_structures": {"N01": 0.70, "N02": 0.80, "N03": 0.75, "N06": 0.60},
    "linear_algebra": {"N18": 0.50},
    "ml_basics": {"N18": 0.45},
    "deep_learning": {"N18": 0.40, "N19": 0.35},
    "databases": {"N09": 0.55, "N17": 0.50},
    "dev_tools": {},
    "none": {},
}


# ============================================================================
# KnowledgeGraphManager
# ============================================================================

class KnowledgeGraphManager:
    """知识图谱统一管理层。

    策略:
      1. 尝试连接 Neo4j — 成功则查询数据库
      2. Neo4j 不可用 → 自动回退内存模式 (种子数据)
      3. 首次内存模式时，自动写入种子数据
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
    ) -> None:
        self._neo4j_client: Any = None
        self._neo4j_available: bool = False
        self._in_memory_nodes: Dict[str, KnowledgeNode] = {}
        self._in_memory_edges: List[KnowledgeEdge] = []

        # 尝试连接 Neo4j
        if self._try_connect_neo4j(neo4j_uri, neo4j_user, neo4j_password):
            self._neo4j_available = True
        else:
            self._init_in_memory()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @property
    def is_neo4j_available(self) -> bool:
        return self._neo4j_available

    def get_all_nodes(self) -> List[KnowledgeNode]:
        """获取全部知识点节点。"""
        if self._neo4j_available:
            return self._export_nodes_from_neo4j()
        return list(self._in_memory_nodes.values())

    def get_all_edges(self) -> List[KnowledgeEdge]:
        """获取全部依赖边。"""
        if self._neo4j_available:
            return self._export_edges_from_neo4j()
        return list(self._in_memory_edges)

    def get_node_by_id(self, node_id: str) -> Optional[KnowledgeNode]:
        """按 ID 获取单个节点。"""
        if self._neo4j_available:
            nodes = self._export_nodes_from_neo4j()
            for n in nodes:
                if n.node_id == node_id:
                    return n
            return None
        return self._in_memory_nodes.get(node_id)

    def get_node_title(self, node_id: str) -> str:
        """获取节点标题（用于 UI 展示）。"""
        node = self.get_node_by_id(node_id)
        return node.title if node else node_id

    def get_knowledge_mastery_map(
        self, knowledge_items: List[str]
    ) -> Dict[str, float]:
        """根据用户知识基础列表，计算初始掌握度映射。

        Args:
            knowledge_items: 用户在冷启动中选择的知识基础项。

        Returns:
            {node_id: mastery (0.0-1.0)}。
        """
        result: Dict[str, float] = {}
        for item in knowledge_items:
            node_mastery = SEED_KNOWLEDGE_MASTERY.get(item, {})
            for node_id, mastery in node_mastery.items():
                result[node_id] = max(result.get(node_id, 0.0), mastery)
        return result

    def get_node_id_to_title_map(self) -> Dict[str, str]:
        nodes = self.get_all_nodes()
        return {n.node_id: n.title for n in nodes}

    def create_path_planner(self):
        """创建配置好的 PathPlanner 实例。"""
        from ..infrastructure.path_planner import PathPlanner
        nodes = self.get_all_nodes()
        edges = self.get_all_edges()
        return PathPlanner(nodes, edges)

    # ------------------------------------------------------------------
    # Neo4j 连接
    # ------------------------------------------------------------------

    def _try_connect_neo4j(
        self,
        uri: Optional[str],
        user: Optional[str],
        password: Optional[str],
    ) -> bool:
        """尝试建立 Neo4j 连接并导入种子数据。"""
        try:
            from .neo4j_client import Neo4jClient, Neo4jConfig

            config = Neo4jConfig(
                uri=uri or os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                username=user or os.getenv("NEO4J_USER", "neo4j"),
                password=password or os.getenv("NEO4J_PASSWORD", "neo4j"),
            )
            self._neo4j_client = Neo4jClient(config)
            self._neo4j_client.connect()

            # 检查是否为空数据库 → 自动播种
            existing = self._export_nodes_from_neo4j()
            if not existing:
                self._seed_neo4j()

            return True
        except Exception:
            return False

    def _seed_neo4j(self) -> None:
        """将种子节点和边写入 Neo4j。"""
        try:
            for node in SEED_NODES:
                self._neo4j_client.create_knowledge_node(node)
            for edge in SEED_EDGES:
                self._neo4j_client.create_prerequisite(
                    edge.source_id, edge.target_id,
                    dependency_type=edge.dependency_type, weight=edge.weight,
                )
        except Exception:
            pass

    def _export_nodes_from_neo4j(self) -> List[KnowledgeNode]:
        try:
            return self._neo4j_client.export_nodes_for_planner()
        except Exception:
            return []

    def _export_edges_from_neo4j(self) -> List[KnowledgeEdge]:
        try:
            return self._neo4j_client.export_edges_for_planner()
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 内存回退
    # ------------------------------------------------------------------

    def _init_in_memory(self) -> None:
        """初始化内存中的种子数据。"""
        self._in_memory_nodes = {n.node_id: n for n in SEED_NODES}
        self._in_memory_edges = list(SEED_EDGES)


# ============================================================================
# 全局单例
# ============================================================================

_kg_manager: Optional[KnowledgeGraphManager] = None


def get_kg_manager() -> KnowledgeGraphManager:
    """获取全局单例 KnowledgeGraphManager。"""
    global _kg_manager
    if _kg_manager is None:
        _kg_manager = KnowledgeGraphManager()
        backend = "Neo4j" if _kg_manager.is_neo4j_available else "Memory"
        print(f"[KG] KnowledgeGraphManager initialized ({backend} backend)")
    return _kg_manager
