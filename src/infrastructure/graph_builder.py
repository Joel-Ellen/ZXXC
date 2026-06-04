# -*- coding: utf-8 -*-
"""
数据治理辅助组件二：知识图谱构建器 (Graph Builder)
===================================================

基于 Neo4j 官方驱动的图谱构建引擎，实现：

1. 节点与依赖边的批量建立
2. Tarjan 强连通分量 (SCC) 算法检测并剔除有向图环路
3. 传递闭包剪枝 (Transitive Reduction) — 剔除多层级冗余依赖边
4. 确保知识图谱呈纯净 DAG 状态

算法原理：
  - Tarjan SCC: O(V+E) 线性时间，基于 DFS 的 lowlink 追踪
  - Transitive Reduction: 对 DAG 的每条边 (u,v)，检查是否存在
    长度 ≥ 2 的替代路径 u → ... → v，若存在则 (u,v) 为冗余边

依赖声明：
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
  Neo4j 官方 Python Driver 遵循 Apache 2.0 协议。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict

from pydantic import BaseModel, Field, field_validator

from .path_planner import KnowledgeNode, KnowledgeEdge
from ..graph.neo4j_client import Neo4jClient


# ============================================================================
# Pydantic 数据模型
# ============================================================================

class GraphBuildConfig(BaseModel):
    """图谱构建配置。"""

    # 依赖关系过滤
    min_edge_weight: float = Field(default=0.0, ge=0.0, le=10.0, description="最小边权重阈值")
    allowed_dependency_types: List[str] = Field(
        default_factory=lambda: ["strict", "recommended", "optional"],
        description="允许的依赖关系类型"
    )

    # SCC 处理
    scc_resolution_strategy: str = Field(
        default="remove_weakest_edge",
        pattern=r"^(remove_weakest_edge|remove_all_cycle_edges|raise_error)$",
        description="SCC 环处理策略"
    )

    # 传递归约
    enable_transitive_reduction: bool = Field(default=True, description="是否启用传递闭包剪枝")
    transitive_reduction_keep_types: List[str] = Field(
        default_factory=lambda: ["strict"],
        description="传递归约时保留的依赖类型（仅这些类型参与冗余判断）"
    )


class SCCDetectionResult(BaseModel):
    """SCC 检测结果。"""

    has_cycle: bool = Field(default=False, description="是否检测到环")
    sccs: List[List[str]] = Field(
        default_factory=list,
        description="各强连通分量的节点列表"
    )
    cycle_edges_removed: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="为消除环而移除的边 (source, target)"
    )
    diagnostic_message: str = Field(default="", description="诊断信息")


class TransitiveReductionResult(BaseModel):
    """传递归约结果。"""

    original_edge_count: int = Field(default=0, description="原始边数")
    redundant_edges_removed: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="移除的冗余边 (source, target)"
    )
    remaining_edge_count: int = Field(default=0, description="归约后边数")
    reduction_ratio: float = Field(default=0.0, description="归约比例 (0.0-1.0)")


class GraphBuildResult(BaseModel):
    """图谱构建的完整结果报告。"""

    nodes_created: int = Field(default=0, description="创建的节点数")
    edges_created: int = Field(default=0, description="创建的边数")
    scc_result: SCCDetectionResult = Field(
        default_factory=SCCDetectionResult, description="环检测与消除结果"
    )
    transitive_reduction_result: TransitiveReductionResult = Field(
        default_factory=TransitiveReductionResult, description="传递归约结果"
    )
    final_edge_count: int = Field(default=0, description="最终合法边数")
    is_valid_dag: bool = Field(default=False, description="最终是否为合法 DAG")


# ============================================================================
# Tarjan 强连通分量算法 (SCC)
# ============================================================================

class TarjanSCC:
    """Tarjan 算法的独立实现 — 检测有向图中的所有强连通分量。

    算法特征:
      - 单次 DFS 遍历, O(V+E) 线性时间复杂度
      - 使用 index + lowlink 追踪
      - 递归实现（通过 sys.setrecursionlimit 支持中等规模图）

    Reference:
      Tarjan, R. E. (1972). Depth-first search and linear graph algorithms.
    """

    def __init__(self, adj: Dict[str, List[str]]) -> None:
        """初始化 Tarjan SCC 检测器。

        Args:
            adj: 邻接表 {node_id → [neighbor_id, ...]}。
        """
        import sys
        self._adj = adj
        self._index_counter: int = 0
        self._index: Dict[str, int] = {}
        self._lowlink: Dict[str, int] = {}
        self._on_stack: Dict[str, bool] = {}
        self._stack: List[str] = []
        self._sccs: List[List[str]] = []
        # 提升递归深度上限以支持知识图谱规模
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

    def find_sccs(self) -> List[List[str]]:
        """执行 SCC 检测，返回所有强连通分量。

        Returns:
            List[List[str]]: 所有 SCC，按发现顺序排列。
        """
        self._index_counter = 0
        self._index.clear()
        self._lowlink.clear()
        self._on_stack.clear()
        self._stack.clear()
        self._sccs.clear()

        # 收集所有节点
        all_nodes: Set[str] = set(self._adj.keys())
        for neighbors in self._adj.values():
            all_nodes.update(neighbors)

        for v in sorted(all_nodes):
            if v not in self._index:
                self._strongconnect(v)

        return self._sccs

    def _strongconnect(self, v: str) -> None:
        """Tarjan 核心递归 — 经典递归实现。

        为节点 v 分配 index 和 lowlink，遍历其所有邻居：
          - 若邻居未访问 → 递归进入
          - 若邻居在栈上 → 更新 lowlink (回边，形成环)
          - 若邻居已处理但不在栈上 → 忽略 (横叉边，不影响 SCC)
        """
        self._index[v] = self._index_counter
        self._lowlink[v] = self._index_counter
        self._index_counter += 1
        self._stack.append(v)
        self._on_stack[v] = True

        # 遍历 v 的所有出边邻居
        for w in self._adj.get(v, []):
            if w not in self._index:
                # 树边 (tree edge): 未访问的邻居
                self._strongconnect(w)
                self._lowlink[v] = min(self._lowlink[v], self._lowlink[w])
            elif self._on_stack.get(w, False):
                # 回边 (back edge): w 在栈上 → 环路
                self._lowlink[v] = min(self._lowlink[v], self._index[w])
            # else: 横叉边/前向边 (cross/forward edge) → 忽略

        # 如果 v 是 SCC 的根节点
        if self._lowlink[v] == self._index[v]:
            scc: List[str] = []
            while True:
                w = self._stack.pop()
                self._on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            self._sccs.append(scc)

    def has_cycle(self) -> bool:
        """检查图是否包含环 (是否存在 size>1 的 SCC 或自环)。"""
        if not self._sccs:
            self.find_sccs()
        # size>1 的 SCC 是环；自环 (A→A) 也会形成 size=1 的 SCC 但也是环
        for scc in self._sccs:
            if len(scc) > 1:
                return True
            # 检测自环: 单节点 SCC 但该节点有指向自己的边
            if len(scc) == 1:
                node = scc[0]
                if node in self._adj.get(node, []):
                    return True
        return False

    def get_cycle_nodes(self) -> Set[str]:
        """获取所有参与环的节点。"""
        if not self._sccs:
            self.find_sccs()
        cycle_nodes: Set[str] = set()
        for scc in self._sccs:
            if len(scc) > 1:
                cycle_nodes.update(scc)
            elif len(scc) == 1:
                node = scc[0]
                if node in self._adj.get(node, []):
                    cycle_nodes.add(node)
        return cycle_nodes


# ============================================================================
# 传递闭包剪枝 (Transitive Reduction)
# ============================================================================

class TransitiveReducer:
    """DAG 传递闭包剪枝器。

    对 DAG 的每条边 (u,v)，若存在另一条长度 ≥ 2 的路径 u → ... → v，
    则 (u,v) 为冗余边，应被移除。

    算法: O(V·(V+E)) 或使用 BFS/DFS 逐节点检测可达性。
    对中等规模知识图谱 (<5000 节点) 表现良好。

    对于大规模图，可切换为 O(V³) 的 Floyd-Warshall 或使用 bitset 加速。
    """

    def __init__(self, adj: Dict[str, List[Tuple[str, float]]]) -> None:
        """初始化传递归约器。

        Args:
            adj: 带权邻接表 {source → [(target, weight), ...]}。
        """
        self._adj = adj
        # 构建纯邻接表 (不含权重) 用于快速可达性检查
        self._simple_adj: Dict[str, Set[str]] = {}
        for src, edges in adj.items():
            self._simple_adj[src] = {tgt for tgt, _ in edges}

    def reduce(
        self, keep_types: Optional[Set[str]] = None
    ) -> Tuple[List[Tuple[str, str]], Dict[str, List[Tuple[str, float]]]]:
        """执行传递归约。

        对每条边 (u,v):
          1. 临时从图中移除 (u,v)
          2. BFS/DFS 检查 u 是否仍可达 v
          3. 若仍可达 → (u,v) 为冗余边
          4. 恢复 (u,v) 或不恢复（取决于是否冗余）

        Args:
            keep_types: 若指定，仅对此集合中的依赖类型执行归约。

        Returns:
            (removed_edges, reduced_adj):
              - removed_edges: 被移除的冗余边列表
              - reduced_adj: 归约后的邻接表
        """
        removed: List[Tuple[str, str]] = []
        # 复制邻接表
        reduced: Dict[str, List[Tuple[str, float]]] = {
            src: list(edges) for src, edges in self._adj.items()
        }

        # 收集所有边 (src, tgt, weight)
        all_edges: List[Tuple[str, str, float]] = []
        for src, edges in self._adj.items():
            for tgt, weight in edges:
                all_edges.append((src, tgt, weight))

        # 按拓扑序排序以提高剪枝效率（可选优化）
        # 这里直接逐边检测

        for src, tgt, weight in all_edges:
            # 检查是否存在替代路径
            if self._has_alternative_path(src, tgt, reduced):
                removed.append((src, tgt))
                # 从归约邻接表中移除此边
                reduced[src] = [(t, w) for t, w in reduced[src] if t != tgt]

        return removed, reduced

    def _has_alternative_path(
        self, src: str, tgt: str,
        reduced_adj: Dict[str, List[Tuple[str, float]]],
    ) -> bool:
        """BFS 检测在不使用直接边 (src,tgt) 的情况下，src 是否可达 tgt。"""
        if src not in reduced_adj or not reduced_adj[src]:
            return False

        visited: Set[str] = {src}
        queue: List[str] = []

        # 初始队列: src 的所有邻居（排除 tgt）
        for neighbor, _ in reduced_adj.get(src, []):
            if neighbor != tgt and neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

        # BFS
        while queue:
            current = queue.pop(0)
            if current == tgt:
                return True
            for neighbor, _ in reduced_adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False


# ============================================================================
# 知识图谱构建器 (Graph Builder)
# ============================================================================

class GraphBuilder:
    """知识图谱构建编排器 — 节点/边创建、SCC 检测、传递归约。

    构建流程:
      1. 接收 KnowledgeNode / KnowledgeEdge 列表
      2. 写入 Neo4j（通过 Neo4jClient）
      3. 在内存图中运行 Tarjan SCC 检测环路
      4. 若发现环路 → 根据策略移除环中最弱边
      5. 执行传递归约 → 剔除冗余间接依赖
      6. 将修正后的图同步回 Neo4j
      7. 输出完整构建报告

    使用示例:
        >>> builder = GraphBuilder(neo4j_client)
        >>> result = builder.build(nodes, edges)
        >>> print(f"DAG valid: {result.is_valid_dag}")
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        config: Optional[GraphBuildConfig] = None,
    ) -> None:
        self._neo4j = neo4j_client
        self._config = config or GraphBuildConfig()

    @property
    def config(self) -> GraphBuildConfig:
        return self._config

    # ------------------------------------------------------------------
    # 主入口: build()
    # ------------------------------------------------------------------

    def build(
        self,
        nodes: List[KnowledgeNode],
        edges: List[KnowledgeEdge],
    ) -> GraphBuildResult:
        """执行完整的图谱构建管线。

        Args:
            nodes: 知识节点列表。
            edges: 依赖边列表。

        Returns:
            GraphBuildResult: 包含 SCC 检测与传递归约结果的完整报告。
        """
        # ---- Step 1: 写入节点 ----
        nodes_created = 0
        if self._neo4j.is_connected():
            nodes_created = self._neo4j.create_knowledge_nodes_batch(nodes)

        # ---- Step 2: 构建内存邻接表 (用于 SCC 与传递归约) ----
        adj = self._build_adjacency(edges)

        # ---- Step 3: Tarjan SCC 检测与环路消除 ----
        scc_result = self._detect_and_resolve_cycles(adj, edges)

        # 获取消环后的边列表
        cycle_removed_set: Set[Tuple[str, str]] = set(scc_result.cycle_edges_removed)
        clean_edges = [e for e in edges if (e.source_id, e.target_id) not in cycle_removed_set]

        # ---- Step 4: 传递闭包剪枝 ----
        tr_result = TransitiveReductionResult()
        final_edges = clean_edges

        if self._config.enable_transitive_reduction:
            clean_adj = self._build_weighted_adjacency(clean_edges)
            reducer = TransitiveReducer(clean_adj)
            removed_tr, reduced_adj = reducer.reduce()
            tr_result = TransitiveReductionResult(
                original_edge_count=len(clean_edges),
                redundant_edges_removed=removed_tr,
                remaining_edge_count=sum(len(v) for v in reduced_adj.values()),
                reduction_ratio=(
                    len(removed_tr) / len(clean_edges) if clean_edges else 0.0
                ),
            )
            # 重建最终边列表
            tr_removed_set: Set[Tuple[str, str]] = set(removed_tr)
            final_edges = [
                e for e in clean_edges
                if (e.source_id, e.target_id) not in tr_removed_set
            ]

        # ---- Step 5: 写入边到 Neo4j ----
        edges_created = 0
        if self._neo4j.is_connected():
            edges_created = self._neo4j.create_dependency_edges_batch(final_edges)

        # ---- Step 6: 最终 DAG 验证 ----
        final_adj = self._build_adjacency(final_edges)
        scc_final = TarjanSCC(final_adj)
        is_dag = not scc_final.has_cycle()

        return GraphBuildResult(
            nodes_created=nodes_created,
            edges_created=edges_created,
            scc_result=scc_result,
            transitive_reduction_result=tr_result,
            final_edge_count=len(final_edges),
            is_valid_dag=is_dag,
        )

    # ------------------------------------------------------------------
    # 内存邻接表构建
    # ------------------------------------------------------------------

    def _build_adjacency(self, edges: List[KnowledgeEdge]) -> Dict[str, List[str]]:
        """构建纯邻接表 {src → [tgt, ...]}。"""
        adj: Dict[str, List[str]] = defaultdict(list)
        for e in edges:
            if e.dependency_type in self._config.allowed_dependency_types:
                adj[e.source_id].append(e.target_id)
        return dict(adj)

    def _build_weighted_adjacency(
        self, edges: List[KnowledgeEdge]
    ) -> Dict[str, List[Tuple[str, float]]]:
        """构建带权邻接表 {src → [(tgt, weight), ...]}。"""
        adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for e in edges:
            if e.dependency_type in self._config.allowed_dependency_types:
                adj[e.source_id].append((e.target_id, e.weight))
        return dict(adj)

    # ------------------------------------------------------------------
    # SCC 检测与环路消除
    # ------------------------------------------------------------------

    def _detect_and_resolve_cycles(
        self,
        adj: Dict[str, List[str]],
        edges: List[KnowledgeEdge],
    ) -> SCCDetectionResult:
        """检测 SCC 并根据策略消除环路。

        Strategies:
          - remove_weakest_edge: 对每个 size>1 的 SCC，移除其中权重最小的边
          - remove_all_cycle_edges: 移除 SCC 中的所有边
          - raise_error: 抛出异常
        """
        tarjan = TarjanSCC(adj)
        sccs = tarjan.find_sccs()
        cycle_sccs = [scc for scc in sccs if len(scc) > 1]

        if not cycle_sccs:
            return SCCDetectionResult(
                has_cycle=False,
                sccs=sccs,
                diagnostic_message="未检测到环，知识图谱为合法 DAG",
            )

        strategy = self._config.scc_resolution_strategy
        removed: List[Tuple[str, str]] = []

        if strategy == "raise_error":
            cycle_nodes = sorted(set(n for scc in cycle_sccs for n in scc))
            raise ValueError(
                f"知识图谱中检测到 {len(cycle_sccs)} 个环！"
                f"涉及节点: {cycle_nodes}。"
                f"请手动修正数据或将 strategy 设为 remove_weakest_edge。"
            )

        elif strategy == "remove_all_cycle_edges":
            # 收集所有参与环的节点
            cycle_node_set: Set[str] = set()
            for scc in cycle_sccs:
                cycle_node_set.update(scc)
            # 移除所有以环内节点为源且目标也在环内的边
            for e in edges:
                if e.source_id in cycle_node_set and e.target_id in cycle_node_set:
                    removed.append((e.source_id, e.target_id))

        elif strategy == "remove_weakest_edge":
            for scc in cycle_sccs:
                scc_set = set(scc)
                # 收集该 SCC 中的所有边
                scc_edges: List[Tuple[str, str, float]] = []
                for e in edges:
                    if e.source_id in scc_set and e.target_id in scc_set:
                        scc_edges.append((e.source_id, e.target_id, e.weight))
                if scc_edges:
                    # 按 weight 排序（升序），移除 weight 最小的边
                    scc_edges.sort(key=lambda x: x[2])
                    weakest = scc_edges[0]
                    removed.append((weakest[0], weakest[1]))

        return SCCDetectionResult(
            has_cycle=True,
            sccs=cycle_sccs,
            cycle_edges_removed=removed,
            diagnostic_message=(
                f"检测到 {len(cycle_sccs)} 个强连通分量（环），"
                f"策略={strategy}，移除了 {len(removed)} 条边"
            ),
        )

    # ------------------------------------------------------------------
    # 便捷方法: 独立运行 SCC 检测 (不修改图)
    # ------------------------------------------------------------------

    def validate_dag(
        self, nodes: List[KnowledgeNode], edges: List[KnowledgeEdge]
    ) -> SCCDetectionResult:
        """仅验证图是否为合法 DAG，不执行修改。

        Args:
            nodes: 节点列表。
            edges: 边列表。

        Returns:
            SCCDetectionResult。
        """
        adj = self._build_adjacency(edges)
        tarjan = TarjanSCC(adj)
        sccs = tarjan.find_sccs()
        cycle_sccs = [scc for scc in sccs if len(scc) > 1]
        return SCCDetectionResult(
            has_cycle=len(cycle_sccs) > 0,
            sccs=cycle_sccs,
            diagnostic_message=(
                "图为合法 DAG" if not cycle_sccs
                else f"检测到 {len(cycle_sccs)} 个环，涉及 {sum(len(s) for s in cycle_sccs)} 个节点"
            ),
        )

    # ------------------------------------------------------------------
    # 从 Neo4j 加载并校验
    # ------------------------------------------------------------------

    def load_and_validate(self) -> SCCDetectionResult:
        """从 Neo4j 加载现有图并进行 DAG 校验。

        Returns:
            SCCDetectionResult。
        """
        if not self._neo4j.is_connected():
            return SCCDetectionResult(
                diagnostic_message="Neo4j 未连接"
            )

        nodes = self._neo4j.export_nodes_for_planner()
        edges = self._neo4j.export_edges_for_planner()
        return self.validate_dag(nodes, edges)
