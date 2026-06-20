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

# 每门课程的种子节点数据
SEED_NODES: Dict[str, List[KnowledgeNode]] = {
    "data_structures": [
        KnowledgeNode(node_id="N01", course_id="data_structures", title="算法复杂度分析", difficulty=0.25, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="N02", course_id="data_structures", title="线性表与顺序存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
        KnowledgeNode(node_id="N03", course_id="data_structures", title="链表与链式存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
        KnowledgeNode(node_id="N04", course_id="data_structures", title="栈及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="N05", course_id="data_structures", title="队列及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="N06", course_id="data_structures", title="树与二叉树基础", difficulty=0.45, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="N07", course_id="data_structures", title="二叉搜索树", difficulty=0.50, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="N08", course_id="data_structures", title="AVL 平衡树", difficulty=0.60, estimated_hours=3.5, category="concept"),
        KnowledgeNode(node_id="N09", course_id="data_structures", title="散列表与哈希", difficulty=0.55, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="N10", course_id="data_structures", title="图的基本概念与存储", difficulty=0.50, estimated_hours=2.5, category="concept"),
        KnowledgeNode(node_id="N11", course_id="data_structures", title="图的遍历 DFS/BFS", difficulty=0.55, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="N12", course_id="data_structures", title="最小生成树", difficulty=0.65, estimated_hours=3.5, category="skill"),
        KnowledgeNode(node_id="N13", course_id="data_structures", title="最短路径算法", difficulty=0.70, estimated_hours=4.0, category="skill"),
        KnowledgeNode(node_id="N14", course_id="data_structures", title="拓扑排序与关键路径", difficulty=0.70, estimated_hours=3.5, category="skill"),
        KnowledgeNode(node_id="N15", course_id="data_structures", title="排序算法基础", difficulty=0.55, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="N16", course_id="data_structures", title="高级排序算法", difficulty=0.65, estimated_hours=4.0, category="skill"),
        KnowledgeNode(node_id="N17", course_id="data_structures", title="查找与索引技术", difficulty=0.60, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="N18", course_id="data_structures", title="动态规划入门", difficulty=0.75, estimated_hours=5.0, category="skill"),
        KnowledgeNode(node_id="N19", course_id="data_structures", title="贪心算法与回溯", difficulty=0.70, estimated_hours=4.5, category="skill"),
        KnowledgeNode(node_id="N20", course_id="data_structures", title="数据结构综合应用", difficulty=0.80, estimated_hours=6.0, category="project"),
    ],
    "operating_systems": [
        KnowledgeNode(node_id="OS01", course_id="operating_systems", title="操作系统概述", difficulty=0.30, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="OS02", course_id="operating_systems", title="进程与线程", difficulty=0.45, estimated_hours=3.5, category="concept"),
        KnowledgeNode(node_id="OS03", course_id="operating_systems", title="CPU 调度算法", difficulty=0.55, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="OS04", course_id="operating_systems", title="同步与死锁", difficulty=0.65, estimated_hours=4.0, category="concept"),
        KnowledgeNode(node_id="OS05", course_id="operating_systems", title="内存管理", difficulty=0.60, estimated_hours=4.0, category="concept"),
        KnowledgeNode(node_id="OS06", course_id="operating_systems", title="文件系统", difficulty=0.50, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="OS07", course_id="operating_systems", title="I/O 与磁盘调度", difficulty=0.55, estimated_hours=2.5, category="skill"),
        KnowledgeNode(node_id="OS08", course_id="operating_systems", title="操作系统综合设计", difficulty=0.75, estimated_hours=5.0, category="project"),
    ],
    "computer_networks": [
        KnowledgeNode(node_id="CN01", course_id="computer_networks", title="网络体系结构", difficulty=0.35, estimated_hours=2.5, category="concept"),
        KnowledgeNode(node_id="CN02", course_id="computer_networks", title="物理层与数据链路层", difficulty=0.40, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="CN03", course_id="computer_networks", title="IP 协议与路由", difficulty=0.55, estimated_hours=3.5, category="concept"),
        KnowledgeNode(node_id="CN04", course_id="computer_networks", title="TCP 与 UDP", difficulty=0.60, estimated_hours=3.5, category="concept"),
        KnowledgeNode(node_id="CN05", course_id="computer_networks", title="应用层协议", difficulty=0.45, estimated_hours=2.5, category="concept"),
        KnowledgeNode(node_id="CN06", course_id="computer_networks", title="网络安全基础", difficulty=0.55, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="CN07", course_id="computer_networks", title="网络编程实践", difficulty=0.65, estimated_hours=4.0, category="project"),
    ],
    "machine_learning": [
        KnowledgeNode(node_id="ML01", course_id="machine_learning", title="机器学习概论", difficulty=0.30, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="ML02", course_id="machine_learning", title="监督学习：回归与分类", difficulty=0.45, estimated_hours=3.5, category="concept"),
        KnowledgeNode(node_id="ML03", course_id="machine_learning", title="无监督学习：聚类与降维", difficulty=0.50, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="ML04", course_id="machine_learning", title="特征工程与模型评估", difficulty=0.55, estimated_hours=3.5, category="skill"),
        KnowledgeNode(node_id="ML05", course_id="machine_learning", title="神经网络基础", difficulty=0.65, estimated_hours=4.0, category="concept"),
        KnowledgeNode(node_id="ML06", course_id="machine_learning", title="深度学习框架实践", difficulty=0.70, estimated_hours=5.0, category="project"),
        KnowledgeNode(node_id="ML07", course_id="machine_learning", title="模型部署与 MLOps", difficulty=0.75, estimated_hours=4.0, category="skill"),
    ],
    "python_programming": [
        KnowledgeNode(node_id="PY01", course_id="python_programming", title="Python 基础语法", difficulty=0.15, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="PY02", course_id="python_programming", title="数据结构与容器", difficulty=0.25, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="PY03", course_id="python_programming", title="函数与模块化", difficulty=0.30, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="PY04", course_id="python_programming", title="面向对象编程", difficulty=0.35, estimated_hours=4.0, category="concept"),
        KnowledgeNode(node_id="PY05", course_id="python_programming", title="文件操作与异常处理", difficulty=0.25, estimated_hours=2.0, category="skill"),
        KnowledgeNode(node_id="PY06", course_id="python_programming", title="标准库与第三方库", difficulty=0.35, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="PY07", course_id="python_programming", title="函数式编程与迭代器", difficulty=0.40, estimated_hours=3.0, category="concept"),
        KnowledgeNode(node_id="PY08", course_id="python_programming", title="综合项目实战", difficulty=0.50, estimated_hours=5.0, category="project"),
    ],
}

# 每门课程的种子边数据
SEED_EDGES: Dict[str, List[KnowledgeEdge]] = {
    "data_structures": [
        KnowledgeEdge(source_id="N01", target_id="N02", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N01", target_id="N03", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N01", target_id="N06", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N01", target_id="N15", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N02", target_id="N04", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N02", target_id="N05", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N03", target_id="N04", course_id="data_structures", dependency_type="recommended", weight=0.5),
        KnowledgeEdge(source_id="N03", target_id="N05", course_id="data_structures", dependency_type="recommended", weight=0.5),
        KnowledgeEdge(source_id="N06", target_id="N07", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N07", target_id="N08", course_id="data_structures", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="N03", target_id="N09", course_id="data_structures", dependency_type="recommended", weight=0.7),
        KnowledgeEdge(source_id="N06", target_id="N09", course_id="data_structures", dependency_type="recommended", weight=0.5),
        KnowledgeEdge(source_id="N06", target_id="N10", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N10", target_id="N11", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N11", target_id="N12", course_id="data_structures", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="N11", target_id="N13", course_id="data_structures", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="N13", target_id="N14", course_id="data_structures", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="N15", target_id="N16", course_id="data_structures", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="N16", target_id="N17", course_id="data_structures", dependency_type="recommended", weight=0.8),
        KnowledgeEdge(source_id="N13", target_id="N18", course_id="data_structures", dependency_type="strict", weight=1.5),
        KnowledgeEdge(source_id="N14", target_id="N18", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N16", target_id="N19", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N18", target_id="N19", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N08", target_id="N20", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N09", target_id="N20", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N12", target_id="N20", course_id="data_structures", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="N19", target_id="N20", course_id="data_structures", dependency_type="strict", weight=1.5),
    ],
    "operating_systems": [
        KnowledgeEdge(source_id="OS01", target_id="OS02", course_id="operating_systems", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="OS02", target_id="OS03", course_id="operating_systems", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="OS02", target_id="OS04", course_id="operating_systems", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="OS01", target_id="OS05", course_id="operating_systems", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="OS05", target_id="OS06", course_id="operating_systems", dependency_type="recommended", weight=0.8),
        KnowledgeEdge(source_id="OS05", target_id="OS07", course_id="operating_systems", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="OS04", target_id="OS08", course_id="operating_systems", dependency_type="strict", weight=1.5),
        KnowledgeEdge(source_id="OS06", target_id="OS08", course_id="operating_systems", dependency_type="strict", weight=1.0),
    ],
    "computer_networks": [
        KnowledgeEdge(source_id="CN01", target_id="CN02", course_id="computer_networks", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="CN01", target_id="CN03", course_id="computer_networks", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="CN03", target_id="CN04", course_id="computer_networks", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="CN04", target_id="CN05", course_id="computer_networks", dependency_type="recommended", weight=0.8),
        KnowledgeEdge(source_id="CN04", target_id="CN06", course_id="computer_networks", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="CN02", target_id="CN06", course_id="computer_networks", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="CN05", target_id="CN07", course_id="computer_networks", dependency_type="strict", weight=1.5),
        KnowledgeEdge(source_id="CN06", target_id="CN07", course_id="computer_networks", dependency_type="strict", weight=1.0),
    ],
    "machine_learning": [
        KnowledgeEdge(source_id="ML01", target_id="ML02", course_id="machine_learning", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="ML01", target_id="ML03", course_id="machine_learning", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="ML02", target_id="ML04", course_id="machine_learning", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="ML03", target_id="ML04", course_id="machine_learning", dependency_type="recommended", weight=0.8),
        KnowledgeEdge(source_id="ML02", target_id="ML05", course_id="machine_learning", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="ML05", target_id="ML06", course_id="machine_learning", dependency_type="strict", weight=1.5),
        KnowledgeEdge(source_id="ML04", target_id="ML06", course_id="machine_learning", dependency_type="recommended", weight=1.0),
        KnowledgeEdge(source_id="ML06", target_id="ML07", course_id="machine_learning", dependency_type="strict", weight=1.2),
    ],
    "python_programming": [
        KnowledgeEdge(source_id="PY01", target_id="PY02", course_id="python_programming", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="PY01", target_id="PY03", course_id="python_programming", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="PY02", target_id="PY04", course_id="python_programming", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="PY03", target_id="PY04", course_id="python_programming", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="PY03", target_id="PY05", course_id="python_programming", dependency_type="recommended", weight=0.5),
        KnowledgeEdge(source_id="PY04", target_id="PY06", course_id="python_programming", dependency_type="strict", weight=1.0),
        KnowledgeEdge(source_id="PY06", target_id="PY07", course_id="python_programming", dependency_type="recommended", weight=0.7),
        KnowledgeEdge(source_id="PY05", target_id="PY08", course_id="python_programming", dependency_type="strict", weight=1.2),
        KnowledgeEdge(source_id="PY07", target_id="PY08", course_id="python_programming", dependency_type="strict", weight=1.0),
    ],
}

# 知识基础 → 节点初始掌握度映射（按课程隔离）
SEED_KNOWLEDGE_MASTERY = {
    "data_structures": {
        "python_basics": {"N02": 0.75, "N03": 0.70, "N04": 0.65, "N05": 0.65},
        "data_structures": {"N01": 0.70, "N02": 0.80, "N03": 0.75, "N06": 0.60},
        "databases": {"N09": 0.55, "N17": 0.50},
    },
    "operating_systems": {
        "python_basics": {"OS01": 0.50},
        "dev_tools": {"OS02": 0.40},
    },
    "computer_networks": {
        "python_basics": {"CN01": 0.55},
        "dev_tools": {"CN03": 0.40},
    },
    "machine_learning": {
        "python_basics": {"ML01": 0.60, "ML02": 0.40},
        "linear_algebra": {"ML02": 0.55},
        "ml_basics": {"ML01": 0.70},
    },
    "python_programming": {
        "python_basics": {"PY01": 0.85, "PY02": 0.70},
        "none": {},
    },
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

    def get_all_nodes(self, course_id: str = "data_structures") -> List[KnowledgeNode]:
        """获取指定课程的全部知识点节点。"""
        if self._neo4j_available:
            return self._export_nodes_from_neo4j(course_id)
        return [n for n in self._in_memory_nodes.values() if n.course_id == course_id]

    def get_all_edges(self, course_id: str = "data_structures") -> List[KnowledgeEdge]:
        """获取指定课程的全部依赖边。"""
        if self._neo4j_available:
            return self._export_edges_from_neo4j(course_id)
        return [e for e in self._in_memory_edges if e.course_id == course_id]

    def get_node_by_id(self, node_id: str, course_id: str = "data_structures") -> Optional[KnowledgeNode]:
        """按 ID 获取单个节点。"""
        nodes = self.get_all_nodes(course_id)
        for n in nodes:
            if n.node_id == node_id:
                return n
        return None

    def get_node_title(self, node_id: str) -> str:
        """获取节点标题（用于 UI 展示）。"""
        node = self.get_node_by_id(node_id)
        return node.title if node else node_id

    def get_knowledge_mastery_map(
        self, knowledge_items: List[str], course_id: str = "data_structures"
    ) -> Dict[str, float]:
        """根据用户知识基础列表，计算初始掌握度映射（按课程隔离）。"""
        course_mastery = SEED_KNOWLEDGE_MASTERY.get(course_id, {})
        result: Dict[str, float] = {}
        for item in knowledge_items:
            node_mastery = course_mastery.get(item, {})
            for nid, m in node_mastery.items():
                result[nid] = max(result.get(nid, 0.0), m)
        return result

    def get_node_id_to_title_map(self, course_id: str = "data_structures") -> Dict[str, str]:
        nodes = self.get_all_nodes(course_id)
        return {n.node_id: n.title for n in nodes}

    def create_path_planner(self, course_id: str = "data_structures"):
        """创建配置好的 PathPlanner 实例（仅加载指定课程数据）。"""
        from ..infrastructure.path_planner import PathPlanner
        nodes = self.get_all_nodes(course_id)
        edges = self.get_all_edges(course_id)
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
                database=os.getenv("NEO4J_DATABASE", "neo4j"),
            )
            self._neo4j_client = Neo4jClient(config)
            self._neo4j_client.connect()

            # 检查是否为空数据库 → 自动播种全部课程
            existing = self._export_nodes_from_neo4j("data_structures")
            if not existing:
                self._seed_neo4j()  # 播种全部课程

            return True
        except Exception:
            return False

    def _seed_neo4j(self, course_id: Optional[str] = None) -> None:
        """将种子节点和边写入 Neo4j。如果指定 course_id 则只播种该课程。"""
        try:
            courses = [course_id] if course_id else list(SEED_NODES.keys())
            for cid in courses:
                for node in SEED_NODES.get(cid, []):
                    self._neo4j_client.create_knowledge_node(node)
                for edge in SEED_EDGES.get(cid, []):
                    self._neo4j_client.create_dependency_edge(edge)
        except Exception:
            pass

    def seed_course(self, course_id: str) -> None:
        """播种指定课程的知识图谱数据到 Neo4j。"""
        if self._neo4j_available:
            self._seed_neo4j(course_id)

    def _export_nodes_from_neo4j(self, course_id: str = "data_structures") -> List[KnowledgeNode]:
        if not self._neo4j_available:
            return []
        try:
            return self._neo4j_client.export_nodes_for_planner(course_id)
        except Exception:
            self._neo4j_available = False
            print("[KG] Neo4j connection lost — falling back to in-memory")
            return []

    def _export_edges_from_neo4j(self, course_id: str = "data_structures") -> List[KnowledgeEdge]:
        if not self._neo4j_available:
            return []
        try:
            return self._neo4j_client.export_edges_for_planner(course_id)
        except Exception:
            self._neo4j_available = False
            return []

    # ------------------------------------------------------------------
    # 内存回退
    # ------------------------------------------------------------------

    def _init_in_memory(self) -> None:
        """初始化内存中的种子数据（所有课程）。"""
        self._in_memory_nodes = {}
        self._in_memory_edges = []
        for cid in SEED_NODES:
            for n in SEED_NODES[cid]:
                self._in_memory_nodes[n.node_id] = n
        for cid in SEED_EDGES:
            self._in_memory_edges.extend(SEED_EDGES[cid])


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
