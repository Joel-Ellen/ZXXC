"""Context assembly for grounded, personalized resource generation."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from src.observability import incr_metric, observe_metric, set_metric

from .schemas import CONTENT_VERSION
from .services import sanitize_untrusted_evidence


_DEFAULT_RESOURCE_KB_CLIENT: Any | None = None
_DEFAULT_RESOURCE_KB_INITIALIZED = False
_DEFAULT_RESOURCE_KB_LOCK = threading.Lock()
_DEFAULT_RESOURCE_KB_FAILURES = 0
_DEFAULT_RESOURCE_KB_CIRCUIT_OPEN_UNTIL = 0.0

EVIDENCE_QUERY_KINDS = (
    "definition",
    "mechanism",
    "conditions",
    "examples",
    "boundaries",
    "misconceptions",
    "complexity_code",
    "video",
)
EVIDENCE_CANDIDATE_LIMIT = 20
EVIDENCE_SELECTED_MIN = 6
EVIDENCE_SELECTED_MAX = 10
EVIDENCE_TOKEN_LIMIT = 4_000


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
        for field_name in (
            "course_id",
            "node_ids",
            "content_kind",
            "locale",
            "content_version",
            "document_id",
            "section",
        ):
            if value.get(field_name) not in (None, "", []):
                ref[field_name] = value[field_name]
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


def _call_retriever(
    retriever: Callable[..., Any],
    query: str,
    course_id: str,
    *,
    top_k: int = 5,
    node_id: str = "",
    content_kind: str = "",
    locale: str = "",
) -> list[dict[str, Any]]:
    """Accept injected retrievers without coupling generation to a vendor SDK."""
    try:
        result = retriever(
            query=query,
            top_k=top_k,
            course_id=course_id,
            node_id=node_id,
            content_kind=content_kind,
            locale=locale,
        )
    except TypeError:
        try:
            result = retriever(query=query, top_k=top_k, course_id=course_id)
        except TypeError:
            try:
                result = retriever(query, top_k=top_k, course_id=course_id)
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
        if len(refs) == top_k:
            break
    return refs


def _evidence_queries(title: str, locale: str) -> list[tuple[str, str]]:
    if locale.lower().startswith("zh"):
        templates = {
            "definition": f"{title} 定义 核心概念",
            "mechanism": f"{title} 原理 机制 状态变化",
            "conditions": f"{title} 前提 条件 适用场景",
            "examples": f"{title} 示例 典型应用",
            "boundaries": f"{title} 边界情况 反例 限制",
            "misconceptions": f"{title} 常见误区 易错点",
            "complexity_code": f"{title} 复杂度 代码 实现",
            "video": f"{title} 可信视频 讲解",
        }
    else:
        templates = {
            "definition": f"{title} definition core concept",
            "mechanism": f"{title} mechanism state transition",
            "conditions": f"{title} preconditions applicability",
            "examples": f"{title} worked example application",
            "boundaries": f"{title} boundary counterexample limitation",
            "misconceptions": f"{title} misconception common error",
            "complexity_code": f"{title} complexity implementation code",
            "video": f"{title} trusted video lecture",
        }
    return [(kind, templates[kind]) for kind in EVIDENCE_QUERY_KINDS]


def _approx_tokens(text: str) -> int:
    # Conservative for mixed Chinese and code without adding a tokenizer to
    # the API process.
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def _normalized_excerpt(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold(), flags=re.UNICODE)


def _select_evidence(
    candidates: list[dict[str, Any]],
    *,
    course_id: str,
    node_id: str,
    strict_scope: bool,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_documents: set[tuple[str, str]] = set()
    seen_text: list[str] = []
    token_count = 0
    for candidate in candidates[:EVIDENCE_CANDIDATE_LIMIT]:
        candidate_course = _text(candidate.get("course_id"))
        candidate_nodes = candidate.get("node_ids")
        if isinstance(candidate_nodes, str):
            candidate_nodes = [candidate_nodes]
        candidate_nodes = {
            _text(value)
            for value in (candidate_nodes or [])
            if _text(value)
        }
        if strict_scope and (
            candidate_course != course_id
            or not candidate_nodes
            or node_id not in candidate_nodes
        ):
            if candidate_course and candidate_course != course_id:
                incr_metric(
                    "resource_cross_course_recall_total",
                    source="knowledge_base",
                )
            continue
        excerpt = _text(candidate.get("excerpt"))
        normalized = _normalized_excerpt(excerpt)
        if not normalized:
            continue
        document_key = (
            _text(candidate.get("document_id") or candidate.get("uri")),
            _text(candidate.get("section") or candidate.get("title")),
        )
        if document_key != ("", "") and document_key in seen_documents:
            continue
        if any(
            normalized in previous
            or previous in normalized
            or (
                min(len(normalized), len(previous)) >= 80
                and normalized[:80] == previous[:80]
            )
            for previous in seen_text
        ):
            continue
        tokens = _approx_tokens(excerpt)
        if token_count + tokens > EVIDENCE_TOKEN_LIMIT:
            continue
        selected.append(candidate)
        token_count += tokens
        seen_documents.add(document_key)
        seen_text.append(normalized)
        if len(selected) >= EVIDENCE_SELECTED_MAX:
            break
    return selected


def _build_evidence_pack(
    retriever: Callable[..., Any],
    *,
    title: str,
    course_id: str,
    node_id: str,
    locale: str,
    strict_scope: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for kind, query in _evidence_queries(title, locale):
        content_kind = "video" if kind == "video" else kind
        refs = _call_retriever(
            retriever,
            query,
            course_id,
            top_k=EVIDENCE_CANDIDATE_LIMIT,
            node_id=node_id,
            content_kind=content_kind,
            locale=locale,
        )
        for ref in refs:
            ref_id = _text(ref.get("id"))
            if not ref_id or ref_id in seen_ids:
                continue
            enriched = dict(ref)
            enriched["query_kind"] = kind
            candidates.append(enriched)
            seen_ids.add(ref_id)
            if len(candidates) >= EVIDENCE_CANDIDATE_LIMIT:
                break
        if len(candidates) >= EVIDENCE_CANDIDATE_LIMIT:
            break
    return _select_evidence(
        candidates,
        course_id=course_id,
        node_id=node_id,
        strict_scope=strict_scope,
    )


def _resource_kb_is_enabled() -> bool:
    """Avoid creating a remote client unless the deployment configured ES."""
    enabled = str(os.environ.get("EDUAGENT_RESOURCE_KB_RETRIEVAL_ENABLED", "true")).strip().lower()
    return enabled not in {"0", "false", "off", "no"} and bool(str(os.environ.get("ES_HOSTS") or "").strip())


def _get_default_resource_kb_client() -> Any | None:
    """Lazily initialize the existing ES KB client for generation workers only."""
    global _DEFAULT_RESOURCE_KB_CLIENT, _DEFAULT_RESOURCE_KB_INITIALIZED
    if not _resource_kb_is_enabled():
        return None
    if time.monotonic() < _DEFAULT_RESOURCE_KB_CIRCUIT_OPEN_UNTIL:
        set_metric(
            "resource_provider_circuit_open",
            1.0,
            provider="elasticsearch",
        )
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
            production = str(
                os.environ.get("APP_ENV")
                or os.environ.get("ENVIRONMENT")
                or ""
            ).strip().lower() in {"prod", "production"}
            if production and any(
                not host.lower().startswith("https://")
                for host in hosts
            ):
                raise RuntimeError(
                    "production resource KB requires TLS Elasticsearch hosts"
                )
            try:
                timeout_seconds = int(os.environ.get("EDUAGENT_RESOURCE_KB_TIMEOUT_SEC", "2"))
            except (TypeError, ValueError):
                timeout_seconds = 2
            verify_certs = str(
                os.environ.get("ES_VERIFY_CERTS") or "true"
            ).strip().lower() not in {"0", "false", "off", "no"}
            config = ElasticsearchKnowledgeBaseConfig(
                hosts=hosts,
                index_name=str(
                    os.environ.get("EDUAGENT_RESOURCE_KB_INDEX")
                    or "eduagent_data_structure_kb"
                ),
                request_timeout=max(1, min(5, timeout_seconds)),
                verify_certs=verify_certs,
                ca_certs=os.environ.get("ES_CA_CERTS") or None,
                basic_auth_user=os.environ.get("ES_USER") or None,
                basic_auth_password=os.environ.get("ES_PASSWORD") or None,
            )
            client = ElasticsearchKnowledgeBaseClient(config)
            client.connect()
            if str(os.environ.get("EMBEDDING_SERVICE_URL") or "").strip():
                from .services import EmbeddingServiceClient

                embedding_client = EmbeddingServiceClient()
                client.set_embedding_function(
                    lambda text: embedding_client.embed([text])[0],
                    lambda texts: embedding_client.embed(texts),
                )
            _DEFAULT_RESOURCE_KB_CLIENT = client
            set_metric(
                "resource_provider_circuit_open",
                0.0,
                provider="elasticsearch",
            )
        except Exception:
            _DEFAULT_RESOURCE_KB_CLIENT = None
        return _DEFAULT_RESOURCE_KB_CLIENT


def _default_resource_knowledge_retriever(
    *,
    query: str,
    top_k: int = 5,
    course_id: str = "",
    node_id: str = "",
    content_kind: str = "",
    locale: str = "",
) -> list[dict[str, Any]]:
    """Map ES hits to the source-record shape consumed by ``ResourceContext``.

    This deliberately uses the client's lexical path: it is bounded, needs no
    local embedding model and leaves GET cache reads untouched because callers
    only select this retriever when a real runtime is present.
    """
    global _DEFAULT_RESOURCE_KB_FAILURES, _DEFAULT_RESOURCE_KB_CIRCUIT_OPEN_UNTIL
    client = _get_default_resource_kb_client()
    if client is None:
        return []
    try:
        filters: dict[str, Any] = {}
        if course_id:
            filters["course_id"] = course_id
        if node_id:
            filters["node_ids"] = node_id
        if content_kind:
            filters["content_kind"] = content_kind
        if locale:
            filters["locale"] = locale
        try:
            response = client.hybrid_search(
                query,
                top_k=max(1, min(EVIDENCE_CANDIDATE_LIMIT, int(top_k))),
                filters=filters,
            )
        except (AttributeError, RuntimeError):
            try:
                response = client.lexical_search(
                    query,
                    top_k=max(1, min(EVIDENCE_CANDIDATE_LIMIT, int(top_k))),
                    filters=filters,
                )
            except TypeError:
                response = client.lexical_search(
                    query,
                    top_k=max(1, min(EVIDENCE_CANDIDATE_LIMIT, int(top_k))),
                )
        _DEFAULT_RESOURCE_KB_FAILURES = 0
        set_metric(
            "resource_provider_circuit_open",
            0.0,
            provider="elasticsearch",
        )
    except Exception:
        _DEFAULT_RESOURCE_KB_FAILURES += 1
        if _DEFAULT_RESOURCE_KB_FAILURES >= 3:
            _DEFAULT_RESOURCE_KB_CIRCUIT_OPEN_UNTIL = time.monotonic() + 30.0
            _DEFAULT_RESOURCE_KB_FAILURES = 0
            set_metric(
                "resource_provider_circuit_open",
                1.0,
                provider="elasticsearch",
            )
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
            record["metadata"] = {**metadata, "retrieval_course_id": course_id}
        if str(record.get("id") or "").strip() and str(record.get("excerpt") or "").strip():
            records.append(record)
        if len(records) >= max(1, min(EVIDENCE_CANDIDATE_LIMIT, int(top_k))):
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
    evidence_status: str = "grounded"
    evidence_issue: str = ""
    blueprint_snapshot: dict[str, Any] = field(default_factory=dict)

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
        safe_refs: list[dict[str, Any]] = []
        injection_detected = False
        for ref in self.knowledge_refs:
            safe_ref = dict(ref)
            safe_excerpt, detected = sanitize_untrusted_evidence(
                str(safe_ref.get("excerpt") or "")
            )
            safe_ref["excerpt"] = safe_excerpt
            injection_detected = injection_detected or detected
            safe_refs.append(safe_ref)
        if self.content_version.startswith("resource-v4"):
            learner_context = {
                "mastery_bucket": self.mastery_bucket,
                "error_tags": [
                    value.strip()
                    for value in self.error_signature.split(",")
                    if value.strip() and value.strip().lower() != "none"
                ][:5],
                "learning_stage": self.learning_stage,
            }
        else:
            learner_context = {
                "mastery": round(self.mastery, 3),
                "mastery_bucket": self.mastery_bucket,
                "recent_error_signature": self.error_signature,
                "cognitive_style": self.cognitive_style,
                "learning_stage": self.learning_stage,
                "completed_resource_types": self.completed_resource_types,
                "recent_diagnostic": self.recent_diagnostic,
            }
        return {
            "course": self.course_id,
            "node": {"id": self.node_id, "title": self.node_title},
            "capability_target": self.capability_target,
            "prerequisites": self.prerequisite_nodes,
            "successors": self.successor_nodes,
            "knowledge_base": {
                "trusted_as_instructions": False,
                "prompt_injection_detected": injection_detected,
                "sources": safe_refs,
            },
            "learner": learner_context,
            "code_practice": self.code_practice,
            "content_version": self.content_version,
            "locale": self.locale,
            "evidence_status": self.evidence_status,
            "evidence_issue": self.evidence_issue,
            "blueprint_snapshot": self.blueprint_snapshot,
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
    content_version: str = "",
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
    blueprint_snapshot: dict[str, Any] = {}
    for card in (getattr(state, "generated_resources", {}) or {}).get(node_id, []):
        if _text(getattr(card, "card_type", "")) != "concept_map":
            continue
        metadata = getattr(card, "metadata", {}) or {}
        structured = (
            metadata.get("structured_payload")
            if isinstance(metadata, dict)
            else None
        )
        candidate = (
            structured.get("learning_blueprint")
            if isinstance(structured, dict)
            else None
        )
        if isinstance(candidate, dict):
            blueprint_snapshot = dict(candidate)
            break
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
    evidence_status = "grounded"
    evidence_issue = ""
    retrieval_started = time.perf_counter()
    effective_content_version = (
        content_version
        or os.environ.get("EDUAGENT_RESOURCE_CONTENT_VERSION", CONTENT_VERSION)
    )
    strict_v4 = str(effective_content_version).startswith("resource-v4")
    if callable(retriever):
        try:
            if strict_v4:
                knowledge_refs = _build_evidence_pack(
                    retriever,
                    title=title,
                    course_id=course_id,
                    node_id=node_id,
                    locale=locale,
                    strict_scope=True,
                )
            else:
                knowledge_refs = _call_retriever(retriever, title, course_id)
        except Exception:
            knowledge_refs = []
        if knowledge_refs:
            retrieval_source = "knowledge_base"
            if strict_v4 and len(knowledge_refs) < EVIDENCE_SELECTED_MIN:
                evidence_status = "degraded"
                evidence_issue = "insufficient_scoped_evidence"
    if not knowledge_refs:
        graph_refs = [
            {
                "id": f"course:{course_id}:{node_id}",
                "type": "course_graph",
                "title": title,
                "excerpt": f"课程节点：{title}；能力目标：{_text(getattr(current, 'category', ''), 'concept')}。",
            },
            *[
                {
                    "id": f"course:{course_id}:{record['node_id']}",
                    "type": "course_graph",
                    "title": record["title"],
                    "excerpt": f"{title} 的前置知识：{record['title']}。",
                }
                for record in prerequisites[:2]
            ],
            *[
                {
                    "id": f"course:{course_id}:{record['node_id']}",
                    "type": "course_graph",
                    "title": record["title"],
                    "excerpt": f"{title} 的后继节点：{record['title']}。",
                }
                for record in successors[:2]
            ],
        ]
        knowledge_refs = graph_refs[:5]
        evidence_status = "degraded"
        evidence_issue = (
            "knowledge_base_unavailable"
            if strict_v4
            else "course_graph_fallback"
        )
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
        knowledge_refs=knowledge_refs[:EVIDENCE_SELECTED_MAX],
        mastery=mastery,
        mastery_bucket=_mastery_bucket(mastery),
        error_signature=error_signature,
        cognitive_style=cognitive_style,
        learning_stage=learning_stage,
        completed_resource_types=list(dict.fromkeys(completed)),
        recent_diagnostic=diagnostic,
        code_practice=code_practice if isinstance(code_practice, dict) else {},
        content_version=effective_content_version,
        knowledge_index_version=os.environ.get("EDUAGENT_KNOWLEDGE_INDEX_VERSION", "course-catalog-v1"),
        locale=locale,
        evidence_status=evidence_status,
        evidence_issue=evidence_issue,
        blueprint_snapshot=blueprint_snapshot,
    )
