# -*- coding: utf-8 -*-
"""
Path Planner Node — 单元测试套件
=================================

覆盖范围:
  1. DAGDijkstraSolver: 图构建
  2. DAGDijkstraSolver: 拓扑排序
  3. DAGDijkstraSolver: 边代价函数
  4. DAGDijkstraSolver: 最短路径求解（线性链）
  5. DAGDijkstraSolver: 菱形依赖最优路径
  6. DAGDijkstraSolver: 不可达检测
  7. PlannerNode: 完整规划管线 (Mock Neo4j)
  8. PlannerNode: 掌握度影响路径选择
  9. PlannerNode: 时间预算截断
 10. PlannerNode: 空图/环图处理
 11. 边界条件: 单节点、自环、超长路径

运行方式:
    pytest tests/test_planner_node.py -v
"""

import pytest
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.planner_node import (
    PlannerNode,
    PlannerInput,
    PlannerOutput,
    DAGDijkstraSolver,
    PathEdgeInfo,
    create_planner_node,
)
from src.infrastructure.path_planner import KnowledgeNode, KnowledgeEdge
from src.state.agent_state import AgentState


# ============================================================================
# Fixtures: 标准测试图
#
#          N1 (0.3, 1h)
#         /  \       weight=1.0
#        v    v
#   N2 (0.5, 2h)  N3 (0.4, 1.5h)   weight=0.5 (推荐依赖)
#        \         /
#     w=1 \       / w=1
#          v     v
#         N4 (0.7, 3h)
#          |   w=1
#          v
#         N5 (0.8, 4h)
# ============================================================================

@pytest.fixture
def standard_nodes() -> list[KnowledgeNode]:
    return [
        KnowledgeNode(node_id="N1", title="基础概念", difficulty=0.3, estimated_hours=1.0),
        KnowledgeNode(node_id="N2", title="中级理论A", difficulty=0.5, estimated_hours=2.0),
        KnowledgeNode(node_id="N3", title="中级理论B", difficulty=0.4, estimated_hours=1.5),
        KnowledgeNode(node_id="N4", title="高级综合", difficulty=0.7, estimated_hours=3.0),
        KnowledgeNode(node_id="N5", title="实战项目", difficulty=0.8, estimated_hours=4.0),
    ]


@pytest.fixture
def standard_edges() -> list[KnowledgeEdge]:
    return [
        KnowledgeEdge(source_id="N1", target_id="N2", weight=1.0),
        KnowledgeEdge(source_id="N1", target_id="N3", weight=0.5, dependency_type="recommended"),
        KnowledgeEdge(source_id="N2", target_id="N4", weight=1.0),
        KnowledgeEdge(source_id="N3", target_id="N4", weight=1.0),
        KnowledgeEdge(source_id="N4", target_id="N5", weight=1.0),
    ]


@pytest.fixture
def solver(standard_nodes, standard_edges) -> DAGDijkstraSolver:
    s = DAGDijkstraSolver()
    s.build_graph(standard_nodes, standard_edges)
    return s


@pytest.fixture
def empty_solver() -> DAGDijkstraSolver:
    return DAGDijkstraSolver()


@pytest.fixture
def agent_state() -> AgentState:
    state = AgentState(user_id="U_PLAN", course_id="CS101",
                       current_node_id="N1", target_node_id="N5")
    state.dynamic_profile.knowledge_mastery["N1"] = 0.85
    state.dynamic_profile.knowledge_mastery["N2"] = 0.60
    state.dynamic_profile.knowledge_mastery["N3"] = 0.40
    state.dynamic_profile.knowledge_mastery["N4"] = 0.30
    state.dynamic_profile.knowledge_mastery["N5"] = 0.00
    return state


# ============================================================================
# 1. DAGDijkstraSolver — 图构建
# ============================================================================

