from __future__ import annotations

from src.resource_generation import context as context_module
from src.state.agent_state import AgentState


def test_generation_context_uses_default_retriever_when_runtime_has_no_override(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def default_retriever(*, query: str, top_k: int, course_id: str):
        calls.append({"query": query, "top_k": top_k, "course_id": course_id})
        return [{
            "id": "kb-queue-1",
            "type": "knowledge_base",
            "title": "Queue invariant",
            "excerpt": "A queue removes the earliest enqueued item.",
        }]

    monkeypatch.setattr(context_module, "_default_resource_knowledge_retriever", default_retriever)
    state = AgentState(user_id="context-user", course_id="course-a")

    context = context_module.build_resource_context(
        object(),
        state,
        "course-a",
        "N01",
        node_title="Queue invariants",
    )

    assert calls == [{"query": "Queue invariants", "top_k": 5, "course_id": "course-a"}]
    assert context.knowledge_refs == [{
        "id": "kb-queue-1",
        "type": "knowledge_base",
        "title": "Queue invariant",
        "uri": "",
        "excerpt": "A queue removes the earliest enqueued item.",
    }]


def test_cache_context_with_no_runtime_never_initializes_the_default_retriever(monkeypatch) -> None:
    def must_not_retrieve(**_kwargs):
        raise AssertionError("cache reads must not initialize or query Elasticsearch")

    monkeypatch.setattr(context_module, "_default_resource_knowledge_retriever", must_not_retrieve)
    state = AgentState(user_id="context-user", course_id="course-a")

    context = context_module.build_resource_context(
        None,
        state,
        "course-a",
        "N01",
        node_title="Queue invariants",
    )

    assert context.knowledge_refs
    assert all(ref["type"] == "course_graph" for ref in context.knowledge_refs)


def test_default_es_retriever_converts_hits_to_grounded_source_records(monkeypatch) -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def lexical_search(self, query: str, *, top_k: int):
            self.calls.append((query, top_k))
            return {
                "hits": {
                    "hits": [{
                        "_id": "fallback-id",
                        "_source": {
                            "chunk_id": "kb-avl-1",
                            "source_path": "kb/trees.md",
                            "knowledge_point": "AVL rotations",
                            "content": "A rotation restores local AVL balance.",
                        },
                    }],
                },
            }

    client = Client()
    monkeypatch.setattr(context_module, "_get_default_resource_kb_client", lambda: client)

    records = context_module._default_resource_knowledge_retriever(
        query="AVL rotation",
        top_k=5,
        course_id="course-a",
    )

    assert client.calls == [("AVL rotation", 5)]
    assert records == [{
        "chunk_id": "kb-avl-1",
        "source_path": "kb/trees.md",
        "knowledge_point": "AVL rotations",
        "content": "A rotation restores local AVL balance.",
        "id": "kb-avl-1",
        "type": "knowledge_base",
        "title": "AVL rotations",
        "uri": "kb/trees.md",
        "excerpt": "A rotation restores local AVL balance.",
        "metadata": {"retrieval_course_id": "course-a"},
    }]
