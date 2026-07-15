"""Context assembly for grounded, personalized resource generation."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from src.observability import observe_metric

from .schemas import CONTENT_VERSION


_DEFAULT_RESOURCE_KB_CLIENT: Any | None = None
_DEFAULT_RESOURCE_KB_INITIALIZED = False
_DEFAULT_RESOURCE_KB_DISABLED = False
_DEFAULT_RESOURCE_KB_LOCK = threading.Lock()


def _text(value: Any, default: str = "") -> str:
    value = str(value or "").strip()
    return value or default


def _node_record(node: Any) -> dict[str, Any]:
    return {
        "node_id": _text(getattr(node, "node_id", "")),
        "title": _text(getattr(node, "title", "")),
        "difficulty": getattr(node, "difficulty", None),
        "category": _text(getattr(node, "category", "")),
    }


def _mastery_bucket(value: float) -> str:
    if value < 0.35:
        return "foundational"
    if value < 0.65:
        return "developing"
    if value < 0.85:
        return "proficient"
    return "advanced"


def _as_source_ref(value: Any, fallback_id: str) -> dict[str, Any]:
    if isinstance(value, dict):
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        video_url = _text(
            value.get("video_url")
            or metadata.get("video_url")
            or (value.get("url") if _text(value.get("type")).lower() == "video" else ""),
        )
        video_source_id = _text(value.get("video_source_id") or metadata.get("video_source_id"))
        ref = {
            "id": _text(value.get("id") or value.get("chunk_id") or value.get("source_id"), fallback_id),
            "type": _text(value.get("type"), "knowledge_base"),
            "title": _text(value.get("title") or value.get("section") or value.get("knowledge_point"), fallback_id),
            "uri": _text(value.get("uri") or value.get("source_path")),
            "excerpt": _text(value.get("excerpt") or value.get("content"))[:1600],
        }
        if video_url:
            ref["video_url"] = video_url
        if video_source_id:
            ref["video_source_id"] = video_source_id
        return ref
    return {
        "id": fallback_id,
        "type": "knowledge_base",
        "title": fallback_id,
        "uri": "",
        "excerpt": _text(value)[:1600],
    }


def _call_retriever(retriever: Callable[..., Any], query: str, course_id: str) -> list[dict[str, Any]]:
    """Accept injected retrievers without coupling generation to a vendor SDK."""
    try:
        result = retriever(query=query, top_k=5, course_id=course_id)
    except TypeError:
        try:
            result = retriever(query, top_k=5, course_id=course_id)
        except TypeError:
            result = retriever(query)
    if isinstance(result, dict):
        result = result.get("results") or result.get("hits") or result.get("chunks") or []
    if not isinstance(result, Iterable) or isinstance(result, (str, bytes)):
        return []
    refs: list[dict[str, Any]] = []
    for index, value in enumerate(result):
        if isinstance(value, dict) and isinstance(value.get("_source"), dict):
            value = value["_source"]
        ref = _as_source_ref(value, f"kb-{index + 1}")
        if ref["excerpt"]:
            refs.append(ref)
        if len(refs) == 5:
            break
    return refs


def _resource_kb_is_enabled() -> bool:
    """Avoid creating a remote client unless the deployment configured ES."""
    enabled = str(os.environ.get("EDUAGENT_RESOURCE_KB_RETRIEVAL_ENABLED", "true")).strip().lower()
    return enabled not in {"0", "false", "off", "no"} and bool(str(os.environ.get("ES_HOSTS") or "").strip())


def _get_default_resource_kb_client() -> Any | None:
    """Lazily initialize the existing ES KB client for generation workers only."""
    global _DEFAULT_RESOURCE_KB_CLIENT, _DEFAULT_RESOURCE_KB_INITIALIZED
    if not _resource_kb_is_enabled() or _DEFAULT_RESOURCE_KB_DISABLED:
        return None
    with _DEFAULT_RESOURCE_KB_LOCK:
        if _DEFAULT_RESOURCE_KB_INITIALIZED:
            return _DEFAULT_RESOURCE_KB_CLIENT
        _DEFAULT_RESOURCE_KB_INITIALIZED = True
        try:
            from src.vector.elasticsearch_knowledge_base import (
                ElasticsearchKnowledgeBaseClient,
                ElasticsearchKnowledgeBaseConfig,
            )

            hosts = [
                host.strip()
                for host in str(os.environ.get("ES_HOSTS") or "").split(",")
                if host.strip()
            ]
            try:
                timeout_seconds = int(os.environ.get("EDUAGENT_RESOURCE_KB_TIMEOUT_SEC", "2"))
            except (TypeError, ValueError):
                timeout_seconds = 2
            config = ElasticsearchKnowledgeBaseConfig(
                hosts=hosts,
                index_name=str(
                    os.environ.get("EDUAGENT_RESOURCE_KB_INDEX")
                    or "eduagent_data_structure_kb"
                ),
                request_timeout=max(1, min(5, timeout_seconds)),
                verify_certs=False,
                basic_auth_user=os.environ.get("ES_USER") or None,
                basic_auth_password=os.environ.get("ES_PASSWORD") or None,
            )
            client = ElasticsearchKnowledgeBaseClient(config)
            client.connect()
            _DEFAULT_RESOURCE_KB_CLIENT = client
        except Exception:
            _DEFAULT_RESOURCE_KB_CLIENT = None
        return _DEFAULT_RESOURCE_KB_CLIENT


def _default_resource_knowledge_retriever(
    *,
    query: str,
    top_k: int = 5,
    course_id: str = "",
) -> list[dict[str, Any]]:
    """Map ES hits to the source-record shape consumed by ``ResourceContext``.

    This deliberately uses the client's lexical path: it is bounded, needs no
    local embedding model and leaves GET cache reads untouched because callers
    only select this retriever when a real runtime is present.
    """
    global _DEFAULT_RESOURCE_KB_DISABLED
    client = _get_default_resource_kb_client()
    if client is None:
        return []
    try:
        response = client.lexical_search(query, top_k=max(1, min(5, int(top_k))))
    except Exception:
        # Do not repeatedly spend a cold-start budget on an unavailable remote
        # service. Process restart or explicit runtime injection re-enables it.
        _DEFAULT_RESOURCE_KB_DISABLED = True
        return []

    records: list[dict[str, Any]] = []
    for hit in (response.get("hits", {}).get("hits", []) if isinstance(response, dict) else []):
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source")
        if not isinstance(source, dict):
            continue
        record = dict(source)
        record.setdefault("id", record.get("chunk_id") or hit.get("_id"))
        record.setdefault("type", "knowledge_base")
        record.setdefault("title", record.get("knowledge_point") or record.get("section") or record.get("title_path"))
        record.setdefault("uri", record.get("source_path"))
        record.setdefault("excerpt", record.get("content"))
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        if course_id:
            metadata = {**metadata, "retrieval_course_id": course_id}
            record["metadata"] = metadata
        if str(record.get("id") or "").strip() and str(record.get("excerpt") or "").strip():
            records.append(record)
        if len(records) >= max(1, min(5, int(top_k))):
            break
    return records


@dataclass(frozen=True)
class ResourceContext:
    user_id: str
    course_id: str
    node_id: str
    node_title: str
    capability_target: str
    prerequisite_nodes: list[dict[str, Any]] = field(default_factory=list)
    successor_nodes: list[dict[str, Any]] = field(default_factory=list)
    knowledge_refs: list[dict[str, Any]] = field(default_factory=list)
    mastery: float = 0.5
    mastery_bucket: str = "developing"
    error_signature: str = "none"
    cognitive_style: str = "textual"
    learning_stage: str = "practice"
    completed_resource_types: list[str] = field(default_factory=list)
    recent_diagnostic: dict[str, Any] = field(default_factory=dict)
    code_practice: dict[str, Any] = field(default_factory=dict)
    content_version: str = CONTENT_VERSION
    knowledge_index_version: str = "course-catalog-v1"
    locale: str = "zh-CN"

    @property
    def source_refs(self) -> list[dict[str, Any]]:
        refs = [dict(ref) for ref in self.knowledge_refs]
        refs.append(
            {
                "id": f"course:{self.course_id}:{self.node_id}",
                "type": "course_node",
                "course_id": self.course_id,
                "node_id": self.node_id,
                "title": self.node_title,
            }
        )
        return refs

    @property
    def grounding_ref_ids(self) -> list[str]:
        """Return server-supplied evidence IDs that can ground generated claims.

        The synthetic course-node record in :attr:`source_refs` is useful for
        semantic binding, but it is not a knowledge-base citation.  Keep the
        distinction explicit so a model cannot satisfy evidence requirements by
        citing only the node it was asked to explain.
        """
        return list(dict.fromkeys(
            str(ref.get("id") or "").strip()
            for ref in self.knowledge_refs
            if isinstance(ref, dict)
            and str(ref.get("id") or "").strip()
            and str(ref.get("type") or "").strip().lower() != "course_node"
        ))

    @property
    def personalization_cache_key(self) -> str:
        raw = "|".join(
            (
                self.mastery_bucket,
                self.error_signature,
                self.cognitive_style,
                self.content_version,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "course": self.course_id,
            "node": {"id": self.node_id, "title": self.node_title},
            "capability_target": self.capability_target,
            "prerequisites": self.prerequisite_nodes,
            "successors": self.successor_nodes,
            "knowledge_base": self.knowledge_refs,
            "learner": {
                "mastery": round(self.mastery, 3),
                "mastery_bucket": self.mastery_bucket,
                "recent_error_signature": self.error_signature,
                "cognitive_style": self.cognitive_style,
                "learning_stage": self.learning_stage,
                "completed_resource_types": self.completed_resource_types,
                "recent_diagnostic": self.recent_diagnostic,
            },
            "code_practice": self.code_practice,
            "content_version": self.content_version,
            "locale": self.locale,
        }


def build_resource_context(
    runtime: Any,
    state: Any,
    course_id: str,
    node_id: str,
    *,
    node_title: str = "",
    locale: str = "zh-CN",
    allow_remote_retrieval: bool = True,
) -> ResourceContext:
    """Build a bounded context from the course graph, state and KB adapter.

    A deployment can attach ``runtime.resource_knowledge_retriever``.  The
    default remains latency-safe: it uses local course graph source records so
    every card is grounded even when a remote KB is unavailable.
    """
    kg = getattr(runtime, "kg", None)
    nodes: list[Any] = []
    edges: list[Any] = []
    if kg is not None:
        try:
            nodes, edges = kg.get_local_graph(course_id)
        except Exception:
            try:
                nodes = kg.get_all_nodes(course_id)
                edges = kg.get_all_edges(course_id)
            except Exception:
                nodes, edges = [], []
    by_id = {_text(getattr(node, "node_id", "")): node for node in nodes}
    current = by_id.get(node_id)
    title = _text(node_title or getattr(current, "title", ""), node_id)
    prerequisites = [
        _node_record(by_id[edge.source_id])
        for edge in edges
        if _text(getattr(edge, "target_id", "")) == node_id and getattr(edge, "source_id", "") in by_id
    ]
    successors = [
        _node_record(by_id[edge.target_id])
        for edge in edges
        if _text(getattr(edge, "source_id", "")) == node_id and getattr(edge, "target_id", "") in by_id
    ]
    mastery_map = getattr(getattr(state, "dynamic_profile", None), "knowledge_mastery", {}) or {}
    try:
        mastery = float(mastery_map.get(node_id, 0.5))
    except (TypeError, ValueError):
        mastery = 0.5
    mastery = min(1.0, max(0.0, mastery))
    internal = getattr(state, "internal_state", {}) or {}
    recent_errors = internal.get("recent_error_signature") or internal.get("error_signature") or "none"
    if isinstance(recent_errors, (list, tuple)):
        recent_errors = ",".join(_text(item) for item in recent_errors[:3] if _text(item)) or "none"
    error_signature = _text(recent_errors, "none")[:240]
    cognitive_style = _text(getattr(state, "recommended_resource_style", ""), "textual")
    learning_stage = _text(getattr(state, "pedagogical_strategy", ""), "practice")
    completed = [
        _text(getattr(card, "card_type", ""))
        for card in (getattr(state, "generated_resources", {}) or {}).get(node_id, [])
        if _text(getattr(card, "card_type", ""))
    ]
    diagnostic = internal.get("last_diagnostic") or internal.get("diagnostic_result") or {}
    if not isinstance(diagnostic, dict):
        diagnostic = {"summary": _text(diagnostic)}
    try:
        from src.application.code_practice_service import problem_context_for_node

        code_practice = problem_context_for_node(node_id)
    except Exception:
        code_practice = {}

    # Building a job's idempotency key happens on the POST path.  Keep that
    # boundary local-only; the worker rebuilds this context with remote
    # retrieval enabled immediately before model generation.
    retriever = (
        getattr(runtime, "resource_knowledge_retriever", None)
        if allow_remote_retrieval and runtime is not None
        else None
    )
    if not callable(retriever) and allow_remote_retrieval and runtime is not None:
        retriever = _default_resource_knowledge_retriever
    knowledge_refs: list[dict[str, Any]] = []
    retrieval_source = "course_graph"
    retrieval_started = time.perf_counter()
    if callable(retriever):
        try:
            knowledge_refs = _call_retriever(retriever, title, course_id)
        except Exception:
            knowledge_refs = []
        if knowledge_refs:
            retrieval_source = "knowledge_base"
    if not knowledge_refs:
        graph_refs = [
            {
                "id": f"course:{course_id}:{node_id}",
                "type": "course_graph",
                "title": title,
                "excerpt": f"Course node {title}; target capability: {_text(getattr(current, 'category', ''), 'concept')}.",
            },
            *[
                {
                    "id": f"course:{course_id}:{record['node_id']}",
                    "type": "course_graph",
                    "title": record["title"],
                    "excerpt": f"Prerequisite for {title}: {record['title']}.",
                }
                for record in prerequisites[:2]
            ],
            *[
                {
                    "id": f"course:{course_id}:{record['node_id']}",
                    "type": "course_graph",
                    "title": record["title"],
                    "excerpt": f"Follow-on node after {title}: {record['title']}.",
                }
                for record in successors[:2]
            ],
        ]
        knowledge_refs = graph_refs[:5]
    observe_metric(
        "resource.generation.retrieval_ms",
        round((time.perf_counter() - retrieval_started) * 1000, 3),
        source=retrieval_source,
    )

    return ResourceContext(
        user_id=_text(getattr(state, "user_id", "")),
        course_id=course_id,
        node_id=node_id,
        node_title=title,
        capability_target=_text(getattr(current, "category", ""), "concept"),
        prerequisite_nodes=prerequisites[:5],
        successor_nodes=successors[:5],
        knowledge_refs=knowledge_refs[:5],
        mastery=mastery,
        mastery_bucket=_mastery_bucket(mastery),
        error_signature=error_signature,
        cognitive_style=cognitive_style,
        learning_stage=learning_stage,
        completed_resource_types=list(dict.fromkeys(completed)),
        recent_diagnostic=diagnostic,
        code_practice=code_practice if isinstance(code_practice, dict) else {},
        content_version=os.environ.get("EDUAGENT_RESOURCE_CONTENT_VERSION", CONTENT_VERSION),
        knowledge_index_version=os.environ.get("EDUAGENT_KNOWLEDGE_INDEX_VERSION", "course-catalog-v1"),
        locale=locale,
    )