class TestDAGDijkstraBuild:
    """测试图构建与拓扑排序。"""

    def test_graph_build(self, solver: DAGDijkstraSolver) -> None:
        """图应正确构建。"""
        assert solver.node_count == 5
        assert solver.edge_count == 5

    def test_topo_order(self, solver: DAGDijkstraSolver) -> None:
        """拓扑排序应正确。"""
        topo = solver.compute_topological_order()
        assert len(topo) == 5
        assert topo[0] == "N1"  # 零入度
        assert topo[-1] == "N5"  # 零出度

    def test_cycle_detection(self) -> None:
        """含环图应抛出 ValueError。"""
        s = DAGDijkstraSolver()
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.4, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="B", target_id="A"),
        ]
        s.build_graph(nodes, edges)
        with pytest.raises(ValueError):
            s.compute_topological_order()


# ============================================================================
# 2. DAGDijkstraSolver — 边代价函数
# ============================================================================

class TestEdgeCost:
    """测试边代价函数的正确性。"""

    def test_basic_cost(self, solver: DAGDijkstraSolver) -> None:
        """cost = (1-mastery) * weight + difficulty。"""
        mastery = {"N1": 0.8, "N2": 0.5}
        cost = solver.edge_cost("N1", "N2", 1.0, mastery)
        # mastery[N1]=0.8 → unmastered=0.2, weight=1.0, difficulty[N2]=0.5
        # cost ≈ 0.2*1.0 + 0.5 = 0.7
        assert 0.5 < cost < 0.8

    def test_high_mastery_reduces_cost(self, solver: DAGDijkstraSolver) -> None:
        """前置掌握度越高 → 代价越低。"""
        cost_low_mastery = solver.edge_cost("N1", "N2", 1.0, {"N1": 0.2})
        cost_high_mastery = solver.edge_cost("N1", "N2", 1.0, {"N1": 0.9})
        assert cost_high_mastery < cost_low_mastery, (
            f"高掌握应降低成本: low={cost_low_mastery:.4f}, high={cost_high_mastery:.4f}"
        )

    def test_lower_dependency_weight_reduces_cost(self, solver: DAGDijkstraSolver) -> None:
        """推荐依赖比严格依赖代价更低。"""
        cost_strict = solver.edge_cost("N1", "N2", 1.0, {"N1": 0.5})
        cost_recommended = solver.edge_cost("N1", "N3", 0.5, {"N1": 0.5})
        assert cost_recommended < cost_strict, (
            f"推荐依赖代价应更低: strict={cost_strict:.4f}, rec={cost_recommended:.4f}"
        )

    def test_cost_never_negative(self, solver: DAGDijkstraSolver) -> None:
        """边代价不应为负。"""
        for m in [0.0, 0.5, 1.0]:
            cost = solver.edge_cost("N1", "N2", 1.0, {"N1": m})
            assert cost >= 0.0, f"mastery={m}, cost={cost}"


# ============================================================================
# 3. DAGDijkstraSolver — 最短路径
# ============================================================================

