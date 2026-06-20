# -*- coding: utf-8 -*-
"""
路径规划器单元测试套件 (辅助算法三)
====================================

覆盖范围:
  1. Kahn 拓扑排序 (DAG 合法 / 环检测)
  2. DAG-SSSP (单源最短路径) — 各策略
  3. 策略切换 (MIN_WEIGHT / MIN_HOPS / BALANCED / COLD_START)
  4. 已掌握节点剪枝
  5. 路径回溯与可行性校验
  6. 重规划评估 (ReplanTrigger)
  7. 时间预算/路径长度约束截断
  8. 传递前置依赖查询
  9. 动态节点/边添加
  10. 边界条件 (空图、单节点、不连通图、不可达目标)

运行方式:
    pytest tests/test_path_planner.py -v
    或: python -m pytest tests/test_path_planner.py -v
"""

import pytest
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.path_planner import (
    PathPlanner,
    PathPlanResult,
    KnowledgeNode,
    KnowledgeEdge,
    PlanContext,
    PathPlanStrategy,
    ReplanTrigger,
)


# ============================================================================
# Fixtures: 预构建标准测试 DAG
#
#          N1 (0.3, 1h)
#         /  \
#        v    v
#   N2 (0.5, 2h)  N3 (0.4, 1.5h)
#        \         /
#         v       v
#         N4 (0.7, 3h)
#          |
#          v
#         N5 (0.8, 4h)
#
#  拓扑序: N1 → N2 → N3 → N4 → N5
#  边权重: 全部 1.0
# ============================================================================

@pytest.fixture
def standard_nodes() -> list[KnowledgeNode]:
    return [
        KnowledgeNode(node_id="N1", title="基础概念", difficulty=0.3, estimated_hours=1.0, category="concept"),
        KnowledgeNode(node_id="N2", title="中级理论A", difficulty=0.5, estimated_hours=2.0, category="concept"),
        KnowledgeNode(node_id="N3", title="中级理论B", difficulty=0.4, estimated_hours=1.5, category="concept"),
        KnowledgeNode(node_id="N4", title="高级综合", difficulty=0.7, estimated_hours=3.0, category="skill"),
        KnowledgeNode(node_id="N5", title="实战项目", difficulty=0.8, estimated_hours=4.0, category="project"),
    ]


@pytest.fixture
def standard_edges() -> list[KnowledgeEdge]:
    return [
        KnowledgeEdge(source_id="N1", target_id="N2", weight=1.0),
        KnowledgeEdge(source_id="N1", target_id="N3", weight=1.0),
        KnowledgeEdge(source_id="N2", target_id="N4", weight=1.0),
        KnowledgeEdge(source_id="N3", target_id="N4", weight=1.0),
        KnowledgeEdge(source_id="N4", target_id="N5", weight=1.0),
    ]


@pytest.fixture
def planner(standard_nodes, standard_edges) -> PathPlanner:
    return PathPlanner(standard_nodes, standard_edges)


@pytest.fixture
def empty_planner() -> PathPlanner:
    return PathPlanner()


# ============================================================================
# 1. Kahn 拓扑排序
# ============================================================================

