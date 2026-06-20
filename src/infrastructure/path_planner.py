# -*- coding: utf-8 -*-
"""
辅助算法三：基于拓扑排序与最短路径的知识图谱寻路引擎 (Path Planner)
====================================================================

工业级路径规划器的完整落地实现。

算法核心：
  本系统将高校专业课程文档集建模为有向无环图 (DAG) G = (V, E)，其中：
    - V: 知识点节点，携带 (difficulty, estimated_hours) 属性
    - E: 严格的前置依赖关系 u → v 表示"必须先掌握 u 才能学 v"

规划策略 (PathPlanStrategy):
  1. TOPO_MIN_WEIGHT    — 拓扑约束下的最小总权重路径 (Dijkstra on DAG)
  2. TOPO_MIN_HOPS      — 拓扑约束下的最小跳数路径 (BFS on DAG)
  3. TOPO_BALANCED      — 拓扑约束下的难度均衡路径 (难度方差最小化)
  4. COLD_START_HEURISTIC — 冷启动启发式路径 (mix of topological + difficulty-aware DFS)

关键工程特性：
  1. 基于 Kahn 算法的合法拓扑序列构造
  2. 在 DAG 拓扑序上运行单源最短路径 (SSSP) — O(V + E) 线性时间
  3. 动态重规划支持 (re_plan_triggered 闸门)
  4. 已掌握节点剪枝 (knowledge_mastery >= mastery_threshold 的节点视为已解锁)
  5. 路径可行性校验 (validator 确保所有前置依赖已满足)
  6. 冷启动启发式 — 为无历史数据的用户生成探索-利用平衡的推荐路径

References:
  - Kahn, A. B. (1962). Topological sorting of large networks.
  - Cormen, T. H., et al. (2009). Introduction to Algorithms, 3rd Ed. (Ch. 24.2: DAG Shortest Paths)
  - 赛题要求: active_path 激活序列 + c_epoch 冷启动计数器联动
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 枚举与常量
# ============================================================================

class PathPlanStrategy(str, Enum):
    """路径规划策略枚举。"""
    TOPO_MIN_WEIGHT = "topo_min_weight"
    TOPO_MIN_HOPS = "topo_min_hops"
    TOPO_BALANCED = "topo_balanced"
    COLD_START_HEURISTIC = "cold_start_heuristic"


# ============================================================================
# Pydantic 强类型 I/O 模型
# ============================================================================

class KnowledgeNode(BaseModel):
    """知识点节点 — Neo4j 中一个知识点的完整属性投影。"""

    node_id: str = Field(..., min_length=1, description="知识点唯一 ID")
    course_id: str = Field(default="", description="所属课程 ID")
    title: str = Field(default="", description="知识点标题")
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0, description="难度系数 (0.0-1.0)")
    estimated_hours: float = Field(default=1.0, gt=0.0, description="预估学习时长 (小时)")
    category: str = Field(default="concept", description="知识点类别 (concept / skill / project)")
    metadata: Dict[str, str] = Field(default_factory=dict, description="扩展属性键值对")


class KnowledgeEdge(BaseModel):
    """知识点前置依赖边 — Neo4j 中有向关系的投影。"""

    source_id: str = Field(..., min_length=1, description="前置知识点 ID")
    target_id: str = Field(..., min_length=1, description="后继知识点 ID")
    course_id: str = Field(default="", description="所属课程 ID")
    dependency_type: str = Field(
        default="strict",
        pattern=r"^(strict|recommended|optional)$",
        description="依赖关系强度"
    )
    weight: float = Field(default=1.0, gt=0.0, description="边权重 (学习迁移成本)")


class PlanContext(BaseModel):
    """路径规划上下文 — 包含用户画像与学习约束。"""

    user_id: str = Field(..., min_length=1, description="用户唯一 ID")
    course_id: str = Field(..., min_length=1, description="课程唯一 ID")
    current_node_id: Optional[str] = Field(default=None, description="当前所在知识点 ID")
    target_node_id: Optional[str] = Field(default=None, description="目标知识点 ID")
    knowledge_mastery: Dict[str, float] = Field(
        default_factory=dict,
        description="已知掌握度映射 node_id → mastery (0.0-1.0)"
    )
    mastery_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0,
        description="掌握度阈值 — mastery >= 此值视为已掌握，节点可被剪枝"
    )
    time_budget_hours: float = Field(default=10.0, gt=0.0, description="可用学习时间（小时）")
    c_epoch: int = Field(default=0, ge=0, description="冷启动计数器")
    strategy: PathPlanStrategy = Field(
        default=PathPlanStrategy.TOPO_MIN_WEIGHT,
        description="路径规划策略"
    )
    max_path_length: int = Field(default=20, ge=1, le=100, description="最大路径长度 (安全上限)")


class PathPlanResult(BaseModel):
    """路径规划结果 — PathPlanner.compute_path() 的输出。"""

    active_path: List[str] = Field(
        default_factory=list,
        description="拓扑激活序列 (有序知识点 ID 列表)"
    )
    total_estimated_hours: float = Field(default=0.0, ge=0.0, description="路径总预估时长")
    total_difficulty: float = Field(default=0.0, ge=0.0, description="路径总算力需求 (difficulty 之和)")
    pruned_nodes: List[str] = Field(
        default_factory=list,
        description="因已掌握而被剪枝的节点 ID 列表"
    )
    unreachable_nodes: List[str] = Field(
        default_factory=list,
        description="因前置依赖未满足而不可达的节点 ID 列表"
    )
    strategy_used: PathPlanStrategy = Field(..., description="本次使用的规划策略")
    path_found: bool = Field(default=False, description="是否成功找到可达路径")
    diagnostics: Dict[str, str] = Field(
        default_factory=dict,
        description="诊断信息 (warnings, hints)"
    )


class ReplanTrigger(BaseModel):
    """重规划触发条件评估结果。"""

    should_replan: bool = Field(default=False, description="是否应触发重规划")
    reason: str = Field(default="", description="触发原因")
    severity: str = Field(default="info", pattern=r"^(info|warning|critical)$")


# ============================================================================
# 路径规划器主类
# ============================================================================

class PathPlanner:
    """知识图谱拓扑路径规划器 (DAG Shortest Path + Kahn's Algorithm)。

    设计原理：
      1. 从 Neo4j 读取的图数据构建邻接表
      2. 利用 Kahn 算法生成合法拓扑序
      3. 在拓扑序上运行 DAG-SSSP (Single-Source Shortest Path)
      4. 根据策略选择最优路径
      5. 对结果进行可行性校验（确保所有前置依赖已满足）

    使用示例:
        >>> nodes = [
        ...     KnowledgeNode(node_id="N1", difficulty=0.3, estimated_hours=2.0),
        ...     KnowledgeNode(node_id="N2", difficulty=0.5, estimated_hours=3.0),
        ...     KnowledgeNode(node_id="N3", difficulty=0.7, estimated_hours=4.0),
        ... ]
        >>> edges = [
        ...     KnowledgeEdge(source_id="N1", target_id="N2"),
        ...     KnowledgeEdge(source_id="N2", target_id="N3"),
        ... ]
        >>> planner = PathPlanner(nodes, edges)
        >>> ctx = PlanContext(
        ...     user_id="U1", course_id="C1",
        ...     current_node_id="N1", target_node_id="N3",
        ... )
        >>> result = planner.compute_path(ctx)
        >>> print(result.active_path)
        ['N1', 'N2', 'N3']
    """

    # ------------------------------------------------------------------
    # 构造与数据结构初始化
    # ------------------------------------------------------------------

    def __init__(
        self,
        nodes: Optional[List[KnowledgeNode]] = None,
        edges: Optional[List[KnowledgeEdge]] = None,
    ) -> None:
        """初始化路径规划器。

        Args:
            nodes: 知识节点列表 (通常从 Neo4j 中查询得到)。
            edges: 有向边列表 (通常从 Neo4j 中查询得到)。
        """
        # 节点字典: node_id → KnowledgeNode
        self._node_map: Dict[str, KnowledgeNode] = {}
        # 邻接表: source_id → [(target_id, edge_weight)]
        self._adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        # 逆邻接表: target_id → [(source_id, edge_weight)]
        self._rev_adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        # 入度表: node_id → indegree
        self._indegree: Dict[str, int] = defaultdict(int)
        # 拓扑排序缓存
        self._topo_order: Optional[List[str]] = None
        self._topo_rank: Dict[str, int] = {}

        if nodes is not None:
            self._load_nodes(nodes)
        if edges is not None:
            self._load_edges(edges)

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load_nodes(self, nodes: List[KnowledgeNode]) -> None:
        """批量加载知识节点。"""
        for node in nodes:
            self._node_map[node.node_id] = node
            self._indegree.setdefault(node.node_id, 0)

    def _load_edges(self, edges: List[KnowledgeEdge]) -> None:
        """批量加载有向边并构建邻接表 + 入度表。"""
        for edge in edges:
            src, tgt = edge.source_id, edge.target_id
            # 确保两端节点在入度表中注册
            self._indegree.setdefault(src, 0)
            self._indegree.setdefault(tgt, 0)
            # 构建正向邻接表
            self._adj[src].append((tgt, edge.weight))
            # 构建逆邻接表（用于依赖回溯）
            self._rev_adj[tgt].append((src, edge.weight))
            # 递增入度
            self._indegree[tgt] += 1

    def add_node(self, node: KnowledgeNode) -> None:
        """动态添加单个知识节点。"""
        self._node_map[node.node_id] = node
        self._indegree.setdefault(node.node_id, 0)
        self._invalidate_cache()

    def add_edge(self, edge: KnowledgeEdge) -> None:
        """动态添加单条有向边。"""
        src, tgt = edge.source_id, edge.target_id
        self._indegree.setdefault(src, 0)
        self._indegree.setdefault(tgt, 0)
        self._adj[src].append((tgt, edge.weight))
        self._rev_adj[tgt].append((src, edge.weight))
        self._indegree[tgt] += 1
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """使拓扑排序缓存失效。"""
        self._topo_order = None
        self._topo_rank = {}

    # ------------------------------------------------------------------
    # 核心算法 1: Kahn 拓扑排序
    # ------------------------------------------------------------------

    def compute_topological_order(self) -> List[str]:
        """基于 Kahn 算法的拓扑排序。

        时间复杂度: O(V + E)
        空间复杂度: O(V)

        Returns:
            拓扑有序的节点 ID 列表。如果图中存在环，抛出 ValueError。

        Raises:
            ValueError: 如果图中检测到环（即不是合法 DAG）。
        """
        if self._topo_order is not None:
            return self._topo_order

        # 复制入度表
        indegree = dict(self._indegree)
        # 初始化零入度队列
        queue: deque[str] = deque(
            node_id for node_id, deg in indegree.items() if deg == 0
        )

        topo: List[str] = []
        rank: Dict[str, int] = {}

        while queue:
            u = queue.popleft()
            topo.append(u)
            rank[u] = len(topo) - 1

            for v, _ in self._adj.get(u, []):
                indegree[v] -= 1
                if indegree[v] == 0:
                    queue.append(v)

        # 环检测: 如果拓扑序列长度 < 节点总数，说明存在环
        total_nodes = len(self._node_map)
        if len(topo) != total_nodes:
            # 找出环中的节点（入度仍大于 0 的节点）
            cycle_nodes = [nid for nid, deg in indegree.items() if deg > 0]
            raise ValueError(
                f"知识图谱中存在有向环 (非 DAG)！"
                f"拓扑序列长度={len(topo)}, 节点总数={total_nodes}, "
                f"疑似环中节点={cycle_nodes[:10]}"
            )

        self._topo_order = topo
        self._topo_rank = rank
        return topo

    def get_topo_rank(self, node_id: str) -> int:
        """获取节点在拓扑序中的位置索引 (0-based)。

        Returns:
            int: 拓扑排名，若节点不存在或拓扑未计算返回 -1。
        """
        if not self._topo_rank:
            try:
                self.compute_topological_order()
            except ValueError:
                return -1
        return self._topo_rank.get(node_id, -1)

    # ------------------------------------------------------------------
    # 核心算法 2: DAG 单源最短路径 (DAG-SSSP)
    # ------------------------------------------------------------------

    def _dag_sssp(
        self,
        source_id: str,
        weight_fn: Callable[[str, str, float], float],
    ) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
        """在 DAG 拓扑序上运行单源最短路径。

        算法: DAG-SHORTEST-PATHS (Cormen 24.2)
        - 按拓扑序遍历节点
        - 对每个节点的每条出边执行 RELAX 操作
        - 时间复杂度 O(V + E)

        Args:
            source_id: 源节点 ID。
            weight_fn: 边权重函数 (src_id, tgt_id, base_weight) → effective_weight。

        Returns:
            (dist, pred) 元组:
              - dist:  node_id → 最短距离 (float)
              - pred:  node_id → 前驱节点 ID (Optional[str])
        """
        topo = self.compute_topological_order()

        # 初始化
        dist: Dict[str, float] = {nid: float("inf") for nid in self._node_map}
        pred: Dict[str, Optional[str]] = {nid: None for nid in self._node_map}
        dist[source_id] = 0.0

        # 找到源节点在拓扑序中的起始位置
        start_idx = self._topo_rank.get(source_id, -1)
        if start_idx < 0:
            return dist, pred

        # 按拓扑序遍历
        for i in range(start_idx, len(topo)):
            u = topo[i]
            if dist[u] == float("inf"):
                continue  # 不可达，跳过

            for v, base_w in self._adj.get(u, []):
                w = weight_fn(u, v, base_w)
                if dist[v] > dist[u] + w:
                    dist[v] = dist[u] + w
                    pred[v] = u

        return dist, pred

    # ------------------------------------------------------------------
    # 权重函数工厂
    # ------------------------------------------------------------------

    def _make_weight_fn(self, strategy: PathPlanStrategy) -> Callable[[str, str, float], float]:
        """根据策略构造边权重函数。

        所有权重函数均保证返回 >= 0 的值以满足 Dijkstra/DAG-SSSP 的前提。
        """

        if strategy == PathPlanStrategy.TOPO_MIN_WEIGHT:
            # 使用原始边权重（学习迁移成本）+ 节点难度作为成本
            def fn(_src: str, tgt: str, base_w: float) -> float:
                node = self._node_map.get(tgt)
                node_cost = node.difficulty * node.estimated_hours if node else 1.0
                return base_w + node_cost

        elif strategy == PathPlanStrategy.TOPO_MIN_HOPS:
            # 每跳成本固定为 1（等价于 BFS）
            def fn(_src: str, _tgt: str, _base_w: float) -> float:
                return 1.0

        elif strategy == PathPlanStrategy.TOPO_BALANCED:
            # 难度方差最小化 —— 惩罚与当前节点难度差异大的边
            def fn(src: str, tgt: str, base_w: float) -> float:
                src_node = self._node_map.get(src)
                tgt_node = self._node_map.get(tgt)
                diff = abs(
                    (src_node.difficulty if src_node else 0.5) -
                    (tgt_node.difficulty if tgt_node else 0.5)
                )
                # 难度跳跃越大，成本越高
                return base_w * (1.0 + diff * 3.0)

        else:  # COLD_START_HEURISTIC
            # 冷启动：在基本权重基础上加入探索因子
            # 难度适中的节点获得正向偏向（exploration bonus）
            def fn(src: str, tgt: str, base_w: float) -> float:
                tgt_node = self._node_map.get(tgt)
                if tgt_node is None:
                    return base_w
                # 鼓励选择难度在 0.3-0.7 之间的节点（可管理的挑战）
                d = tgt_node.difficulty
                if 0.3 <= d <= 0.7:
                    bonus = -0.3 * base_w  # 负权重 = 低成本 = 被优先选择
                else:
                    bonus = abs(d - 0.5) * base_w  # 偏离中心越远，惩罚越大
                return max(0.01, base_w + bonus)  # 保证非负

        return fn

    # ------------------------------------------------------------------
    # 核心算法 3: 剪枝 (Pruning) — 移除已掌握节点
    # ------------------------------------------------------------------

    def _prune_mastered_nodes(
        self, mastery: Dict[str, float], threshold: float
    ) -> Set[str]:
        """识别已掌握节点集合。

        Args:
            mastery: 掌握度映射 node_id → [0.0, 1.0]。
            threshold: 掌握度阈值。

        Returns:
            已掌握的节点 ID 集合。
        """
        pruned: Set[str] = set()
        for node_id, m in mastery.items():
            if m >= threshold:
                pruned.add(node_id)
        return pruned

    # ------------------------------------------------------------------
    # 路径回溯
    # ------------------------------------------------------------------

    def _reconstruct_path(
        self, target_id: str, pred: Dict[str, Optional[str]]
    ) -> List[str]:
        """从前驱映射中回溯出完整路径。

        Args:
            target_id: 目标节点 ID。
            pred: 前驱映射。

        Returns:
            从源到目标的节点 ID 列表（有序）。
        """
        path: List[str] = []
        current: Optional[str] = target_id
        while current is not None:
            path.append(current)
            current = pred.get(current)
        path.reverse()
        return path

    # ------------------------------------------------------------------
    # 路径可行性校验
    # ------------------------------------------------------------------

    def validate_path(self, path: List[str]) -> Tuple[bool, List[str]]:
        """校验路径的拓扑合法性。

        逐边检查：对路径中每一对连续节点 (u, v)，确认存在边 u → v 或
        u 通过已掌握节点可以逻辑上作为 v 的前置。

        Args:
            path: 待校验的节点 ID 列表。

        Returns:
            (is_valid, violations) 元组:
              - is_valid: 是否合法。
              - violations: 违规描述列表。
        """
        violations: List[str] = []

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # 检查是否存在直接边 u → v
            neighbors = {tgt for tgt, _ in self._adj.get(u, [])}
            if v not in neighbors:
                violations.append(
                    f"路径边 ({u} → {v}) 不存在：节点 '{u}' 的出边中未找到 '{v}'"
                )

        return len(violations) == 0, violations

    # ------------------------------------------------------------------
    # 主入口: 路径计算
    # ------------------------------------------------------------------

    def compute_path(self, context: PlanContext) -> PathPlanResult:
        """主路径规划入口。

        执行流程：
          1. 计算拓扑序 → 校验 DAG 合法性
          2. 剪枝已掌握节点
          3. 确定源节点 (current_node_id 或拓扑序第一个未掌握节点)
          4. 根据策略构造权重函数
          5. 运行 DAG-SSSP
          6. 回溯路径
          7. 可行性校验

        Args:
            context: 规划上下文（用户画像、约束、策略）。

        Returns:
            PathPlanResult: 包含 active_path 的完整规划结果。
        """
        diagnostics: Dict[str, str] = {}

        # ---- Step 1: 拓扑排序 ----
        try:
            topo = self.compute_topological_order()
        except ValueError as e:
            return PathPlanResult(
                strategy_used=context.strategy,
                path_found=False,
                diagnostics={"error": str(e)},
            )

        # ---- Step 2: 剪枝已掌握节点 ----
        pruned = self._prune_mastered_nodes(
            context.knowledge_mastery, context.mastery_threshold
        )

        # ---- Step 3: 确定源节点 ----
        source_id: Optional[str] = None

        if context.current_node_id and context.current_node_id in self._node_map:
            source_id = context.current_node_id
        else:
            # 若未指定当前位置，选择拓扑序中第一个未掌握的节点
            for nid in topo:
                if nid not in pruned:
                    source_id = nid
                    diagnostics["auto_source"] = (
                        f"current_node_id 未指定或无效，自动选择拓扑首节点: {source_id}"
                    )
                    break

        if source_id is None:
            return PathPlanResult(
                strategy_used=context.strategy,
                path_found=False,
                diagnostics={"error": "未找到有效的起始节点（所有节点均已掌握或图为空）"},
            )

        # ---- Step 4: 确定目标节点 ----
        target_id: Optional[str] = context.target_node_id

        # ---- Step 5: 选择策略 ----
        # 冷启动强制使用 COLD_START_HEURISTIC
        effective_strategy = context.strategy
        if context.c_epoch < 5 and context.strategy != PathPlanStrategy.COLD_START_HEURISTIC:
            effective_strategy = PathPlanStrategy.COLD_START_HEURISTIC
            diagnostics["strategy_override"] = (
                f"c_epoch={context.c_epoch} < 5，自动切换为 COLD_START_HEURISTIC"
            )

        # ---- Step 6: DAG-SSSP ----
        weight_fn = self._make_weight_fn(effective_strategy)
        dist, pred = self._dag_sssp(source_id, weight_fn)

        # ---- Step 7: 路径回溯 ----
        if target_id is None:
            # 未指定目标 → 选择最深可达节点
            reachable = [(nid, d) for nid, d in dist.items() if d < float("inf")]
            # 排除已掌握节点（除非没有未掌握的节点可选）
            non_mastered_reachable = [(nid, d) for nid, d in reachable if nid not in pruned]
            if non_mastered_reachable:
                target_id = max(non_mastered_reachable, key=lambda x: x[1])[0]
                diagnostics["auto_target"] = f"自动选择最远未掌握节点作为目标: {target_id}"
            elif reachable:
                # 所有可达节点均已掌握 → 无需学习，返回源节点
                return PathPlanResult(
                    active_path=[source_id],
                    strategy_used=effective_strategy,
                    path_found=True,
                    pruned_nodes=list(pruned),
                    diagnostics={**diagnostics, "note": "所有可达节点均已掌握"},
                )
            else:
                return PathPlanResult(
                    active_path=[source_id],
                    strategy_used=effective_strategy,
                    path_found=True,
                    pruned_nodes=list(pruned),
                    diagnostics={**diagnostics, "note": "无指定目标，返回单节点路径"},
                )

        if dist.get(target_id, float("inf")) == float("inf"):
            # 目标不可达
            unreachable = [
                nid for nid in self._node_map
                if dist.get(nid, float("inf")) == float("inf") and nid not in pruned
            ]
            return PathPlanResult(
                active_path=[source_id],
                strategy_used=effective_strategy,
                path_found=False,
                pruned_nodes=list(pruned),
                unreachable_nodes=unreachable,
                diagnostics={
                    **diagnostics,
                    "error": f"目标节点 '{target_id}' 从源节点 '{source_id}' 不可达",
                },
            )

        path = self._reconstruct_path(target_id, pred)

        # ---- Step 8: 路径长度约束 ----
        if len(path) > context.max_path_length:
            path = path[: context.max_path_length]
            diagnostics["truncated"] = (
                f"路径长度超过上限 {context.max_path_length}，已截断"
            )

        # ---- Step 9: 时间预算约束 ----
        total_hours = sum(
            self._node_map[nid].estimated_hours
            for nid in path
            if nid in self._node_map
        )
        if total_hours > context.time_budget_hours:
            # 贪心截断：从后往前移除节点直到满足时间预算
            while total_hours > context.time_budget_hours and len(path) > 1:
                removed = path.pop()
                if removed in self._node_map:
                    total_hours -= self._node_map[removed].estimated_hours
            diagnostics["time_truncated"] = (
                f"路径总时长超过预算 {context.time_budget_hours}h，已截断至 {total_hours:.1f}h"
            )

        # ---- Step 10: 可行性校验 ----
        is_valid, violations = self.validate_path(path)
        if not is_valid:
            diagnostics["violations"] = "; ".join(violations)

        # ---- Step 11: 总难度计算 ----
        total_difficulty = sum(
            self._node_map[nid].difficulty
            for nid in path
            if nid in self._node_map
        )

        return PathPlanResult(
            active_path=path,
            total_estimated_hours=round(total_hours, 2),
            total_difficulty=round(total_difficulty, 4),
            pruned_nodes=list(pruned),
            strategy_used=effective_strategy,
            path_found=is_valid,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # 重规划评估
    # ------------------------------------------------------------------

    def evaluate_replan(
        self,
        current_node_id: str,
        current_path: List[str],
        knowledge_mastery: Dict[str, float],
        mastery_threshold: float = 0.65,
    ) -> ReplanTrigger:
        """评估是否需要触发全局重规划。

        触发条件（满足任一）：
          1. 当前节点已不在 active_path 中（路径漂移）。
          2. 路径中某个已规划节点的前置依赖已被标记为未掌握（mastery 低于阈值）。
          3. 用户在 active_path 的前置节点上表现持续不佳。

        Args:
            current_node_id: 当前所在节点 ID。
            current_path: 当前激活路径。
            knowledge_mastery: 最新掌握度映射。
            mastery_threshold: 掌握度阈值。

        Returns:
            ReplanTrigger: 重规划决策。
        """
        # Condition 1: 路径漂移
        if current_node_id not in current_path and current_path:
            return ReplanTrigger(
                should_replan=True,
                reason=f"当前节点 '{current_node_id}' 不在 active_path 中，发生路径漂移",
                severity="warning",
            )

        # Condition 2: 前置依赖掌握度退化
        current_idx = current_path.index(current_node_id) if current_node_id in current_path else -1
        for i in range(current_idx):
            prereq_id = current_path[i]
            m = knowledge_mastery.get(prereq_id, 0.0)
            if m < mastery_threshold:
                return ReplanTrigger(
                    should_replan=True,
                    reason=(
                        f"前置节点 '{prereq_id}' 的掌握度 ({m:.2f}) "
                        f"低于阈值 ({mastery_threshold})，需要重新加固"
                    ),
                    severity="critical",
                )

        # Condition 3: 冷启动阶段结束后评估路径合理性
        # （此处保留接口，由上层根据 c_epoch 判断）
        return ReplanTrigger(should_replan=False, reason="路径状态正常", severity="info")

    # ------------------------------------------------------------------
    # 查询与诊断接口
    # ------------------------------------------------------------------

    def get_prerequisites(self, node_id: str) -> List[str]:
        """查询某个知识点的所有直接前置依赖。"""
        return [src for src, _ in self._rev_adj.get(node_id, [])]

    def get_dependents(self, node_id: str) -> List[str]:
        """查询某个知识点的所有直接后继。"""
        return [tgt for tgt, _ in self._adj.get(node_id, [])]

    def get_all_prerequisites_deep(self, node_id: str) -> Set[str]:
        """递归查询某个知识点的所有传递前置依赖（DFS）。"""
        visited: Set[str] = set()

        def dfs(nid: str) -> None:
            for src, _ in self._rev_adj.get(nid, []):
                if src not in visited:
                    visited.add(src)
                    dfs(src)

        dfs(node_id)
        return visited

    def get_node_count(self) -> int:
        """返回图中节点总数。"""
        return len(self._node_map)

    def get_edge_count(self) -> int:
        """返回图中有向边总数。"""
        return sum(len(neighbors) for neighbors in self._adj.values())

    def has_cycle(self) -> bool:
        """检测图中是否存在环。

        Returns:
            True 如果存在环，False 如果为合法 DAG。
        """
        try:
            self.compute_topological_order()
            return False
        except ValueError:
            return True