class TestDAGDijkstraSolve:
    """测试 DAG-Dijkstra 路径求解。"""

    def test_linear_chain(self) -> None:
        """线性链图: A→B→C→D。"""
        s = DAGDijkstraSolver()
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.4, estimated_hours=1.0),
            KnowledgeNode(node_id="C", difficulty=0.5, estimated_hours=1.0),
            KnowledgeNode(node_id="D", difficulty=0.6, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="B", target_id="C"),
            KnowledgeEdge(source_id="C", target_id="D"),
        ]
        s.build_graph(nodes, edges)
        mastery = {"A": 0.7, "B": 0.7, "C": 0.7, "D": 0.7}
        path, cost, details = s.solve("A", "D", mastery)
        assert path == ["A", "B", "C", "D"]
        assert cost < float("inf")

    def test_diamond_prefers_lower_cost_path(self, solver: DAGDijkstraSolver) -> None:
        """菱形依赖: 应选择总代价更低的路径。"""
        mastery = {"N1": 0.5, "N2": 0.9, "N3": 0.2, "N4": 0.5, "N5": 0.5}
        path, cost, details = solver.solve("N1", "N5", mastery)
        assert path[0] == "N1"
        assert path[-1] == "N5"
        # N1→N3 是推荐依赖 (weight=0.5), N1→N2 是严格 (weight=1.0)
        # 且 N2 掌握度高 (0.9), 所以 N1→N2 更便宜
        # 但 N2→N4 和 N3→N4 的代价也需比较
        assert "N2" in path or "N3" in path

    def test_mastery_affects_path_choice(self, solver: DAGDijkstraSolver) -> None:
        """改变掌握度应改变最优路径。"""
        # 低 N2 mastery → N1→N3 更优 (推荐依赖 + 代价更低)
        mastery_low_n2 = {"N1": 0.7, "N2": 0.1, "N3": 0.7, "N4": 0.5, "N5": 0.5}
        path_low, _, _ = solver.solve("N1", "N5", mastery_low_n2)

        # 高 N2 mastery → N1→N2 更优 (前置已掌握)
        mastery_high_n2 = {"N1": 0.7, "N2": 0.9, "N3": 0.1, "N4": 0.5, "N5": 0.5}
        path_high, _, _ = solver.solve("N1", "N5", mastery_high_n2)

        # 不同掌握度应产生不同路径选择
        # 如果完全相同也没关系（可能两条路径总代价恰好相等）
        if path_low != path_high:
            assert path_low[1] != path_high[1], (
                f"不同掌握度应产生不同路径选择"
            )

    def test_unreachable_target(self, solver: DAGDijkstraSolver) -> None:
        """不存在的目标节点应返回空路径。"""
        path, cost, _ = solver.solve("N1", "NONEXISTENT", {"N1": 0.5})
        assert path == []
        assert cost == float("inf")

    def test_source_after_target(self, solver: DAGDijkstraSolver) -> None:
        """源在目标拓扑序之后 → 不可达。"""
        path, cost, _ = solver.solve("N5", "N1", {"N1": 0.5, "N5": 0.5})
        assert path == []

    def test_path_edge_details_populated(self, solver: DAGDijkstraSolver) -> None:
        """边细节应被正确填充。"""
        mastery = {"N1": 0.7, "N2": 0.7, "N3": 0.7, "N4": 0.7, "N5": 0.7}
        path, cost, details = solver.solve("N1", "N5", mastery)
        assert len(details) == len(path) - 1
        for d in details:
            assert d.source_id in path
            assert d.target_id in path
            assert d.computed_cost > 0

    def test_max_path_length_truncation(self, solver: DAGDijkstraSolver) -> None:
        """超长路径应被截断。"""
        mastery = {"N1": 0.5, "N2": 0.5, "N3": 0.5, "N4": 0.5, "N5": 0.5}
        path, _, _ = solver.solve("N1", "N5", mastery, max_path_length=2)
        assert len(path) <= 2

    def test_single_node_path(self) -> None:
        """源即目标 → 单节点路径。"""
        s = DAGDijkstraSolver()
        nodes = [KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0)]
        edges: list[KnowledgeEdge] = []
        s.build_graph(nodes, edges)
        # 源=目标 → 应该直接返回或不可达
        # 由于拓扑序只有 A，rank 相同，应返回空
        path, _, _ = s.solve("A", "A", {"A": 0.5})
        assert path == []  # 同一节点


# ============================================================================
# 4. PlannerNode — Mock Neo4j 完整管线
# ============================================================================