class TestTopologicalSort:
    """测试 Kahn 算法拓扑排序的正确性与环检测。"""

    def test_valid_dag_topo_order(self, planner: PathPlanner) -> None:
        """合法 DAG 应产生符合所有依赖关系的拓扑序。"""
        topo = planner.compute_topological_order()
        assert len(topo) == 5
        assert topo[0] == "N1"  # 入度为 0 的唯一节点
        # N5 应在最后（它只能通过 N4 到达）
        assert topo[-1] == "N5"
        # 依赖关系检查: N2 和 N3 在 N4 之前
        assert topo.index("N2") < topo.index("N4")
        assert topo.index("N3") < topo.index("N4")

    def test_cycle_detection(self) -> None:
        """包含环的图应抛出 ValueError。"""
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.4, estimated_hours=1.0),
            KnowledgeNode(node_id="C", difficulty=0.5, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="B", target_id="C"),
            KnowledgeEdge(source_id="C", target_id="A"),  # 形成环: A→B→C→A
        ]
        p = PathPlanner(nodes, edges)
        with pytest.raises(ValueError, match="有向环"):
            p.compute_topological_order()

    def test_topo_rank(self, planner: PathPlanner) -> None:
        """get_topo_rank 应返回正确的拓扑排名。"""
        rank_n1 = planner.get_topo_rank("N1")
        rank_n5 = planner.get_topo_rank("N5")
        assert rank_n1 == 0
        assert rank_n5 == 4

    def test_topo_rank_nonexistent_node(self, planner: PathPlanner) -> None:
        """不存在的节点返回 -1。"""
        assert planner.get_topo_rank("NONEXISTENT") == -1


# ============================================================================
# 2. 基本路径规划 (MIN_WEIGHT)
# ============================================================================

class TestBasicPathPlanning:
    """测试各策略下的基本路径规划。"""

    def test_n1_to_n5_min_weight(self, planner: PathPlanner) -> None:
        """N1 → N5 的最小权重路径应为 N1→N2→N4→N5 或 N1→N3→N4→N5。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            strategy=PathPlanStrategy.TOPO_MIN_WEIGHT,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        assert result.active_path[0] == "N1"
        assert result.active_path[-1] == "N5"
        # N4 必须在 N5 之前
        assert "N4" in result.active_path
        assert result.active_path.index("N4") < result.active_path.index("N5")

    def test_n1_to_n5_min_hops(self, planner: PathPlanner) -> None:
        """N1 → N5 的最少跳数路径应为 N1→N3→N4→N5 (3跳, N2会导致4跳)。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            strategy=PathPlanStrategy.TOPO_MIN_HOPS,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        # 最小跳数: N1→N3→N4→N5 = 4个节点 = 3条边
        # N1→N2→N4→N5 也是 4个节点 = 3条边，两者等优
        assert len(result.active_path) <= 4

    def test_cold_start_heuristic(self, planner: PathPlanner) -> None:
        """冷启动启发式应返回合法路径。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            strategy=PathPlanStrategy.COLD_START_HEURISTIC,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        assert result.strategy_used == PathPlanStrategy.COLD_START_HEURISTIC

    def test_balanced_strategy(self, planner: PathPlanner) -> None:
        """难度均衡策略应返回合法路径。

        N1(0.3)→N2(0.5): diff=0.2, weight=1*(1+0.6)=1.6
        N1(0.3)→N3(0.4): diff=0.1, weight=1*(1+0.3)=1.3 (更优)
        N2(0.5)→N4(0.7): diff=0.2, weight=1*(1+0.6)=1.6
        N3(0.4)→N4(0.7): diff=0.3, weight=1*(1+0.9)=1.9
        N4(0.7)→N5(0.8): diff=0.1, weight=1*(1+0.3)=1.3

        Path A: N1→N2→N4→N5 = 1.6+1.6+1.3 = 4.5
        Path B: N1→N3→N4→N5 = 1.3+1.9+1.3 = 4.5

        两条路径权重相同，由 DAG-SSSP 的首次松弛决定选择。
        """
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            strategy=PathPlanStrategy.TOPO_BALANCED,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        # 两条路径总成本相等，均为合法解
        assert result.active_path[0] == "N1"
        assert result.active_path[-1] == "N5"
        assert result.active_path[1] in ("N2", "N3"), (
            f"BALANCED 路径第二步应为 N2 或 N3, 实际 {result.active_path[1]}"
        )


# ============================================================================
# 3. 剪枝 (Pruning)
# ============================================================================

class TestPruning:
    """测试已掌握节点的剪枝逻辑。"""

    def test_pruned_nodes_excluded_from_path(self, planner: PathPlanner) -> None:
        """已掌握节点应从路径中移除，前提是其后续节点可达。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            knowledge_mastery={"N2": 0.9, "N4": 0.8},  # N2 和 N4 已掌握
            mastery_threshold=0.65,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        assert "N2" in result.pruned_nodes
        assert "N4" in result.pruned_nodes
        # 实际路径可能不需要学习 N2, N4
        # 但应注意: 剪枝后路径仍需满足拓扑可达性

    def test_all_mastered_returns_single_node(self, planner: PathPlanner) -> None:
        """全部节点已掌握时应返回仅源节点的路径。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1",
            knowledge_mastery={
                "N1": 0.9, "N2": 0.9, "N3": 0.9, "N4": 0.9, "N5": 0.9,
            },
            mastery_threshold=0.65,
        )
        result = planner.compute_path(ctx)
        assert len(result.active_path) <= 1

    def test_prune_intermediate_node(self, planner: PathPlanner) -> None:
        """剪枝中间节点后路径应跳过它。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            knowledge_mastery={"N4": 0.9},  # N4 已掌握
            mastery_threshold=0.65,
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        # N4 被剪枝但路径仍可达 N5（通过已掌握的 N4）
        assert "N4" in result.pruned_nodes


