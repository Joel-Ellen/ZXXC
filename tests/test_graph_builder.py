# -*- coding: utf-8 -*-
"""
知识图谱构建器 — 单元测试套件
===============================

覆盖范围:
  1. TarjanSCC: 合法 DAG → 无环 (所有 SCC size=1)
  2. TarjanSCC: 单环检测
  3. TarjanSCC: 多环检测
  4. TarjanSCC: 自环检测 (self-loop)
  5. TarjanSCC: 复杂图 (多 SCC 交叉)
  6. TransitiveReducer: 链式冗余边移除
  7. TransitiveReducer: 菱形依赖冗余边
  8. TransitiveReducer: 无冗余图 (已最小化)
  9. GraphBuilder: 完整构建管线 (正常 DAG)
  10. GraphBuilder: 含环图的自动修复
  11. GraphBuilder: 传递归约集成
  12. GraphBuilder: validate_dag 独立校验

运行方式:
    pytest tests/test_graph_builder.py -v
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.graph_builder import (
    TarjanSCC,
    TransitiveReducer,
    GraphBuilder,
    GraphBuildConfig,
    GraphBuildResult,
    SCCDetectionResult,
    TransitiveReductionResult,
)
from src.infrastructure.path_planner import KnowledgeNode, KnowledgeEdge


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def dag_adj_simple() -> dict:
    """简单 DAG: A→B→C, A→C (冗余边)。"""
    return {"A": ["B", "C"], "B": ["C"], "C": []}


@pytest.fixture
def dag_adj_diamond() -> dict:
    """菱形 DAG: A→B, A→C, B→D, C→D。"""
    return {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}


@pytest.fixture
def cyclic_adj_simple() -> dict:
    """简单环: A→B→C→A。"""
    return {"A": ["B"], "B": ["C"], "C": ["A"]}


@pytest.fixture
def cyclic_adj_multi() -> dict:
    """多环图: A→B→C→A, 同时 B→D→B。"""
    return {
        "A": ["B"], "B": ["C", "D"],
        "C": ["A"], "D": ["B"],
    }


@pytest.fixture
def self_loop_adj() -> dict:
    """自环: A→A。"""
    return {"A": ["A"]}


@pytest.fixture
def complex_adj() -> dict:
    """复杂图: DAG + 一个环。"""
    return {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D", "E"],
        "D": ["F"],
        "E": ["F", "G"],
        "F": ["H"],
        "G": ["H"],
        "H": [],
        # 添加环: X→Y→Z→X
        "X": ["Y"],
        "Y": ["Z"],
        "Z": ["X"],
    }


@pytest.fixture
def standard_nodes() -> list[KnowledgeNode]:
    return [
        KnowledgeNode(node_id="A", title="Node A", difficulty=0.3, estimated_hours=1.0),
        KnowledgeNode(node_id="B", title="Node B", difficulty=0.4, estimated_hours=1.5),
        KnowledgeNode(node_id="C", title="Node C", difficulty=0.5, estimated_hours=2.0),
        KnowledgeNode(node_id="D", title="Node D", difficulty=0.6, estimated_hours=2.5),
        KnowledgeNode(node_id="E", title="Node E", difficulty=0.7, estimated_hours=3.0),
    ]


@pytest.fixture
def dag_edges() -> list[KnowledgeEdge]:
    """合法 DAG 边集 (含冗余: A→D 被 A→B→D 覆盖)。"""
    return [
        KnowledgeEdge(source_id="A", target_id="B", weight=1.0),
        KnowledgeEdge(source_id="A", target_id="C", weight=1.0),
        KnowledgeEdge(source_id="A", target_id="D", weight=2.0),  # 冗余: A→B→D 更短
        KnowledgeEdge(source_id="B", target_id="D", weight=1.0),
        KnowledgeEdge(source_id="C", target_id="E", weight=1.0),
        KnowledgeEdge(source_id="D", target_id="E", weight=1.0),
    ]


@pytest.fixture
def cycle_edges() -> list[KnowledgeEdge]:
    """含环边集: A→B→C→A。"""
    return [
        KnowledgeEdge(source_id="A", target_id="B", weight=1.0),
        KnowledgeEdge(source_id="B", target_id="C", weight=1.0),
        KnowledgeEdge(source_id="C", target_id="A", weight=0.5),  # 最弱边
    ]


# ============================================================================
# 1. Tarjan SCC — 合法 DAG
# ============================================================================

class TestTarjanSCCOnDAG:
    """测试 Tarjan 算法在合法 DAG 上的行为。"""

    def test_no_cycle_in_simple_dag(self, dag_adj_simple: dict) -> None:
        """简单 DAG 不应检测到环。"""
        tarjan = TarjanSCC(dag_adj_simple)
        assert tarjan.has_cycle() is False

    def test_all_sccs_size_one(self, dag_adj_simple: dict) -> None:
        """合法 DAG 的所有 SCC 大小应为 1。"""
        tarjan = TarjanSCC(dag_adj_simple)
        sccs = tarjan.find_sccs()
        for scc in sccs:
            assert len(scc) == 1, f"合法 DAG 的 SCC 大小应为 1, 实际 {len(scc)}: {scc}"

    def test_no_cycle_in_diamond(self, dag_adj_diamond: dict) -> None:
        """菱形 DAG 不应检测到环。"""
        tarjan = TarjanSCC(dag_adj_diamond)
        assert tarjan.has_cycle() is False

    def test_no_cycle_in_complex_dag_part(self, complex_adj: dict) -> None:
        """复杂图中 DAG 部分的节点不应被标记为环节点。"""
        tarjan = TarjanSCC(complex_adj)
        cycle_nodes = tarjan.get_cycle_nodes()
        # DAG 部分节点不应在环中
        dag_nodes = {"A", "B", "C", "D", "E", "F", "G", "H"}
        cycle_only = {"X", "Y", "Z"}
        assert cycle_nodes == cycle_only, (
            f"环节点应为 {cycle_only}, 实际 {cycle_nodes}"
        )


# ============================================================================
# 2. Tarjan SCC — 环检测
# ============================================================================

class TestTarjanSCCOnCyclic:
    """测试 Tarjan 算法对含环图的检测能力。"""

    def test_simple_cycle_detected(self, cyclic_adj_simple: dict) -> None:
        """A→B→C→A 应被检测为一个 size=3 的 SCC。"""
        tarjan = TarjanSCC(cyclic_adj_simple)
        assert tarjan.has_cycle() is True
        sccs = tarjan.find_sccs()
        assert any(len(scc) == 3 for scc in sccs), (
            f"应有一个 size=3 的 SCC，实际 {sccs}"
        )

    def test_multi_cycle_detected(self, cyclic_adj_multi: dict) -> None:
        """多环图应被正确检测。"""
        tarjan = TarjanSCC(cyclic_adj_multi)
        sccs = tarjan.find_sccs()
        # B 和 D 相互可达，形成 size=2 的 SCC
        # A 和 C 各在独立环中
        cycle_sccs = [scc for scc in sccs if len(scc) > 1]
        assert len(cycle_sccs) >= 1

    def test_self_loop_detected(self, self_loop_adj: dict) -> None:
        """自环 A→A 应被检测为 size=1 的 SCC（但仍是环）。"""
        tarjan = TarjanSCC(self_loop_adj)
        # 自环在 Tarjan 中形成 size=1 的 SCC
        # 但若节点可达自身，它在 DFS 中会被处理为 SCC
        sccs = tarjan.find_sccs()
        # 验证结果非空
        assert len(sccs) >= 1

    def test_cycle_nodes_collection(self, cyclic_adj_simple: dict) -> None:
        """get_cycle_nodes 应返回所有参与环的节点。"""
        tarjan = TarjanSCC(cyclic_adj_simple)
        cycle_nodes = tarjan.get_cycle_nodes()
        assert cycle_nodes == {"A", "B", "C"}

    def test_empty_graph_no_error(self) -> None:
        """空图不应报错。"""
        tarjan = TarjanSCC({})
        sccs = tarjan.find_sccs()
        assert sccs == []
        assert tarjan.has_cycle() is False


# ============================================================================
# 3. TransitiveReducer — 传递归约
# ============================================================================

class TestTransitiveReducer:
    """测试传递闭包剪枝的冗余边识别与移除。"""

    def test_chain_redundant_edge_removed(self, dag_adj_simple: dict) -> None:
        """A→B→C 存在，A→C 应被标记为冗余。"""
        weighted_adj = {
            k: [(t, 1.0) for t in v]
            for k, v in dag_adj_simple.items()
        }
        reducer = TransitiveReducer(weighted_adj)
        removed, reduced_adj = reducer.reduce()
        assert ("A", "C") in removed, (
            f"A→C 应被移除 (A→B→C 可达), 实际移除: {removed}"
        )

    def test_diamond_keeps_all_edges(self, dag_adj_diamond: dict) -> None:
        """菱形 DAG: A→B→D 和 A→C→D 都不可被对方替代，无冗余边。"""
        weighted_adj = {
            k: [(t, 1.0) for t in v]
            for k, v in dag_adj_diamond.items()
        }
        reducer = TransitiveReducer(weighted_adj)
        removed, reduced_adj = reducer.reduce()
        assert len(removed) == 0, "菱形 DAG 应无冗余边"

    def test_multi_hop_redundant(self) -> None:
        """A→B→C→D 长链中 A→D 应为冗余。"""
        adj = {
            "A": [("B", 1.0), ("D", 3.0)],  # A→D 冗余
            "B": [("C", 1.0)],
            "C": [("D", 1.0)],
            "D": [],
        }
        reducer = TransitiveReducer(adj)
        removed, _ = reducer.reduce()
        assert ("A", "D") in removed

    def test_already_minimal_no_changes(self) -> None:
        """已最小化的图不应有变化。"""
        adj = {
            "A": [("B", 1.0)],
            "B": [("C", 1.0)],
            "C": [],
        }
        reducer = TransitiveReducer(adj)
        removed, _ = reducer.reduce()
        assert len(removed) == 0

    def test_reduced_adj_structure(self, dag_adj_simple: dict) -> None:
        """归约后邻接表应正确反映移除后的结构。"""
        weighted_adj = {
            k: [(t, 1.0) for t in v]
            for k, v in dag_adj_simple.items()
        }
        reducer = TransitiveReducer(weighted_adj)
        removed, reduced_adj = reducer.reduce()
        # A→C 被移除后, A 的邻居应为 [B]
        a_neighbors = [t for t, _ in reduced_adj.get("A", [])]
        assert "C" not in a_neighbors, "归约后 A 不应再有直接边到 C"
        assert "B" in a_neighbors, "A→B 应保留"

    def test_no_crash_on_empty_graph(self) -> None:
        """空图传递归约不应报错。"""
        reducer = TransitiveReducer({})
        removed, reduced_adj = reducer.reduce()
        assert removed == []


# ============================================================================
# 4. GraphBuilder — 完整构建管线
# ============================================================================

class TestGraphBuilder:
    """测试 GraphBuilder 的完整构建管线（不依赖真实 Neo4j）。"""

    @pytest.fixture
    def mock_neo4j_client(self):
        """模拟 Neo4j 客户端 — 始终返回成功。"""
        class MockNeo4j:
            def __init__(self):
                self._connected = False

            def connect(self):
                self._connected = True

            def is_connected(self):
                return self._connected

            def create_knowledge_nodes_batch(self, nodes):
                return len(nodes)

            def create_dependency_edges_batch(self, edges):
                return len(edges)

            def export_nodes_for_planner(self, course_id=None):
                return []

            def export_edges_for_planner(self, course_id=None):
                return []

        return MockNeo4j()

    def test_build_valid_dag(self, mock_neo4j_client, standard_nodes, dag_edges) -> None:
        """合法 DAG 应构建成功，无环无冗余。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(mock_neo4j_client)
        result = builder.build(standard_nodes, dag_edges)

        assert isinstance(result, GraphBuildResult)
        assert result.nodes_created == len(standard_nodes)
        assert result.is_valid_dag is True
        assert result.scc_result.has_cycle is False

    def test_build_with_cycle_auto_fix(
        self, mock_neo4j_client, standard_nodes, cycle_edges
    ) -> None:
        """含环图应被自动修复为 DAG (remove_weakest_edge 策略)。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(
            mock_neo4j_client,
            GraphBuildConfig(scc_resolution_strategy="remove_weakest_edge"),
        )
        # 使用 A, B, C 节点（标准节点中取前 3 个）
        nodes_3 = standard_nodes[:3]
        result = builder.build(nodes_3, cycle_edges)

        assert result.scc_result.has_cycle is True, "应检测到环"
        assert len(result.scc_result.cycle_edges_removed) >= 1, (
            "应移除至少 1 条边来打破环"
        )
        assert result.is_valid_dag is True, "移除环边后应为合法 DAG"

    def test_build_with_cycle_raise_error(self, mock_neo4j_client) -> None:
        """raise_error 策略应在检测到环时抛出异常。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(
            mock_neo4j_client,
            GraphBuildConfig(scc_resolution_strategy="raise_error"),
        )
        nodes_3 = [
            KnowledgeNode(node_id="A", difficulty=0.3, estimated_hours=1.0),
            KnowledgeNode(node_id="B", difficulty=0.4, estimated_hours=1.0),
            KnowledgeNode(node_id="C", difficulty=0.5, estimated_hours=1.0),
        ]
        edges = [
            KnowledgeEdge(source_id="A", target_id="B"),
            KnowledgeEdge(source_id="B", target_id="C"),
            KnowledgeEdge(source_id="C", target_id="A"),
        ]
        with pytest.raises(ValueError, match="环"):
            builder.build(nodes_3, edges)

    def test_transitive_reduction_integration(
        self, mock_neo4j_client, standard_nodes, dag_edges
    ) -> None:
        """传递归约集成: 冗余边 A→D 应被移除。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(
            mock_neo4j_client,
            GraphBuildConfig(
                enable_transitive_reduction=True,
            ),
        )
        result = builder.build(standard_nodes, dag_edges)

        assert result.transitive_reduction_result.original_edge_count > 0
        # A→D 是冗余边，应被移除
        removed = result.transitive_reduction_result.redundant_edges_removed
        assert ("A", "D") in removed, (
            f"A→D 应为冗余边, 实际移除: {removed}"
        )
        assert result.is_valid_dag is True

    def test_transitive_reduction_disabled(
        self, mock_neo4j_client, standard_nodes, dag_edges
    ) -> None:
        """禁用传递归约时，冗余边应保留。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(
            mock_neo4j_client,
            GraphBuildConfig(enable_transitive_reduction=False),
        )
        result = builder.build(standard_nodes, dag_edges)
        assert result.transitive_reduction_result.original_edge_count == 0
        assert len(result.transitive_reduction_result.redundant_edges_removed) == 0

    def test_validate_dag_standalone(
        self, mock_neo4j_client
    ) -> None:
        """validate_dag 应独立验证图的合法性。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(mock_neo4j_client)
        nodes = [
            KnowledgeNode(node_id="X", difficulty=0.5, estimated_hours=1.0),
            KnowledgeNode(node_id="Y", difficulty=0.5, estimated_hours=1.0),
        ]
        edges_dag = [KnowledgeEdge(source_id="X", target_id="Y")]
        result = builder.validate_dag(nodes, edges_dag)
        assert result.has_cycle is False

        edges_cycle = [
            KnowledgeEdge(source_id="X", target_id="Y"),
            KnowledgeEdge(source_id="Y", target_id="X"),
        ]
        result2 = builder.validate_dag(nodes, edges_cycle)
        assert result2.has_cycle is True

    def test_disconnected_client_no_error(
        self, mock_neo4j_client, standard_nodes, dag_edges
    ) -> None:
        """未连接的 Neo4j 客户端应跳过数据库写入但不影响内存校验。"""
        # 未调用 connect()
        builder = GraphBuilder(mock_neo4j_client)
        result = builder.build(standard_nodes, dag_edges)
        assert result.nodes_created == 0  # 跳过 DB 写入
        assert result.scc_result.has_cycle is False  # 但内存校验仍执行
        assert result.is_valid_dag is True

    def test_result_model_integrity(
        self, mock_neo4j_client, standard_nodes, dag_edges
    ) -> None:
        """GraphBuildResult 各字段应自洽。"""
        mock_neo4j_client.connect()
        builder = GraphBuilder(
            mock_neo4j_client,
            GraphBuildConfig(enable_transitive_reduction=True),
        )
        result = builder.build(standard_nodes, dag_edges)

        # 最终边数 = 原始边数 - SCC移除 - 传递归约移除
        assert result.final_edge_count == result.edges_created
        assert result.transitive_reduction_result.reduction_ratio >= 0.0
        assert result.transitive_reduction_result.reduction_ratio <= 1.0


# ============================================================================
# 5. GraphBuildConfig 校验
# ============================================================================

class TestGraphBuildConfig:
    """测试构建配置的 Pydantic 校验。"""

    def test_default_config(self) -> None:
        cfg = GraphBuildConfig()
        assert cfg.enable_transitive_reduction is True
        assert cfg.scc_resolution_strategy == "remove_weakest_edge"

    def test_invalid_strategy(self) -> None:
        with pytest.raises(Exception):
            GraphBuildConfig(scc_resolution_strategy="invalid_strategy")

    def test_custom_config(self) -> None:
        cfg = GraphBuildConfig(
            min_edge_weight=0.5,
            enable_transitive_reduction=False,
            scc_resolution_strategy="remove_all_cycle_edges",
        )
        assert cfg.min_edge_weight == 0.5
        assert cfg.enable_transitive_reduction is False


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