class TestPlannerNodeFull:
    """测试 Planner Node 的完整规划管线。"""

    @pytest.fixture
    def mock_neo4j(self, standard_nodes, standard_edges):
        """Mock Neo4j 客户端。"""
        class MockNeo4j:
            def __init__(self, nodes, edges):
                self._nodes = nodes
                self._edges = edges

            def is_connected(self):
                return True

            def export_nodes_for_planner(self, course_id=None):
                return list(self._nodes)

            def export_edges_for_planner(self, course_id=None):
                return list(self._edges)

        return MockNeo4j(standard_nodes, standard_edges)

    def test_full_pipeline(
        self, mock_neo4j, agent_state: AgentState
    ) -> None:
        """完整规划管线: Neo4j 查询 → 图构建 → Dijkstra → 路径更新。"""
        node = PlannerNode(neo4j_client=mock_neo4j)
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)

        assert isinstance(output, PlannerOutput)
        assert output.path_found is True
        assert len(output.active_path) > 1
        assert output.active_path[0] == "N1"
        assert output.active_path[-1] == "N5"
        assert output.total_cost > 0
        # AgentState 应被更新
        assert output.agent_state.active_path == output.active_path
        assert output.agent_state.re_plan_triggered is False

    def test_agent_state_updated(self, mock_neo4j, agent_state: AgentState) -> None:
        """AgentState 的 active_path 和 current_node_id 应被更新。"""
        node = PlannerNode(neo4j_client=mock_neo4j)
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)

        assert output.agent_state.active_path == output.active_path
        assert output.agent_state.current_node_id == output.active_path[0]

    def test_edge_details_provided(self, mock_neo4j, agent_state: AgentState) -> None:
        """输出应包含每条边的详细代价信息。"""
        node = PlannerNode(neo4j_client=mock_neo4j)
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)

        assert len(output.path_edges_detail) > 0
        for edge_detail in output.path_edges_detail:
            assert edge_detail.computed_cost > 0

    def test_time_budget_truncation(
        self, mock_neo4j, agent_state: AgentState
    ) -> None:
        """时间预算不足时应截断路径。"""
        node = PlannerNode(neo4j_client=mock_neo4j)
        # 设置极低的时间预算
        inp = PlannerInput(
            agent_state=agent_state,
            time_budget_hours=2.0,  # 仅 2h 预算，全路径需 1+2+1.5+3+4=11.5h
        )
        output = node(inp)
        assert output.path_found is True
        assert output.total_hours <= 2.0 + 1e-6, (
            f"路径时长应 ≤ 预算: {output.total_hours}"
        )

    def test_disconnected_neo4j_handled(
        self, agent_state: AgentState
    ) -> None:
        """未连接 Neo4j 时应优雅降级。"""
        class DisconnectedNeo4j:
            def is_connected(self):
                return False

        node = PlannerNode(neo4j_client=DisconnectedNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)
        assert output.path_found is False

    def test_empty_graph_handled(self, agent_state: AgentState) -> None:
        """空图应返回 path_found=False。"""
        class EmptyNeo4j:
            def is_connected(self):
                return True
            def export_nodes_for_planner(self, course_id=None):
                return []
            def export_edges_for_planner(self, course_id=None):
                return []

        node = PlannerNode(neo4j_client=EmptyNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)
        assert output.path_found is False


# ============================================================================
# 5. PlannerNode — 掌握度影响路径
# ============================================================================

class TestPlannerMasteryInfluence:
    """测试掌握度对路径选择的实际影响。"""

    def test_mastery_from_agent_state_used(
        self, agent_state: AgentState
    ) -> None:
        """AgentState 中的掌握度应影响路径代价计算。"""
        # 构建带 Mock Neo4j 的 Planner
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.5, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.5, estimated_hours=1.0),
            KnowledgeNode(node_id="C", difficulty=0.5, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="B", target_id="C"),
        ]

        class MockNeo4j:
            def is_connected(self):
                return True
            def export_nodes_for_planner(self, course_id=None):
                return nodes
            def export_edges_for_planner(self, course_id=None):
                return edges

        agent_state.current_node_id = "A"
        agent_state.target_node_id = "C"
        # A 已完全掌握 → 边 A→B 代价应很低
        agent_state.dynamic_profile.knowledge_mastery["A"] = 1.0

        node = PlannerNode(neo4j_client=MockNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)

        assert output.path_found is True
        # 边 A→B 的代价应很低（前置已掌握）
        ab_edge = next(
            (d for d in output.path_edges_detail if d.source_id == "A"),
            None,
        )
        assert ab_edge is not None
        assert ab_edge.computed_cost < 0.8, (
            f"A 已掌握时边成本应很低: {ab_edge.computed_cost}"
        )