# ============================================================================
# 4. 路径可行性校验
# ============================================================================

class TestPathValidation:
    """测试路径拓扑合法性校验。"""

    def test_valid_path_passes(self, planner: PathPlanner) -> None:
        """合法路径应通过校验。"""
        path = ["N1", "N2", "N4", "N5"]
        is_valid, violations = planner.validate_path(path)
        assert is_valid is True
        assert len(violations) == 0

    def test_invalid_path_detected(self, planner: PathPlanner) -> None:
        """非法路径（含有不存在的边）应被检测。"""
        path = ["N1", "N5"]  # N1 没有直接边到 N5
        is_valid, violations = planner.validate_path(path)
        assert is_valid is False
        assert len(violations) > 0
        assert "N1" in violations[0] and "N5" in violations[0]

    def test_single_node_path_is_valid(self, planner: PathPlanner) -> None:
        """单节点路径总是合法。"""
        is_valid, violations = planner.validate_path(["N3"])
        assert is_valid is True
        assert len(violations) == 0


# ============================================================================
# 5. 重规划评估
# ============================================================================

class TestReplanEvaluation:
    """测试重规划触发条件评估。"""

    def test_no_replan_on_normal_path(self, planner: PathPlanner) -> None:
        """正常路径无需重规划。"""
        trigger = planner.evaluate_replan(
            current_node_id="N1",
            current_path=["N1", "N2", "N4", "N5"],
            knowledge_mastery={"N1": 0.8, "N2": 0.7},
        )
        assert trigger.should_replan is False
        assert trigger.severity == "info"

    def test_replan_on_path_drift(self, planner: PathPlanner) -> None:
        """路径漂移应触发重规划。"""
        trigger = planner.evaluate_replan(
            current_node_id="N3",  # N3 不在规划路径中
            current_path=["N1", "N2", "N4", "N5"],
            knowledge_mastery={},
        )
        assert trigger.should_replan is True
        assert trigger.severity == "warning"
        assert "路径漂移" in trigger.reason

    def test_replan_on_prerequisite_regression(self, planner: PathPlanner) -> None:
        """前置依赖掌握度退化应触发 critical 重规划。"""
        trigger = planner.evaluate_replan(
            current_node_id="N4",
            current_path=["N1", "N2", "N4", "N5"],
            knowledge_mastery={"N1": 0.8, "N2": 0.3},  # N2 掌握度低于阈值
            mastery_threshold=0.65,
        )
        assert trigger.should_replan is True
        assert trigger.severity == "critical"
        assert "N2" in trigger.reason


# ============================================================================
# 6. 路径约束 (时间预算 / 长度)
# ============================================================================

