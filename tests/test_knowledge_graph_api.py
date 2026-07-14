import time

from starlette.testclient import TestClient

from frontend import server
from src.graph.knowledge_graph_manager import KnowledgeGraphManager


def test_local_graph_is_initialized_when_remote_backend_is_available(monkeypatch):
    monkeypatch.setattr(
        KnowledgeGraphManager,
        "_try_connect_neo4j",
        lambda self, uri, user, password: True,
    )
    manager = KnowledgeGraphManager()

    def unexpected_remote_call(*_args, **_kwargs):
        raise AssertionError("local graph lookup must not query Neo4j")

    monkeypatch.setattr(manager, "_export_nodes_from_neo4j", unexpected_remote_call)
    monkeypatch.setattr(manager, "_export_edges_from_neo4j", unexpected_remote_call)

    nodes, edges = manager.get_local_graph("data_structures")

    assert manager.is_neo4j_available is True
    assert nodes
    assert edges
    assert all(node.course_id == "data_structures" for node in nodes)
    assert all(edge.course_id == "data_structures" for edge in edges)


def test_knowledge_graph_endpoint_never_calls_slow_or_failing_remote_methods(
    monkeypatch,
):
    remote_calls = []

    def slow_remote_nodes(*_args, **_kwargs):
        remote_calls.append("nodes")
        time.sleep(1)
        return []

    def failing_remote_edges(*_args, **_kwargs):
        remote_calls.append("edges")
        raise RuntimeError("remote graph is unavailable")

    monkeypatch.setattr(server._kg, "_neo4j_available", True)
    monkeypatch.setattr(server._kg, "_export_nodes_from_neo4j", slow_remote_nodes)
    monkeypatch.setattr(server._kg, "_export_edges_from_neo4j", failing_remote_edges)

    response = TestClient(server.app).get(
        "/api/knowledge-graph",
        params={"course_id": "python_programming"},
    )

    assert response.status_code == 200
    assert remote_calls == []
    payload = response.json()
    assert set(payload) == {"nodes", "edges"}
    assert payload["nodes"]
    assert payload["edges"]
    assert set(payload["nodes"][0]) == {
        "id",
        "title",
        "difficulty",
        "estimated_hours",
        "category",
    }
    assert set(payload["edges"][0]) == {
        "source",
        "target",
        "dependency_type",
        "weight",
    }