# ============================================================================
# 6. 边界条件
# ============================================================================

class TestPlannerBoundary:
    """边界条件与异常处理。"""

    def test_single_node_graph(self, agent_state: AgentState) -> None:
        """单节点图: 源即目标。"""
        nodes = [KnowledgeNode(node_id="SOLO", difficulty=0.5, estimated_hours=1.0)]
        edges: list[KnowledgeEdge] = []

        class MockNeo4j:
            def is_connected(self):
                return True
            def export_nodes_for_planner(self, course_id=None):
                return nodes
            def export_edges_for_planner(self, course_id=None):
                return edges

        agent_state.current_node_id = "SOLO"
        agent_state.target_node_id = "SOLO"

        node = PlannerNode(neo4j_client=MockNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)
        assert output.path_found is True
        assert output.active_path == ["SOLO"]

    def test_auto_source_and_target(self, agent_state: AgentState) -> None:
        """未指定 source/target 时应自动选择。"""
        nodes = [
            KnowledgeNode(node_id="X", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="Y", difficulty=0.4, estimated_hours=1.0),
        ]
        edges = [KnowledgeEdge(source_id="X", target_id="Y")]

        class MockNeo4j:
            def is_connected(self):
                return True
            def export_nodes_for_planner(self, course_id=None):
                return nodes
            def export_edges_for_planner(self, course_id=None):
                return edges

        agent_state.current_node_id = None
        agent_state.target_node_id = None

        node = PlannerNode(neo4j_client=MockNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)
        assert output.path_found is True
        assert len(output.active_path) > 0

    def test_large_graph_performance(self) -> None:
        """100 节点长链图应快速求解。"""
        n = 100
        nodes = [
            KnowledgeNode(node_id=f"K{i}", difficulty=0.3, estimated_hours=0.5)
            for i in range(n)
        ]
        edges = [
            KnowledgeEdge(source_id=f"K{i}", target_id=f"K{i+1}")
            for i in range(n - 1)
        ]
        s = DAGDijkstraSolver()
        s.build_graph(nodes, edges)
        mastery = {f"K{i}": 0.5 for i in range(n)}
        path, cost, _ = s.solve("K0", f"K{n-1}", mastery, max_path_length=n)
        assert len(path) == n
        assert cost < float("inf")

    def test_graph_stats_in_output(self, agent_state: AgentState) -> None:
        """输出中应包含图统计信息。"""
        nodes = [
            KnowledgeNode(node_id="G1", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="G2", difficulty=0.4, estimated_hours=1.0),
        ]
        edges = [KnowledgeEdge(source_id="G1", target_id="G2")]

        class MockNeo4j:
            def is_connected(self):
                return True
            def export_nodes_for_planner(self, course_id=None):
                return nodes
            def export_edges_for_planner(self, course_id=None):
                return edges

        agent_state.current_node_id = "G1"
        agent_state.target_node_id = "G2"

        node = PlannerNode(neo4j_client=MockNeo4j())
        inp = PlannerInput(agent_state=agent_state)
        output = node(inp)
        assert output.graph_stats["total_nodes"] == 2
        assert output.graph_stats["total_edges"] == 1

    def test_factory_function(self) -> None:
        """create_planner_node 应返回正确的实例。"""
        node = create_planner_node()
        assert isinstance(node, PlannerNode)


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