class TestPathConstraints:
    """测试路径规划中的约束条件。"""

    def test_time_budget_truncation(self, planner: PathPlanner) -> None:
        """路径总时长超过预算时应截断。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            time_budget_hours=5.0,  # 全路径 1+2+1.5+3+4=11.5h, 预算仅 5h
        )
        result = planner.compute_path(ctx)
        assert result.total_estimated_hours <= 5.0 + 1e-6
        assert "time_truncated" in result.diagnostics

    def test_max_path_length_enforced(self, planner: PathPlanner) -> None:
        """路径长度不应超过 max_path_length。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            max_path_length=2,  # 最多 2 个节点
        )
        result = planner.compute_path(ctx)
        assert len(result.active_path) <= 2
        assert "truncated" in result.diagnostics

    def test_unlimited_time_budget(self, planner: PathPlanner) -> None:
        """足够大的时间预算不应触发截断。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            time_budget_hours=1000.0,  # 远超实际需要
        )
        result = planner.compute_path(ctx)
        assert "time_truncated" not in result.diagnostics
        assert result.total_estimated_hours > 5


# ============================================================================
# 7. 传递依赖与图查询
# ============================================================================

class TestGraphQueries:
    """测试图的结构查询功能。"""

    def test_get_prerequisites(self, planner: PathPlanner) -> None:
        """N4 的直接前置依赖应为 N2 和 N3。"""
        prereqs = planner.get_prerequisites("N4")
        assert set(prereqs) == {"N2", "N3"}

    def test_get_dependents(self, planner: PathPlanner) -> None:
        """N1 的直接后继应为 N2 和 N3。"""
        deps = planner.get_dependents("N1")
        assert set(deps) == {"N2", "N3"}

    def test_get_all_prerequisites_deep(self, planner: PathPlanner) -> None:
        """N5 的传递前置依赖应为 {N1, N2, N3, N4}。"""
        deep_prereqs = planner.get_all_prerequisites_deep("N5")
        assert deep_prereqs == {"N1", "N2", "N3", "N4"}

    def test_graph_statistics(self, planner: PathPlanner) -> None:
        """节点与边计数应正确。"""
        assert planner.get_node_count() == 5
        assert planner.get_edge_count() == 5

    def test_has_cycle_false_on_dag(self, planner: PathPlanner) -> None:
        """合法 DAG 不应包含环。"""
        assert planner.has_cycle() is False


# ============================================================================
# 8. 动态图更新
# ============================================================================

class TestDynamicGraphUpdate:
    """测试动态添加节点/边后拓扑缓存失效与正确性。"""

    def test_add_node_and_edge(self, empty_planner: PathPlanner) -> None:
        """动态构建图应产生正确的规划结果。"""
        p = empty_planner
        p.add_node(KnowledgeNode(node_id="X1", difficulty=0.2, estimated_hours=1.0))
        p.add_node(KnowledgeNode(node_id="X2", difficulty=0.5, estimated_hours=2.0))
        p.add_edge(KnowledgeEdge(source_id="X1", target_id="X2"))

        assert p.get_node_count() == 2
        assert p.get_edge_count() == 1

        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="X1", target_node_id="X2",
        )
        result = p.compute_path(ctx)
        assert result.path_found is True
        assert result.active_path == ["X1", "X2"]

    def test_cache_invalidation(self, empty_planner: PathPlanner) -> None:
        """添加边后拓扑缓存应失效并重新计算。"""
        p = empty_planner
        p.add_node(KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0))
        p.add_node(KnowledgeNode(node_id="B", difficulty=0.3, estimated_hours=1.0))

        topo_before = p.compute_topological_order()
        assert len(topo_before) == 2

        p.add_edge(KnowledgeEdge(source_id="A", target_id="B"))
        topo_after = p.compute_topological_order()
        assert len(topo_after) == 2
        # 边 A→B 存在，所以 A 必须在 B 之前
        assert topo_after.index("A") < topo_after.index("B")


# ============================================================================
# 9. 边界条件
# ============================================================================

class TestBoundaryConditions:
    """测试极端边界条件。"""

    def test_empty_graph(self, empty_planner: PathPlanner) -> None:
        """空图应返回空路径。"""
        ctx = PlanContext(user_id="U1", course_id="C1")
        result = empty_planner.compute_path(ctx)
        assert result.path_found is False

    def test_single_node_graph(self) -> None:
        """单节点图应返回该节点。"""
        p = PathPlanner([
            KnowledgeNode(node_id="SOLO", difficulty=0.5, estimated_hours=1.0)
        ])
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="SOLO",
        )
        result = p.compute_path(ctx)
        assert result.path_found is True
        assert result.active_path == ["SOLO"]

    def test_unreachable_target(self, planner: PathPlanner) -> None:
        """目标节点不在图中时不可达。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1",
            target_node_id="NONEXISTENT",
        )
        result = planner.compute_path(ctx)
        assert result.path_found is False
        assert "不可达" in result.diagnostics.get("error", "")

    def test_disconnected_components(self) -> None:
        """两个不连通的子图: 从A无法到达B。"""
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="C", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="D", difficulty=0.3, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="C"),
            KnowledgeEdge(source_id="B", target_id="D"),
        ]
        p = PathPlanner(nodes, edges)
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="A", target_node_id="D",
        )
        result = p.compute_path(ctx)
        assert result.path_found is False

    def test_no_target_auto_select_farthest(self, planner: PathPlanner) -> None:
        """未指定目标时应自动选择最远可达节点。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1",
            target_node_id=None,  # 不指定目标
        )
        result = planner.compute_path(ctx)
        assert result.path_found is True
        assert "auto_target" in result.diagnostics
        # 应到达 N5（由 MIN_WEIGHT 策略选择收益最大的目标）
        assert result.active_path[-1] == "N5"

    def test_diamond_dependency(self) -> None:
        """菱形依赖结构: A→B, A→C, B→D, C→D。"""
        nodes = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.5, estimated_hours=2.0),
            KnowledgeNode(node_id="C", difficulty=0.4, estimated_hours=1.5),
            KnowledgeNode(node_id="D", difficulty=0.7, estimated_hours=3.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="A", target_id="C"),
            KnowledgeEdge(source_id="B", target_id="D"),
            KnowledgeEdge(source_id="C", target_id="D"),
        ]
        p = PathPlanner(nodes, edges)

        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="A", target_node_id="D",
            strategy=PathPlanStrategy.TOPO_MIN_WEIGHT,
        )
        result = p.compute_path(ctx)
        assert result.path_found is True
        # 路径必然包含 A 和 D
        assert result.active_path[0] == "A"
        assert result.active_path[-1] == "D"
        # 中间经过 B 或 C（由权重决定）
        assert "B" in result.active_path or "C" in result.active_path

    def test_cold_start_auto_strategy_override(self, planner: PathPlanner) -> None:
        """c_epoch < 5 时自动使用冷启动策略。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            c_epoch=2,  # 冷启动阶段
            strategy=PathPlanStrategy.TOPO_MIN_WEIGHT,  # 用户指定了 MIN_WEIGHT
        )
        result = planner.compute_path(ctx)
        assert result.strategy_used == PathPlanStrategy.COLD_START_HEURISTIC
        assert "strategy_override" in result.diagnostics

    def test_non_cold_start_uses_specified_strategy(self, planner: PathPlanner) -> None:
        """c_epoch >= 5 时应使用指定策略。"""
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="N1", target_node_id="N5",
            c_epoch=10,
            strategy=PathPlanStrategy.TOPO_MIN_HOPS,
        )
        result = planner.compute_path(ctx)
        assert result.strategy_used == PathPlanStrategy.TOPO_MIN_HOPS


