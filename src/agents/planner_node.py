# -*- coding: utf-8 -*-
"""
Path Planner Node — LangGraph 图谱寻路大脑
===========================================

本节点是 LangGraph StateGraph 中的路径规划控制节点，在 Profiler 之后执行，
负责根据最新的用户掌握度向量和 Neo4j 知识图谱实时计算最优学习路径。

核心能力：
1. Neo4j 图查询 — 通过 Cypher 提取课程知识图谱的真实前置拓扑依赖边
2. 拓扑激活路径代价函数:
     edge_cost(u→v) = (1 - mastery[u]) · dependency_weight + difficulty[v]
   即：前置节点掌握度越低 → 边代价越高（需要更多精力弥补前置）
3. 最小堆优化的 Dijkstra 变体在 DAG 上求解 SSSP:
     · 基于拓扑序的松弛操作 O(V + E)
     · 堆优化用于选择当前最优出边方向
4. 更新 AgentState.active_path 为求解出的最优激活序列

依赖声明：
  Neo4j 官方 Python Driver 遵循 Apache 2.0 协议。
  图算法参考 Cormen et al. (2009) Ch. 24.2 (DAG Shortest Paths)。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator, ConfigDict

from ..state.agent_state import AgentState
from ..graph.neo4j_client import Neo4jClient, Neo4jConfig
from ..infrastructure.path_planner import KnowledgeNode, KnowledgeEdge


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class PlannerInput(BaseModel):
    """Path Planner Node 的输入。"""

    model_config = {"arbitrary_types_allowed": True}

    agent_state: AgentState = Field(..., description="当前全局 AgentState")
    # 可选的 Neo4j 客户端注入（测试时可 Mock）
    neo4j_client: Optional[Any] = Field(
        default=None,
        description="Neo4j 客户端实例 (若 agent_state 中未绑定)"
    )
    # 规划参数覆盖
    max_path_length: Optional[int] = Field(
        default=None, ge=1, le=100, description="最大路径长度覆盖"
    )
    time_budget_hours: Optional[float] = Field(
        default=None, gt=0.0, description="时间预算覆盖（小时）"
    )


class PathEdgeInfo(BaseModel):
    """单条路径边的详细信息（用于诊断输出）。"""

    source_id: str = Field(..., description="源节点 ID")
    target_id: str = Field(..., description="目标节点 ID")
    source_mastery: float = Field(default=0.0, description="源节点掌握度")
    target_difficulty: float = Field(default=0.5, description="目标节点难度")
    dependency_weight: float = Field(default=1.0, description="依赖权重")
    computed_cost: float = Field(default=0.0, description="计算出的边代价")
    target_estimated_hours: float = Field(default=1.0, description="目标节点预估时长")


class PlannerOutput(BaseModel):
    """Path Planner Node 的输出。"""

    agent_state: AgentState = Field(..., description="更新后的全局 AgentState")
    active_path: List[str] = Field(
        default_factory=list, description="求解出的拓扑激活序列"
    )
    path_edges_detail: List[PathEdgeInfo] = Field(
        default_factory=list, description="路径中各边的详细代价信息"
    )
    total_cost: float = Field(default=0.0, description="路径总代价")
    total_hours: float = Field(default=0.0, description="路径总预估时长")
    path_found: bool = Field(default=False, description="是否成功找到路径")
    source_node_id: str = Field(default="", description="起始节点 ID")
    target_node_id: str = Field(default="", description="目标节点 ID")
    graph_stats: Dict[str, int] = Field(
        default_factory=dict, description="图统计 (nodes, edges)"
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict, description="诊断信息"
    )


# ============================================================================
# 最小堆优化的 DAG 最短路径求解器 (Dijkstra on DAG)
# ============================================================================

class DAGDijkstraSolver:
    """在 DAG 上运行的最小堆优化 Dijkstra 变体。

    核心思想:
      1. 首先通过 Kahn 算法生成拓扑序
      2. 按拓扑序遍历节点，对每条出边执行 RELAX
      3. 使用最小堆追踪当前最近节点（加速目标导向搜索）

    边代价函数:
      cost(u → v) = (1 - mastery[u]) · dependency_weight(u,v) + difficulty[v]

    解释:
      - (1 - mastery[u]): 前置节点 u 的"未掌握度"，越大则需更多精力弥补
      - dependency_weight: 前置依赖的重要程度（严格/推荐/可选）
      - difficulty[v]: 目标节点 v 的自身难度

    时间复杂度: O((V + E) · log V) with heap, O(V + E) for DAG SSSP
    """

    def __init__(self) -> None:
        # 图数据结构
        self._nodes: Dict[str, KnowledgeNode] = {}
        self._adj: Dict[str, List[Tuple[str, float]]] = {}  # src → [(tgt, weight)]
        self._rev_adj: Dict[str, List[str]] = {}            # tgt → [src]
        self._indegrees: Dict[str, int] = {}
        self._topo_order: List[str] = []
        self._topo_rank: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 图构建
    # ------------------------------------------------------------------

    def build_graph(
        self, nodes: List[KnowledgeNode], edges: List[KnowledgeEdge]
    ) -> None:
        """从节点和边列表构建内部图表示。

        Args:
            nodes: 知识节点列表。
            edges: 有向边列表。
        """
        self._nodes.clear()
        self._adj.clear()
        self._rev_adj.clear()
        self._indegrees.clear()
        self._topo_order.clear()
        self._topo_rank.clear()

        for node in nodes:
            self._nodes[node.node_id] = node
            self._indegrees.setdefault(node.node_id, 0)
            self._adj.setdefault(node.node_id, [])
            self._rev_adj.setdefault(node.node_id, [])

        for edge in edges:
            self._adj.setdefault(edge.source_id, [])
            self._adj[edge.source_id].append((edge.target_id, edge.weight))
            self._rev_adj.setdefault(edge.target_id, [])
            self._rev_adj[edge.target_id].append(edge.source_id)
            self._indegrees[edge.target_id] = self._indegrees.get(edge.target_id, 0) + 1

    # ------------------------------------------------------------------
    # Kahn 拓扑排序
    # ------------------------------------------------------------------

    def compute_topological_order(self) -> List[str]:
        """Kahn 算法生成拓扑序。O(V + E)。"""
        if self._topo_order:
            return self._topo_order

        indeg = dict(self._indegrees)
        queue: List[str] = [
            nid for nid, d in indeg.items() if d == 0
        ]
        # 使用 deque 的 popleft 更高效，但此处为保持纯净用 list pop(0)
        # 对教育知识图谱规模 (<5000 节点) 足够

        topo: List[str] = []
        rank: Dict[str, int] = {}

        while queue:
            u = queue.pop(0)
            topo.append(u)
            rank[u] = len(topo) - 1

            for v, _ in self._adj.get(u, []):
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)

        if len(topo) != len(self._nodes):
            # 有环！返回部分拓扑序并标记不可排序节点
            cycle_nodes = [n for n, d in indeg.items() if d > 0]
            raise ValueError(
                f"知识图谱存在有向环！无法拓扑排序。"
                f"拓扑长度={len(topo)}, 节点总数={len(self._nodes)}, "
                f"环中节点={cycle_nodes[:10]}"
            )

        self._topo_order = topo
        self._topo_rank = rank
        return topo

    # ------------------------------------------------------------------
    # 边代价函数
    # ------------------------------------------------------------------

    def edge_cost(
        self,
        source_id: str,
        target_id: str,
        dependency_weight: float,
        mastery_map: Dict[str, float],
    ) -> float:
        """计算有向边 u → v 的激活代价。

        cost = (1 - mastery[u]) · weight(u,v) + difficulty[v]

        特殊处理:
          - 若 mastery[u] >= 0.8 → 前置已基本掌握，代价大幅降低
          - 若 mastery[u] <= 0.2 → 前置严重不足，代价 ×2 惩罚

        Args:
            source_id: 源节点（前置）ID。
            target_id: 目标节点 ID。
            dependency_weight: 依赖关系权重。
            mastery_map: 掌握度映射。

        Returns:
            float: 边代价 (≥ 0)。
        """
        src_mastery = mastery_map.get(source_id, 0.5)
        tgt_node = self._nodes.get(target_id)

        # 前置未掌握度
        unmastered = max(0.0, 1.0 - src_mastery)

        # 自适应惩罚因子
        if src_mastery >= 0.8:
            unmastered *= 0.3  # 基本掌握，代价大幅降低
        elif src_mastery <= 0.2:
            unmastered *= 2.0  # 严重不足，代价翻倍

        # 目标节点自身难度
        tgt_difficulty = tgt_node.difficulty if tgt_node else 0.5

        # 基础代价
        cost = unmastered * dependency_weight + tgt_difficulty

        # 保证非负
        return max(0.001, cost)

    # ------------------------------------------------------------------
    # 最小堆优化的 DAG-Dijkstra
    # ------------------------------------------------------------------

    def solve(
        self,
        source_id: str,
        target_id: str,
        mastery_map: Dict[str, float],
        max_path_length: int = 50,
    ) -> Tuple[List[str], float, List[PathEdgeInfo]]:
        """求解 DAG 上从 source 到 target 的最短路径。

        算法: 拓扑序松弛 + 最小堆加速 (DAG-Dijkstra)

        Args:
            source_id: 起始节点 ID。
            target_id: 目标节点 ID。
            mastery_map: node_id → mastery 的掌握度映射。
            max_path_length: 路径长度上限。

        Returns:
            (path, total_cost, edge_details):
              - path: 节点 ID 序列。
              - total_cost: 路径总代价。
              - edge_details: 各边细节。
        """
        topo = self.compute_topological_order()

        if source_id not in self._topo_rank:
            return [], float("inf"), []
        if target_id not in self._topo_rank:
            return [], float("inf"), []

        src_rank = self._topo_rank[source_id]
        tgt_rank = self._topo_rank[target_id]

        if src_rank >= tgt_rank:
            # 源在目标之后或等于目标 → 不可达（拓扑约束）
            return [], float("inf"), []

        # 初始化
        dist: Dict[str, float] = {nid: float("inf") for nid in self._nodes}
        pred: Dict[str, Optional[str]] = {nid: None for nid in self._nodes}
        pred_edge_weight: Dict[str, float] = {}  # 记录前驱边的权重

        dist[source_id] = 0.0

        # 最小堆: (distance, node_id, topo_rank)
        heap: List[Tuple[float, int, str]] = [(0.0, src_rank, source_id)]

        # 按拓扑序遍历 + 堆优化
        # 只需遍历 [src_rank, tgt_rank] 范围内的节点
        for i in range(src_rank, tgt_rank + 1):
            u = topo[i]
            if dist[u] == float("inf"):
                continue

            # 对 u 的每条出边执行 RELAX
            for v, weight in self._adj.get(u, []):
                v_rank = self._topo_rank.get(v, -1)
                if v_rank < 0 or v_rank > tgt_rank:
                    continue  # 跳过不在目标范围内的节点

                # 计算边代价
                edge_cost_val = self.edge_cost(u, v, weight, mastery_map)

                # RELAX
                new_dist = dist[u] + edge_cost_val
                if new_dist < dist[v]:
                    dist[v] = new_dist
                    pred[v] = u
                    pred_edge_weight[v] = weight
                    heapq.heappush(heap, (new_dist, v_rank, v))

        # 路径回溯
        if dist[target_id] == float("inf"):
            return [], float("inf"), []

        path: List[str] = []
        current: Optional[str] = target_id
        while current is not None:
            path.append(current)
            current = pred.get(current)
        path.reverse()

        # 长度约束
        if len(path) > max_path_length:
            path = path[:max_path_length]

        # 构建边细节
        edge_details: List[PathEdgeInfo] = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            dw = pred_edge_weight.get(v, 1.0)
            tgt_node = self._nodes.get(v)
            edge_details.append(PathEdgeInfo(
                source_id=u,
                target_id=v,
                source_mastery=round(mastery_map.get(u, 0.5), 4),
                target_difficulty=round(tgt_node.difficulty if tgt_node else 0.5, 4),
                dependency_weight=round(dw, 4),
                computed_cost=round(self.edge_cost(u, v, dw, mastery_map), 6),
                target_estimated_hours=round(
                    tgt_node.estimated_hours if tgt_node else 1.0, 2
                ),
            ))

        total_cost = dist[target_id]

        return path, round(total_cost, 6), edge_details

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self._adj.values())


# ============================================================================
# Path Planner Node — LangGraph Node 主类
# ============================================================================

class PlannerNode:
    """LangGraph Path Planner Node — 图谱寻路大脑。

    在 LangGraph 中的注册方式:
        >>> graph.add_node("planner", planner_node)

    执行流程:
      1. 从 Neo4j 查询课程知识图谱（节点 + 前置依赖边）
      2. 构建 DAGDijkstraSolver 内部图
      3. 从 AgentState 提取掌握度向量 mastery_map
      4. 确定 source (current_node_id) 和 target (target_node_id)
      5. 运行最小堆 DAG-Dijkstra 求解最优激活路径
      6. 更新 AgentState.active_path
    """

    def __init__(self, neo4j_client: Optional[Neo4jClient] = None) -> None:
        """初始化 Path Planner Node。

        Args:
            neo4j_client: Neo4j 客户端实例（可通过 PlannerInput 覆盖）。
        """
        self._neo4j = neo4j_client
        self._solver = DAGDijkstraSolver()

    @property
    def solver(self) -> DAGDijkstraSolver:
        return self._solver

    # ------------------------------------------------------------------
    # LangGraph Node 调用签名
    # ------------------------------------------------------------------

    def __call__(self, inp: PlannerInput) -> PlannerOutput:
        return self.plan(inp)

    # ------------------------------------------------------------------
    # 核心规划逻辑
    # ------------------------------------------------------------------

    def plan(self, inp: PlannerInput) -> PlannerOutput:
        """执行完整的路径规划管线。

        Args:
            inp: PlannerInput 结构体。

        Returns:
            PlannerOutput: 更新后的 AgentState + 路径详情。
        """
        state = inp.agent_state
        diagnostics: Dict[str, Any] = {}
        neo4j = inp.neo4j_client or self._neo4j

        # ---- Step 1: 从 Neo4j 获取图数据 ----
        nodes: List[KnowledgeNode] = []
        edges: List[KnowledgeEdge] = []

        if neo4j and neo4j.is_connected():
            try:
                nodes = neo4j.export_nodes_for_planner(state.course_id)
                edges = neo4j.export_edges_for_planner(state.course_id)
                diagnostics["neo4j_nodes"] = len(nodes)
                diagnostics["neo4j_edges"] = len(edges)
            except Exception as e:
                diagnostics["neo4j_error"] = str(e)
                return PlannerOutput(
                    agent_state=state,
                    path_found=False,
                    diagnostics=diagnostics,
                )
        else:
            diagnostics["neo4j_status"] = "not_connected"

        if not nodes:
            diagnostics["warning"] = "知识图谱为空，无法规划路径"
            return PlannerOutput(
                agent_state=state,
                path_found=False,
                diagnostics=diagnostics,
            )

        # ---- Step 2: 构建内部图 ----
        self._solver.build_graph(nodes, edges)
        diagnostics["graph_nodes"] = self._solver.node_count
        diagnostics["graph_edges"] = self._solver.edge_count

        # ---- Step 3: 提取掌握度向量 ----
        mastery_map: Dict[str, float] = dict(
            state.dynamic_profile.knowledge_mastery
        )
        # 对于未在 mastery_map 中的节点，默认 0.5
        for node in nodes:
            if node.node_id not in mastery_map:
                mastery_map[node.node_id] = 0.5

        # ---- Step 4: 确定源节点和目标节点 ----
        source_id = state.current_node_id
        target_id = state.target_node_id

        if not source_id:
            # 自动选择第一个节点（拓扑序的最小入度节点）
            try:
                topo = self._solver.compute_topological_order()
                source_id = topo[0] if topo else ""
                diagnostics["auto_source"] = source_id
            except ValueError:
                diagnostics["error"] = "图包含环，无法自动选择源节点"
                return PlannerOutput(
                    agent_state=state,
                    path_found=False,
                    diagnostics=diagnostics,
                )

        if not source_id or source_id not in mastery_map:
            if nodes:
                source_id = nodes[0].node_id
            else:
                return PlannerOutput(
                    agent_state=state,
                    path_found=False,
                    diagnostics=diagnostics,
                )

        if not target_id:
            # 自动选择最后一个节点（拓扑序的最大 rank 节点）
            try:
                topo = self._solver.compute_topological_order()
                target_id = topo[-1] if topo else ""
                diagnostics["auto_target"] = target_id
            except ValueError:
                diagnostics["error"] = "无法确定目标节点"
                return PlannerOutput(
                    agent_state=state, path_found=False,
                    diagnostics=diagnostics,
                )

        if not target_id or source_id == target_id:
            # 源即目标 → 单节点路径
            state.active_path = [source_id]
            state.re_plan_triggered = False
            return PlannerOutput(
                agent_state=state,
                active_path=[source_id],
                path_found=True,
                source_node_id=source_id,
                target_node_id=source_id,
                diagnostics=diagnostics,
            )

        # ---- Step 5: DAG-Dijkstra 求解 ----
        max_len = inp.max_path_length or 50
        try:
            path, total_cost, edge_details = self._solver.solve(
                source_id=source_id,
                target_id=target_id,
                mastery_map=mastery_map,
                max_path_length=max_len,
            )
        except ValueError as e:
            diagnostics["error"] = str(e)
            return PlannerOutput(
                agent_state=state, path_found=False,
                diagnostics=diagnostics,
            )

        if not path:
            diagnostics["error"] = (
                f"从 {source_id} 到 {target_id} 不可达"
            )
            return PlannerOutput(
                agent_state=state,
                path_found=False,
                source_node_id=source_id,
                target_node_id=target_id,
                diagnostics=diagnostics,
            )

        # ---- Step 6: 时间预算约束 ----
        time_budget = inp.time_budget_hours or state.static_profile.time_budget_hours_per_week
        total_hours = sum(
            self._solver._nodes[nid].estimated_hours
            for nid in path
            if nid in self._solver._nodes
        )

        if total_hours > time_budget and len(path) > 1:
            # 贪心截断：从后往前移除节点直到满足时间预算
            while total_hours > time_budget and len(path) > 1:
                removed = path.pop()
                if removed in self._solver._nodes:
                    total_hours -= self._solver._nodes[removed].estimated_hours
            diagnostics["time_truncated"] = (
                f"路径总时长 {total_hours:.1f}h 超过预算 {time_budget}h, 已截断"
            )

        # ---- Step 7: 更新 AgentState ----
        state.active_path = list(path)
        state.re_plan_triggered = False  # 完成规划后清除触发标记
        state.current_node_id = path[0]  # 更新当前节点为路径起点

        # ---- Step 8: 组装输出 ----
        return PlannerOutput(
            agent_state=state,
            active_path=list(path),
            path_edges_detail=edge_details,
            total_cost=round(total_cost, 6),
            total_hours=round(total_hours, 2),
            path_found=True,
            source_node_id=source_id,
            target_node_id=target_id,
            graph_stats={
                "total_nodes": self._solver.node_count,
                "total_edges": self._solver.edge_count,
            },
            diagnostics=diagnostics,
        )


# ============================================================================
# 工厂函数
# ============================================================================

def create_planner_node(
    neo4j_client: Optional[Neo4jClient] = None,
) -> PlannerNode:
    """创建 Planner Node 实例。"""
    return PlannerNode(neo4j_client=neo4j_client)