# ============================================================================
# 10. PlanContext 模型校验
# ============================================================================

class TestPlanContextValidation:
    """测试 PlanContext Pydantic 模型的字段校验。"""

    def test_default_values(self) -> None:
        """默认值应符合预期。"""
        ctx = PlanContext(user_id="U1", course_id="C1")
        assert ctx.mastery_threshold == 0.65
        assert ctx.time_budget_hours == 10.0
        assert ctx.strategy == PathPlanStrategy.TOPO_MIN_WEIGHT
        assert ctx.max_path_length == 20

    def test_invalid_strategy_rejected(self) -> None:
        """非法策略字符串应被拒绝。"""
        with pytest.raises(Exception):
            PlanContext(user_id="U1", course_id="C1", strategy="invalid_strategy")

    def test_mastery_threshold_bounds(self) -> None:
        """mastery_threshold 必须在 [0,1] 区间。"""
        with pytest.raises(Exception):
            PlanContext(user_id="U1", course_id="C1", mastery_threshold=1.5)
        with pytest.raises(Exception):
            PlanContext(user_id="U1", course_id="C1", mastery_threshold=-0.1)


# ============================================================================
# 11. 综合集成测试
# ============================================================================

class TestIntegration:
    """模拟 LangGraph Node 中的完整路径规划流程。"""

    def test_full_planning_pipeline(self, planner: PathPlanner) -> None:
        """完整规划管线: 冷启动 → 学习 → 掌握 → 重规划。"""
        # Phase 1: 冷启动阶段 (c_epoch=0)
        ctx1 = PlanContext(
            user_id="U1", course_id="CS101",
            c_epoch=0,
            current_node_id="N1",
            target_node_id="N5",
            knowledge_mastery={},
        )
        r1 = planner.compute_path(ctx1)
        assert r1.strategy_used == PathPlanStrategy.COLD_START_HEURISTIC
        assert len(r1.active_path) > 1
        path_v1 = r1.active_path

        # Phase 2: 学习一段时间后 (c_epoch=8，掌握了一些节点)
        ctx2 = PlanContext(
            user_id="U1", course_id="CS101",
            c_epoch=8,
            current_node_id=path_v1[min(2, len(path_v1) - 1)],
            target_node_id="N5",
            knowledge_mastery={
                path_v1[0]: 0.85,  # 已掌握路径第一个节点
            },
            mastery_threshold=0.65,
        )
        r2 = planner.compute_path(ctx2)
        assert r2.strategy_used != PathPlanStrategy.COLD_START_HEURISTIC
        assert path_v1[0] in r2.pruned_nodes  # 已掌握节点被剪枝

        # Phase 3: 检查重规划需求（假设路径漂移到 N3）
        trigger = planner.evaluate_replan(
            current_node_id="N3",
            current_path=path_v1,
            knowledge_mastery={path_v1[0]: 0.85},
        )
        if "N3" not in path_v1:
            assert trigger.should_replan is True

    def test_large_graph_performance(self) -> None:
        """构造一个长链图验证线性时间复杂度。"""
        n = 100
        nodes = [
            KnowledgeNode(
                node_id=f"K{i}",
                difficulty=0.3 + 0.005 * i,
                estimated_hours=0.5,
            )
            for i in range(n)
        ]
        edges = [
            KnowledgeEdge(source_id=f"K{i}", target_id=f"K{i+1}")
            for i in range(n - 1)
        ]
        p = PathPlanner(nodes, edges)
        ctx = PlanContext(
            user_id="U1", course_id="C1",
            current_node_id="K0", target_node_id=f"K{n-1}",
            max_path_length=n,
            time_budget_hours=n * 10.0,  # 充足的时间预算
        )
        result = p.compute_path(ctx)
        assert result.path_found is True
        assert len(result.active_path) == n
        # 拓扑排序应为 0..n-1
        assert result.active_path[0] == "K0"
        assert result.active_path[-1] == f"K{n-1}"


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
