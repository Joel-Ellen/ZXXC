# -*- coding: utf-8 -*-
"""Resource lookup and regeneration for the current learning node."""

from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, Optional

from src.adapters.domain_to_response import resource_response
from src.adapters.state_to_domain import (
    public_resource_contract_dict,
    resource_contract_from_card,
)
from src.database.resource_generation_repo import (
    DEFAULT_LEASE_SECONDS,
    ResourceAdmissionError,
    ResourceGenerationRepo,
)
from src.observability import (
    bind_context,
    get_request_id,
    incr_metric,
    log_event,
    observe_metric,
    set_metric,
)
from src.orchestration_runtime import get_runtime
from src.resource_events import notifier as resource_event_notifier
from src.resource_generation import (
    CARD_TYPES,
    TEMPLATE_NOTICE,
    GeneratedResourcePayload,
    ResourceContext,
    ResourceGenerator,
    build_resource_context,
    validate_resource_payload,
)
from src.resource_generation.prompts import render_markdown
from src.resource_generation.policy import (
    BLUEPRINT_VERSION,
    BUNDLE_DEADLINE_SECONDS,
    CONCEPT_DEADLINE_SECONDS,
    MAX_GENERATION_CALLS,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    PIPELINE_VERSION,
    PROMPT_VERSION,
    QUALITY_VERSION,
    resource_v4_rollout,
)
from src.resource_generation.quality import evaluate_resource_quality
from src.resource_generation.services import content_hash
from src.state.agent_state import ResourceCard
from src.validation.c_syntax import is_c_learner_resource
from src.validation.language import (
    is_chinese_learning_content,
    non_chinese_resource_fields,
)
from src.validation.pipeline import get_validation_pipeline

from .code_practice_service import problem_binding_for_node
from ._common import (
    RESOURCE_CARD_ORDER,
    get_node_title,
    get_session,
    normalize_state_resources,
    persist_session,
    upsert_resource_card,
)


# 与生成器共用同一段模板回退提示，保证 startswith 前缀判断不会漂移。
_TEMPLATE_FALLBACK_NOTICE = TEMPLATE_NOTICE
_COURSE_BASE_CACHE_POLICY = "generic-context-v1"
_QUIZ_SHUFFLE_EPHEMERAL_KEY = secrets.token_bytes(32)


def _server_option_index(
    *,
    node_id: str,
    revision: int,
    item_index: int,
    item_id: str,
) -> int:
    configured_key = str(
        os.environ.get("EDUAGENT_QUIZ_SHUFFLE_SECRET") or ""
    ).encode("utf-8")
    shuffle_key = (
        configured_key
        if len(configured_key) >= 32
        else _QUIZ_SHUFFLE_EPHEMERAL_KEY
    )
    message = "|".join((
        str(node_id),
        str(revision),
        str(item_index),
        str(item_id),
    )).encode("utf-8")
    return int.from_bytes(
        hmac.new(shuffle_key, message, hashlib.sha256).digest()[:8],
        "big",
    ) % 4

_KNOWN_SEMANTIC_KEYWORDS: Dict[tuple[str, str], tuple[str, ...]] = {
    ("data_structures", "N01"): (
        "算法复杂度",
        "时间复杂度",
        "空间复杂度",
        "渐进复杂度",
        "Big O",
        "大 O",
    ),
}


def _call_supports_keyword(callable_obj: Any, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == keyword
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _canonical_node_binding(runtime: Any, course_id: str, node_id: str) -> Dict[str, Any]:
    """Resolve the node identity from the server catalog, never model output."""
    kg = getattr(runtime, "kg", None)
    canonical_node = None
    catalog_checked = False
    get_local_graph = getattr(kg, "get_local_graph", None)
    if callable(get_local_graph):
        try:
            nodes, _ = get_local_graph(course_id)
            catalog_checked = True
            canonical_node = next(
                (node for node in nodes if str(getattr(node, "node_id", "")) == node_id),
                None,
            )
        except Exception:
            canonical_node = None

    # A successful course-graph lookup is authoritative, including when the
    # requested node is absent. Falling back to a global node lookup in that
    # case could bind a same-named node from another course.
    if canonical_node is None and not catalog_checked:
        get_node_by_id = getattr(kg, "get_node_by_id", None)
        if callable(get_node_by_id):
            try:
                canonical_node = get_node_by_id(node_id, course_id)
                catalog_checked = True
            except TypeError:
                try:
                    canonical_node = get_node_by_id(node_id)
                    catalog_checked = True
                except Exception:
                    canonical_node = None
            except Exception:
                canonical_node = None

    title = str(getattr(canonical_node, "title", "") or "").strip()
    canonical_course_id = str(getattr(canonical_node, "course_id", "") or course_id).strip()
    belongs_to_course = (
        canonical_node is not None
        and canonical_course_id == str(course_id).strip()
    )
    if not title:
        get_title = getattr(kg, "get_node_title", None)
        if callable(get_title):
            try:
                title = str(get_title(node_id) or "").strip()
            except Exception:
                title = ""
    title = title or get_node_title(node_id, node_id) or node_id

    keywords = list(_KNOWN_SEMANTIC_KEYWORDS.get((course_id, node_id), ()))
    for part in re.split(r"(?:与|及其|及|和|、|：|:|/|\s+)", title):
        candidate = part.strip()
        if len(candidate) >= 3 and candidate not in keywords:
            keywords.append(candidate)

    return {
        "version": 1,
        "source": "server_course_catalog",
        "course_id": canonical_course_id or course_id,
        "node_id": node_id,
        "title": title,
        "keywords": keywords,
        "catalog_checked": catalog_checked,
        "exists": belongs_to_course,
    }


def _bound_template_content(binding: Dict[str, Any], card_type: str) -> str:
    """Return a deterministic template whose topic is the canonical node."""
    node_id = str(binding.get("node_id") or "")
    canonical_title = str(binding.get("title") or node_id)
    title = canonical_title
    if not is_chinese_learning_content(title, allow_name_only=True):
        localized = f"当前知识点（{node_id}）" if node_id else "当前知识点"
        title = localized if is_chinese_learning_content(localized) else "当前知识点"
    templates = {
        "concept_map": (
            f"## {title}\n\n"
            f"### 学习重点\n- 给出{title}的核心定义。\n"
            f"- 找出它的前提、约束和边界情况。\n"
            f"- 在节点 {node_id} 中用一个小例子应用该概念。"
        ),
        "code_snippet": (
            f"## {title}\n\n"
            f"```c\n#include <stddef.h>\n\n/* {title}（{node_id}）的练习脚手架 */\nint solve(const int *values, size_t count) {{\n    (void)values;\n    (void)count;\n    return 0;\n}}\n```"
        ),
        "interactive_exercise": (
            f"## {title}\n\n"
            f"先解释{title}的一条定义性质，再把它应用到一个小例子上。"
        ),
        "video_summary": (
            f"## {title}\n\n"
            f"依次复习{title}的定义、一个代表性示例和主要边界。"
        ),
        "diagnostic_quiz": (
            f"## {title}\n\n"
            f"1. 哪种说法最能概括{title}的定义性约束？"
        ),
    }
    return _TEMPLATE_FALLBACK_NOTICE + templates.get(card_type, templates["concept_map"])


def _with_semantic_binding(card: ResourceCard, binding: Dict[str, Any]) -> ResourceCard:
    metadata = dict(card.metadata or {})
    metadata["title"] = binding["title"]
    metadata["semantic_binding"] = dict(binding)
    source_refs = [
        ref
        for ref in metadata.get("source_refs", [])
        if isinstance(ref, dict) and ref.get("type") != "course_node"
    ]
    source_refs.append(
        {
            "type": "course_node",
            "course_id": binding["course_id"],
            "node_id": binding["node_id"],
            "title": binding["title"],
        }
    )
    metadata["source_refs"] = source_refs
    return card.model_copy(update={"metadata": metadata})


def _truthful_generated_content(content: str, generation: Dict[str, Any]) -> str:
    """Make an explicit template fallback visible even for extension runtimes."""
    normalized_content = str(content or "")
    source = str((generation or {}).get("source") or "unknown").strip().lower()
    if source == "template" and not normalized_content.lstrip().startswith(_TEMPLATE_FALLBACK_NOTICE):
        return _TEMPLATE_FALLBACK_NOTICE + normalized_content
    return normalized_content


def _resource_card_language_valid(card: ResourceCard, locale: str) -> bool:
    metadata = card.metadata if isinstance(card.metadata, dict) else {}
    canonical_payload = metadata.get("structured_payload")
    has_canonical_payload = isinstance(canonical_payload, dict)
    structured_payload = canonical_payload
    if not has_canonical_payload:
        try:
            projected = resource_contract_from_card(card).structured_payload
        except Exception:
            projected = {}
        structured_payload = projected if isinstance(projected, dict) else {}
    # Apply the same C/example fence contract used by state serialization.
    # Canonical code payloads additionally require an explicit C language.
    if not is_c_learner_resource(
        card.content,
        card_type=card.card_type,
        structured_payload=structured_payload,
        require_structured_language=has_canonical_payload,
    ):
        return False
    if not str(locale or "").lower().startswith("zh"):
        return True
    if not is_chinese_learning_content(card.content):
        return False
    return not non_chinese_resource_fields(structured_payload)


def _requested_card_types(card_type: Optional[str]) -> tuple[Optional[list[str]], Optional[str]]:
    if card_type is None or not str(card_type).strip():
        return list(RESOURCE_CARD_ORDER), None
    normalized = str(card_type).strip()
    if normalized not in RESOURCE_CARD_ORDER:
        return None, f"不支持的资源类型：{normalized}。"
    return [normalized], None


def _active_retest_resource_id(state: Any, node_id: str) -> str:
    """Return a diagnostic resource that an open review item must keep."""
    review_items = state.internal_state.get("review_items", [])
    if not isinstance(review_items, list):
        return ""
    for item in review_items:
        if not isinstance(item, dict):
            continue
        if (
            item.get("node_id") == node_id
            and item.get("status") == "in_progress"
            and item.get("phase") == "retest"
        ):
            resource_id = str(item.get("retest_resource_id") or "").strip()
            if resource_id:
                return resource_id
    return ""


def _diagnostic_quiz_metadata(
    node_id: str,
    title: str,
    content: str,
    revision: int = 1,
) -> Dict[str, Any]:
    """Build server-owned quiz answer keys for the diagnostic resource contract."""
    del content
    question_specs = (
        (
            "核心约束",
            f"能准确说明 {title} 的定义、前提和关键约束",
            "理解概念首先要能说明它成立的条件与不能省略的约束。",
        ),
        (
            "适用场景",
            f"能依据问题目标和输入条件判断何时使用 {title}",
            "适用场景应由问题目标和输入约束决定，而不是套用固定模板。",
        ),
        (
            "常见边界",
            f"会检查边界输入以及 {title} 的适用限制",
            "可靠应用必须覆盖边界输入，并明确该概念的适用限制。",
        ),
    )
    questions = []
    for index, (suffix, correct_option, explanation) in enumerate(question_specs, start=1):
        distractors = [
            f"{title} 与当前节点没有直接关系",
            f"{title} 只适用于唯一固定模板",
            "只要记住术语就可以忽略条件与边界",
        ]
        question_id = f"{node_id}-q{index}"
        correct_index = _server_option_index(
            node_id=node_id,
            revision=revision,
            item_index=index,
            item_id=question_id,
        )
        options = list(distractors)
        options.insert(correct_index, correct_option)
        questions.append(
            {
                "id": question_id,
                "prompt": f"关于 {title}，下列哪项最符合当前学习材料的 {suffix}？",
                "options": options,
                "answer_index": correct_index,
                "explanation": explanation,
                "skill_tag": suffix,
                "difficulty": "medium",
            }
        )
    return {
        "render_type": "diagnostic_quiz",
        "title": f"{title} 诊断测验",
        "questions": questions,
        "pass_threshold": 0.65,
        "after_quiz_guidance": "再次作答前，请回看概念讲解和练习中的条件、例子与边界。",
        "quiz_revision": revision,
    }


def _interactive_exercise_metadata(
    node_id: str,
    title: str,
    *,
    revision: int = 1,
) -> Dict[str, Any]:
    """Attach one server-graded checkpoint to the directed practice card.

    The adapter removes ``answer_index`` before returning the resource to the
    browser.  Keeping the key in the persisted card lets an ``answer_submitted``
    event prove that a learner attempted the exercise without treating that
    practice result as mastery evidence.
    """
    correct_option = (
        f"先说明 {title} 的成立条件，再用一个小例子验证关键约束和边界"
    )
    distractors = [
        f"只记住 {title} 的术语，不检查输入条件",
        "直接套用固定模板，并忽略不符合预期的边界输入",
        "先查看答案，再把结论原样复述为自己的推导",
    ]
    question_id = f"{node_id}-targeted-practice-q1-v{revision}"
    correct_index = _server_option_index(
        node_id=node_id,
        revision=revision,
        item_index=1,
        item_id=question_id,
    )
    options = list(distractors)
    options.insert(correct_index, correct_option)
    return {
        # The resource contract uses the card type as its render type.  This
        # is still a targeted-practice activity, but that belongs in a
        # separate semantic field rather than replacing the UI component type.
        "render_type": "interactive_exercise",
        "practice_mode": "targeted_practice",
        "practice_revision": revision,
        "questions": [
            {
                "id": question_id,
                "prompt": f"完成 {title} 的定向练习时，哪种做法能形成可复测的解题依据？",
                "options": options,
                "answer_index": correct_index,
                "explanation": (
                    "定向练习需要把概念条件落实到具体例子，并主动检查边界；"
                    "只记术语或套模板不能形成可靠证据。"
                ),
                "skill_tag": "targeted_practice",
            }
        ],
    }


def _refresh_unconsumed_diagnostic_metadata(
    state: Any,
    card: ResourceCard,
    binding: Dict[str, Any],
) -> ResourceCard:
    """Repair legacy quiz options without rewriting already-used evidence."""
    if card.card_type != "diagnostic_quiz":
        return card
    consumed = state.internal_state.get("consumed_completion_resource_ids", [])
    if isinstance(consumed, list) and card.resource_id in consumed:
        return card
    metadata = dict(card.metadata or {})
    try:
        revision = max(1, int(metadata.get("quiz_revision", 1)))
    except (TypeError, ValueError):
        revision = 1
    quiz_metadata = _diagnostic_quiz_metadata(
        str(binding["node_id"]),
        str(binding["title"]),
        card.content,
        revision=revision,
    )
    metadata.update(quiz_metadata)
    metadata["structured_payload"] = dict(quiz_metadata)
    return card.model_copy(update={"metadata": metadata})


def _refresh_interactive_exercise_metadata(
    card: ResourceCard,
    binding: Dict[str, Any],
) -> tuple[ResourceCard, bool]:
    """Repair persisted exercise cards that predate graded practice metadata."""
    if card.card_type != "interactive_exercise":
        return card, False
    metadata = dict(card.metadata or {})
    try:
        revision = max(1, int(metadata.get("practice_revision", 1)))
    except (TypeError, ValueError):
        revision = 1
    practice_metadata = _interactive_exercise_metadata(
        str(binding["node_id"]),
        str(binding["title"]),
        revision=revision,
    )
    existing_payload = metadata.get("structured_payload")
    payload = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    changed = any(metadata.get(key) != value for key, value in practice_metadata.items())
    changed = changed or any(payload.get(key) != value for key, value in practice_metadata.items())
    if not changed:
        return card, False
    metadata.update(practice_metadata)
    payload.update(practice_metadata)
    metadata["structured_payload"] = payload
    return card.model_copy(update={"metadata": metadata}), True


def _diagnostic_quiz_revision(existing: list[ResourceCard], force: bool) -> int:
    if not force:
        return 1
    current = next((card for card in existing if card.card_type == "diagnostic_quiz"), None)
    if current is None:
        return 1
    try:
        return max(1, int((current.metadata or {}).get("quiz_revision", 1))) + 1
    except (TypeError, ValueError):
        return 2


def _resource_metadata(
    *,
    binding: Dict[str, Any],
    node_id: str,
    card_type: str,
    content: str,
    quiz_revision: int,
    generation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach only learner-safe, server-owned metadata to generated cards."""
    metadata: Dict[str, Any]
    if card_type == "diagnostic_quiz":
        metadata = _diagnostic_quiz_metadata(
            node_id,
            str(binding["title"]),
            content,
            revision=quiz_revision,
        )
        metadata["structured_payload"] = dict(metadata)
    elif card_type == "interactive_exercise":
        metadata = _interactive_exercise_metadata(
            node_id,
            str(binding["title"]),
        )
        metadata["structured_payload"] = dict(metadata)
    elif card_type == "code_snippet":
        practice = problem_binding_for_node(node_id)
        metadata = {
            "practice": practice,
            # Flat aliases keep older resource consumers compatible while the
            # nested object carries the canonical versioned binding.
            "practice_problem_id": practice["problem_id"],
            "practice_version": practice["version"],
            "starter_code": practice["starter_code"],
        }
    else:
        metadata = {}
    metadata["title"] = binding["title"]
    metadata["semantic_binding"] = dict(binding)
    metadata["source_refs"] = [
        {
            "type": "course_node",
            "course_id": binding["course_id"],
            "node_id": binding["node_id"],
            "title": binding["title"],
        }
    ]
    if generation:
        metadata["generation"] = dict(generation)
    return metadata


def _generation_metadata(result: Any) -> tuple[str, Dict[str, Any]]:
    """Extract content and provenance without trusting an untyped runtime."""
    if isinstance(result, dict):
        content = str(result.get("content") or "")
        raw_metadata = result.get("generation")
        if isinstance(raw_metadata, dict):
            return content, dict(raw_metadata)
        return content, {"source": str(result.get("source") or "unknown")}

    content = str(getattr(result, "content", result) or "")
    to_metadata = getattr(result, "to_metadata", None)
    if callable(to_metadata):
        metadata = to_metadata()
        if isinstance(metadata, dict):
            return content, dict(metadata)

    metadata = {
        "source": str(getattr(result, "source", "unknown") or "unknown"),
    }
    for field_name in (
        "provider",
        "model",
        "attempt_count",
        "fallback_reason",
        "elapsed_ms",
        "input_tokens",
        "output_tokens",
    ):
        value = getattr(result, field_name, None)
        if value not in (None, ""):
            metadata[field_name] = value
    return content, metadata


def _generate_resource_results(
    runtime: Any,
    course_id: str,
    node_id: str,
    node_title: str,
    card_types: list[str],
    difficulty: float,
) -> Dict[str, tuple[str, Dict[str, Any]]]:
    """Prefer the bounded, provenance-aware runtime API when available."""
    batch_generator = getattr(runtime, "generate_resource_contents", None)
    if callable(batch_generator):
        kwargs: Dict[str, Any] = {}
        if _call_supports_keyword(batch_generator, "course_id"):
            kwargs["course_id"] = course_id
        if _call_supports_keyword(batch_generator, "node_title"):
            kwargs["node_title"] = node_title
        raw_results = batch_generator(node_id, card_types, difficulty, **kwargs)
        if isinstance(raw_results, dict):
            return {
                card_type: _generation_metadata(raw_results[card_type])
                for card_type in card_types
                if card_type in raw_results
            }

    result_generator = getattr(runtime, "generate_resource_content_result", None)
    if callable(result_generator):
        kwargs = {}
        if _call_supports_keyword(result_generator, "course_id"):
            kwargs["course_id"] = course_id
        if _call_supports_keyword(result_generator, "node_title"):
            kwargs["node_title"] = node_title
        return {
            card_type: _generation_metadata(
                result_generator(node_id, card_type, difficulty, **kwargs)
            )
            for card_type in card_types
        }

    # Test and extension runtimes may expose only the historical string API.
    # Preserve that compatibility, but never label an untraceable result as
    # model-generated.
    return {
        card_type: (
            str(runtime.generate_resource_content(node_id, card_type, difficulty) or ""),
            {"source": "unknown"},
        )
        for card_type in card_types
    }


def _resource_card(
    *,
    resource_id: str,
    binding: Dict[str, Any],
    card_type: str,
    content: str,
    difficulty: float,
    cognitive_style: str,
    quiz_revision: int,
    generation: Dict[str, Any],
) -> ResourceCard:
    return ResourceCard(
        resource_id=resource_id,
        node_id=str(binding["node_id"]),
        card_type=card_type,
        content=content,
        difficulty=difficulty,
        cognitive_style=cognitive_style,
        metadata=_resource_metadata(
            binding=binding,
            node_id=str(binding["node_id"]),
            card_type=card_type,
            content=content,
            quiz_revision=quiz_revision,
            generation=generation,
        ),
    )


def _record_resource_rejection(
    state: Any,
    node_id: str,
    card_type: str,
    validation: Any,
    *,
    stage: str,
) -> list[str]:
    issue_codes = [str(getattr(issue, "code", "")) for issue in validation.issues]
    incr_metric(
        "validation.reject_total",
        stage=stage,
        card_type=card_type,
        code=issue_codes[0] if issue_codes else "validation_failed",
    )
    state.record_error(
        f"resource_validation_rejected:{node_id}:{card_type}:"
        f"[{','.join(issue_codes)}]:"
        + ";".join(str(issue.message) for issue in validation.issues)
    )
    return issue_codes


def _is_template_generated(metadata: Any) -> bool:
    """Whether a card is a local template placeholder for a failed generation."""
    if not isinstance(metadata, dict):
        return False
    generation = metadata.get("generation")
    return isinstance(generation, dict) and generation.get("source") == "template"


def _fallback_generation(
    rejected_generation: Dict[str, Any],
    issue_codes: list[str],
) -> Dict[str, Any]:
    fallback_reason = (
        "semantic_binding_failed"
        if any(code.startswith("resource_semantic_") for code in issue_codes)
        else "resource_validation_failed"
    )
    return {
        "source": "template",
        "fallback_reason": fallback_reason,
        "rejected_source": str(rejected_generation.get("source") or "unknown"),
        "validation_issue_codes": issue_codes,
    }


def _attach_generation_summary(
    payload: Dict[str, Any],
    generation_by_type: Dict[str, Dict[str, Any]],
) -> None:
    if not generation_by_type:
        return
    template_fallback_count = sum(
        1
        for generation in generation_by_type.values()
        if generation.get("source") == "template"
    )
    sources = {
        str(generation.get("source") or "unknown")
        for generation in generation_by_type.values()
    }
    if template_fallback_count == len(generation_by_type):
        generation_status = "template_fallback"
    elif template_fallback_count:
        generation_status = "partial_fallback"
    elif sources == {"llm"}:
        generation_status = "llm_generated"
    else:
        generation_status = "generation_unknown"
    payload["generation"] = {
        "status": generation_status,
        "template_fallback_count": template_fallback_count,
        "resources": generation_by_type,
    }


def _legacy_generate_current_node_resources(
    user_id: str,
    course_id: str = "data_structures",
    node_id: Optional[str] = None,
    force: bool = False,
    include_legacy: bool = False,
    card_type: Optional[str] = None,
) -> Dict[str, Any]:
    from src.orchestration_runtime import get_runtime

    with bind_context(
        user_id=user_id,
        course_id=course_id,
        node_id=node_id or "",
        operation="generate_current_node_resources",
    ):
        started = time.perf_counter()
        session = get_session(user_id, course_id)
        state = session.agent_state
        target_node = node_id or state.current_node_id or (state.active_path[0] if state.active_path else None)
        if not target_node:
            return {"error": "缺少学习节点标识。", "status_code": 400}

        requested_types, card_type_error = _requested_card_types(card_type)
        if card_type_error:
            return {"error": card_type_error, "status_code": 400}

        active_retest_resource_id = _active_retest_resource_id(state, target_node)
        if force and active_retest_resource_id and "diagnostic_quiz" in (requested_types or []):
            if str(card_type or "").strip() == "diagnostic_quiz":
                return {
                    "status": "review_retest_active",
                    "error": "请先完成当前复习复测，再替换诊断测验。",
                    "status_code": 409,
                    "node_id": target_node,
                    "retest_resource_id": active_retest_resource_id,
                }
            # A general refresh may still update supporting material, but it
            # must not replace the only diagnostic card that can close the
            # active review item.
            requested_types = [
                resource_type
                for resource_type in requested_types or []
                if resource_type != "diagnostic_quiz"
            ]

        runtime = get_runtime()
        binding = _canonical_node_binding(runtime, course_id, target_node)
        validation_pipeline = get_validation_pipeline()
        difficulty = max(0.1, 1.0 - state.dynamic_profile.knowledge_mastery.get(target_node, 0.5))
        rejected_cards = 0
        generation_by_type: Dict[str, Dict[str, Any]] = {}
        existing = state.generated_resources.get(target_node, [])

        # Persisted cards predate the semantic binding contract. Revalidate
        # them before the already_exists fast path so a stale wrong-topic card
        # cannot remain visible indefinitely.
        if not force:
            audited_existing: list[ResourceCard] = []
            repaired_existing = False
            for existing_card in existing:
                if existing_card.card_type not in (requested_types or []):
                    audited_existing.append(existing_card)
                    continue
                bound_existing = _with_semantic_binding(existing_card, binding)
                bound_existing = _refresh_unconsumed_diagnostic_metadata(
                    state,
                    bound_existing,
                    binding,
                )
                bound_existing, practice_metadata_changed = _refresh_interactive_exercise_metadata(
                    bound_existing,
                    binding,
                )
                repaired_existing = repaired_existing or practice_metadata_changed
                validated_existing, validation = validation_pipeline.validate_resource_card(
                    bound_existing
                )
                if validated_existing is not None:
                    audited_existing.append(validated_existing)
                    continue

                repaired_existing = True
                rejected_cards += 1
                issue_codes = _record_resource_rejection(
                    state,
                    target_node,
                    existing_card.card_type,
                    validation,
                    stage="persisted_resource_output",
                )
                previous_generation = (
                    existing_card.metadata.get("generation", {})
                    if isinstance(existing_card.metadata, dict)
                    else {}
                )
                if not isinstance(previous_generation, dict):
                    previous_generation = {}
                fallback_generation = _fallback_generation(previous_generation, issue_codes)
                fallback_content = _bound_template_content(binding, existing_card.card_type)
                try:
                    quiz_revision = max(
                        1,
                        int((existing_card.metadata or {}).get("quiz_revision", 1)),
                    )
                except (TypeError, ValueError):
                    quiz_revision = 1
                fallback_card = _resource_card(
                    resource_id=existing_card.resource_id,
                    binding=binding,
                    card_type=existing_card.card_type,
                    content=fallback_content,
                    difficulty=existing_card.difficulty,
                    cognitive_style=existing_card.cognitive_style,
                    quiz_revision=quiz_revision,
                    generation=fallback_generation,
                )
                validated_fallback, fallback_validation = validation_pipeline.validate_resource_card(
                    fallback_card
                )
                if validated_fallback is not None:
                    audited_existing.append(validated_fallback)
                    generation_by_type[existing_card.card_type] = fallback_generation
                else:
                    _record_resource_rejection(
                        state,
                        target_node,
                        existing_card.card_type,
                        fallback_validation,
                        stage="resource_template_fallback",
                    )

            state.generated_resources[target_node] = audited_existing
            if repaired_existing:
                normalize_state_resources(state)
                persist_session(session)
            existing = state.generated_resources.get(target_node, [])

        # Template fallbacks are placeholders for a failed generation. Treat
        # them as missing so a later request retries with a fresh LLM budget
        # instead of pinning the degraded card until a force regeneration.
        existing_types = {
            card.card_type
            for card in existing
            if not _is_template_generated(card.metadata)
        }
        if not force and existing_types.issuperset(set(requested_types or [])):
            normalize_state_resources(state)
            resources = [
                resource_contract_from_card(card)
                for card in state.generated_resources.get(target_node, [])
                if card.card_type in (requested_types or [])
            ]
            response = resource_response(
                target_node,
                resources,
                status="repaired_fallback" if generation_by_type else "already_exists",
            )
            payload = (
                response.to_compatible_dict()
                if include_legacy
                else response.to_dto_dict()
            )
            _attach_generation_summary(payload, generation_by_type)
            return payload

        types_to_generate = [
            requested_card_type
            for requested_card_type in requested_types or []
            if force or requested_card_type not in existing_types
        ]
        generation_results = _generate_resource_results(
            runtime,
            course_id,
            target_node,
            str(binding["title"]),
            types_to_generate,
            difficulty,
        )
        for requested_card_type in requested_types or []:
            if not force and requested_card_type in existing_types:
                continue
            content, generation = generation_results.get(
                requested_card_type,
                ("", {"source": "unknown"}),
            )
            content = _truthful_generated_content(content, generation)
            quiz_revision = (
                _diagnostic_quiz_revision(existing, force)
                if requested_card_type == "diagnostic_quiz"
                else 1
            )
            resource_id = f"{target_node}_{requested_card_type}_supp"
            if requested_card_type == "diagnostic_quiz" and quiz_revision > 1:
                resource_id = f"{resource_id}_r{quiz_revision}"
            raw_card = _resource_card(
                resource_id=resource_id,
                binding=binding,
                card_type=requested_card_type,
                content=content,
                difficulty=difficulty,
                cognitive_style=state.recommended_resource_style or "textual",
                quiz_revision=quiz_revision,
                generation=generation,
            )
            validated_card, validation = validation_pipeline.validate_resource_card(raw_card)
            if validated_card is not None:
                upsert_resource_card(state, validated_card)
                generation_by_type[requested_card_type] = generation
            else:
                rejected_cards += 1
                issue_codes = _record_resource_rejection(
                    state,
                    target_node,
                    requested_card_type,
                    validation,
                    stage="resource_output",
                )
                fallback_generation = _fallback_generation(generation, issue_codes)
                fallback_content = _bound_template_content(binding, requested_card_type)
                fallback_card = _resource_card(
                    resource_id=resource_id,
                    binding=binding,
                    card_type=requested_card_type,
                    content=fallback_content,
                    difficulty=difficulty,
                    cognitive_style=state.recommended_resource_style or "textual",
                    quiz_revision=quiz_revision,
                    generation=fallback_generation,
                )
                validated_fallback, fallback_validation = validation_pipeline.validate_resource_card(
                    fallback_card
                )
                generation_by_type[requested_card_type] = fallback_generation
                if validated_fallback is not None:
                    upsert_resource_card(state, validated_fallback)
                else:
                    _record_resource_rejection(
                        state,
                        target_node,
                        requested_card_type,
                        fallback_validation,
                        stage="resource_template_fallback",
                    )

        normalize_state_resources(state)
        persist_session(session)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric("resource.generate.duration_ms", duration_ms)
        log_event(
            "resource.generate.complete",
            node_id=target_node,
            rejected_cards=rejected_cards,
            template_fallback_count=sum(
                1
                for generation in generation_by_type.values()
                if generation.get("source") == "template"
            ),
            force=force,
            card_type=card_type or "all",
            duration_ms=duration_ms,
        )

        resources = [
            resource_contract_from_card(card)
            for card in state.generated_resources.get(target_node, [])
            if card.card_type in (requested_types or [])
        ]
        response = resource_response(target_node, resources, status="generated")
        payload = response.to_compatible_dict() if include_legacy else response.to_dto_dict()
        _attach_generation_summary(payload, generation_by_type)
        if active_retest_resource_id:
            payload["preserved_retest_resource_id"] = active_retest_resource_id
        return payload


# The legacy implementation above remains as a rollback reference while the
# public entry points below are used by the HTTP API and background workers.
_RESOURCE_JOB_REPO: Optional[ResourceGenerationRepo] = None
_RESOURCE_JOB_REPO_LOCK = threading.Lock()
_RESOURCE_JOB_FUTURES: Dict[str, concurrent.futures.Future[Any]] = {}
_RESOURCE_JOB_FUTURES_LOCK = threading.Lock()
_RESOURCE_JOB_RETRY_TIMERS: Dict[str, threading.Timer] = {}
_RESOURCE_JOB_RETRY_TIMERS_LOCK = threading.Lock()
_RESOURCE_SESSION_LOCKS: Dict[tuple[str, str], threading.RLock] = {}
_RESOURCE_SESSION_LOCKS_LOCK = threading.Lock()


def _resource_job_worker_count() -> int:
    try:
        configured = int(os.environ.get("EDUAGENT_RESOURCE_JOB_WORKERS", "3"))
    except (TypeError, ValueError):
        configured = 3
    return max(1, min(8, configured))


def _resource_global_generation_max_concurrency() -> int:
    """Return the cross-process generation ceiling.

    Local executor workers only constrain one application instance.  Production
    deployments can set this independently when several instances share the
    PostgreSQL coordinator; retaining the old worker count as the default
    keeps a single-instance deployment behaviorally unchanged.
    """
    raw = os.environ.get(
        "EDUAGENT_RESOURCE_GLOBAL_MAX_CONCURRENCY",
        str(_RESOURCE_JOB_WORKER_COUNT),
    )
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = _RESOURCE_JOB_WORKER_COUNT
    return max(1, min(256, configured))


def _resource_global_slot_retry_delay_seconds() -> float:
    """Bound a delayed requeue so a saturated slot never blocks a worker."""
    try:
        configured = float(os.environ.get("EDUAGENT_RESOURCE_SLOT_RETRY_SECONDS", "0.25"))
    except (TypeError, ValueError):
        configured = 0.25
    return max(0.05, min(5.0, configured))


def _resource_job_recovery_stale_seconds() -> float:
    """Return the startup lease timeout for workers that died while running."""
    try:
        configured = float(os.environ.get("EDUAGENT_RESOURCE_JOB_STALE_SECONDS", "90"))
    except (TypeError, ValueError):
        configured = 90.0
    # The normal concept + supporting phases are bounded to roughly 40 seconds.
    # Keep a small positive floor but let operators choose a larger lease for a
    # slower provider or deployment rollout.
    return max(1.0, min(3600.0, configured))


def _resource_cost_setting(name: str) -> int:
    try:
        configured = int(os.environ.get(name, "0"))
    except (TypeError, ValueError):
        configured = 0
    return max(0, configured)


def _resource_cost_microunits(
    input_tokens: int,
    output_tokens: int,
) -> int:
    input_rate = _resource_cost_setting(
        "EDUAGENT_RESOURCE_COST_PER_1K_INPUT_MICROUNITS"
    )
    output_rate = _resource_cost_setting(
        "EDUAGENT_RESOURCE_COST_PER_1K_OUTPUT_MICROUNITS"
    )
    return (
        max(0, int(input_tokens)) * input_rate
        + max(0, int(output_tokens)) * output_rate
        + 999
    ) // 1000


def _in_process_resource_workers_enabled() -> bool:
    """Keep API processes enqueue-only in production.

    The compatibility executor remains available for local development,
    staging smoke tests and the synchronous legacy bridge. Production workers
    run through ``python -m src.resource_worker`` and claim PostgreSQL leases.
    """
    explicit = str(
        os.environ.get("EDUAGENT_RESOURCE_IN_PROCESS_WORKERS", "")
    ).strip().lower()
    if explicit:
        return explicit in {"1", "true", "yes", "on"}
    environment = str(
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or ""
    ).strip().lower()
    return environment not in {"prod", "production"}


_RESOURCE_JOB_WORKER_COUNT = _resource_job_worker_count()

# Keep one worker reserved for the first visible learning surface. The normal
# pool owns the remaining configured capacity, so a queued supporting bundle
# cannot consume every worker while a concept map is waiting. With a one-worker
# deployment all jobs share the reserved worker; that preserves the configured
# concurrency ceiling even though it cannot provide preemption.
_RESOURCE_CONCEPT_JOB_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="eduagent-resource-concept",
)
_RESOURCE_JOB_EXECUTOR: Optional[concurrent.futures.ThreadPoolExecutor] = (
    concurrent.futures.ThreadPoolExecutor(
        max_workers=_RESOURCE_JOB_WORKER_COUNT - 1,
        thread_name_prefix="eduagent-resource-job",
    )
    if _RESOURCE_JOB_WORKER_COUNT > 1
    else None
)


def get_resource_generation_repo() -> ResourceGenerationRepo:
    """Return the process-level coordination repository used by workers."""
    global _RESOURCE_JOB_REPO
    with _RESOURCE_JOB_REPO_LOCK:
        if _RESOURCE_JOB_REPO is None:
            _RESOURCE_JOB_REPO = ResourceGenerationRepo()
        return _RESOURCE_JOB_REPO


@contextmanager
def _resource_session_lock(user_id: str, course_id: str) -> Iterator[None]:
    key = (str(user_id), str(course_id))
    with _RESOURCE_SESSION_LOCKS_LOCK:
        lock = _RESOURCE_SESSION_LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield


def _normalise_requested_types(
    card_types: Optional[Iterable[str]] = None,
    *,
    card_type: Optional[str] = None,
) -> tuple[Optional[list[str]], Optional[str]]:
    if card_types is None:
        values: list[Any] = [card_type] if card_type and str(card_type).strip() else list(CARD_TYPES)
    elif isinstance(card_types, str):
        values = [card_types]
    else:
        values = list(card_types)
    if not values:
        values = list(CARD_TYPES)
    requested = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    invalid = [value for value in requested if value not in CARD_TYPES]
    if invalid:
        return None, f"不支持的资源类型：{invalid[0]}。"
    return [card_type for card_type in RESOURCE_CARD_ORDER if card_type in requested], None


def _read_session(user_id: str, course_id: str) -> Any:
    """Read a session without initializing the expensive orchestration runtime.

    The learning route establishes its session before requesting resources. A
    direct resource GET must not create a graph/LLM runtime merely to discover
    that no cards exist, otherwise a cache read can inherit remote startup
    latency. It also must not hydrate a persisted session here: restoring a
    snapshot replaces process runtime state, which turns a nominal GET into a
    stateful operation. Session bootstrap owns that recovery path.
    """
    from src import orchestration_runtime

    # Unit tests and embedded deployments can inject a lightweight runtime
    # through this module. It must win even when another surface has already
    # initialized the process singleton, otherwise a synchronous compatibility
    # bridge writes one session and reads an unrelated one back.
    if get_runtime is not orchestration_runtime.get_runtime:
        try:
            runtime = get_runtime()
        except Exception:
            runtime = None
    else:
        runtime = getattr(orchestration_runtime, "_runtime", None)
    if runtime is None:
        return None
    peek_session = getattr(runtime, "peek_session", None)
    session = peek_session(user_id, course_id) if callable(peek_session) else None
    return session


def _resource_payload(
    node_id: str,
    cards: Iterable[ResourceCard],
    *,
    requested_types: Iterable[str],
    status: str = "ok",
    include_legacy: bool = False,
) -> Dict[str, Any]:
    cards = list(cards)
    response = resource_response(
        node_id,
        [resource_contract_from_card(card) for card in cards],
        status=status,
    )
    payload = response.to_compatible_dict() if include_legacy else response.to_dto_dict()
    present = {card.card_type for card in cards}
    payload["missing_card_types"] = [
        card_type for card_type in requested_types if card_type not in present
    ]
    return payload


def _cache_record_payload(record: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(record, dict):
        return None
    payload = record.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("card"), dict):
        payload = payload["card"]
    return dict(payload) if isinstance(payload, dict) else None


def _cache_record_source_refs(record: Dict[str, Any], card: ResourceCard) -> list[Dict[str, Any]]:
    metadata = card.metadata if isinstance(card.metadata, dict) else {}
    raw_refs = metadata.get("source_refs")
    if not isinstance(raw_refs, list):
        raw_refs = record.get("source_refs")
    if not isinstance(raw_refs, list):
        return []
    return [
        dict(ref)
        for ref in raw_refs
        if isinstance(ref, dict) and str(ref.get("id") or "").strip()
    ]


def _is_generic_base_cache(record: Any) -> bool:
    """Only permit explicitly sanitized course-cache records across learners."""
    if not isinstance(record, dict):
        return False
    metadata = record.get("metadata")
    if (
        isinstance(metadata, dict)
        and metadata.get("cache_scope") == "course_base"
        and metadata.get("cache_policy") == _COURSE_BASE_CACHE_POLICY
    ):
        return True
    payload = _cache_record_payload(record)
    card_metadata = payload.get("metadata") if isinstance(payload, dict) else None
    return (
        isinstance(card_metadata, dict)
        and card_metadata.get("cache_scope") == "course_base"
        and card_metadata.get("cache_policy") == _COURSE_BASE_CACHE_POLICY
    )


def _cache_read_context(
    user_id: str,
    course_id: str,
    node_id: str,
    state: Any,
    *,
    locale: str,
) -> ResourceContext:
    """Build a local-only context for cache validation without a runtime."""
    context = build_resource_context(
        None,
        state,
        course_id,
        node_id,
        node_title=node_id,
        locale=locale,
    )
    # A persisted state should already agree, but the request identity is the
    # boundary used for a personal-cache lookup.
    return replace(context, user_id=str(user_id))


def _validated_cached_card(
    record: Any,
    context: ResourceContext,
    card_type: str,
    *,
    cache_scope: str,
) -> Optional[ResourceCard]:
    """Validate a cached card before exposing it without writing it anywhere."""
    if not isinstance(record, dict):
        return None
    if str(record.get("content_version") or "") != str(context.content_version):
        return None
    if str(record.get("locale") or "") != str(context.locale):
        return None
    if str(record.get("knowledge_index_version") or "") != str(context.knowledge_index_version):
        return None
    payload = _cache_record_payload(record)
    if payload is None:
        return None
    try:
        card = ResourceCard.model_validate(payload)
    except Exception:
        return None
    if card.card_type != card_type or card.node_id != context.node_id:
        return None

    metadata = dict(card.metadata or {})
    if str(metadata.get("content_version") or "") != str(context.content_version):
        return None
    if str(metadata.get("knowledge_index_version") or "") != str(context.knowledge_index_version):
        return None
    if str(metadata.get("locale") or "") != str(context.locale):
        return None
    cached_generation = metadata.get("generation")
    if not isinstance(cached_generation, dict) or not str(cached_generation.get("source") or "").strip():
        return None
    if cached_generation.get("source") == "template":
        # Guard against caches poisoned before template writes were skipped.
        return None
    structured_payload = metadata.get("structured_payload")
    if not isinstance(structured_payload, dict):
        return None
    source_refs = _cache_record_source_refs(record, card)
    if not source_refs:
        return None
    binding = metadata.get("semantic_binding")
    if not isinstance(binding, dict):
        return None
    if (
        str(binding.get("course_id") or "") != str(context.course_id)
        or str(binding.get("node_id") or "") != str(context.node_id)
        or not str(binding.get("title") or "").strip()
    ):
        return None

    validation_context = replace(
        context,
        node_title=str(binding["title"]),
        knowledge_refs=source_refs,
    )
    structured_validation = validate_resource_payload(card_type, structured_payload, validation_context)
    if not structured_validation.valid or structured_validation.payload is None:
        return None

    generation = dict(metadata.get("generation") or {})
    rendered = _truthful_generated_content(
        render_markdown(card_type, structured_validation.payload),
        generation,
    )
    metadata.update({
        "title": str(structured_validation.payload.get("title") or binding["title"]),
        "structured_payload": structured_validation.payload,
        "body_markdown": rendered,
        "source_refs": source_refs,
    })
    candidate = card.model_copy(update={"content": rendered, "metadata": metadata})
    try:
        validated, _validation = get_validation_pipeline().validate_resource_card(candidate)
    except Exception:
        return None
    if validated is None:
        return None

    validated_metadata = dict(validated.metadata or {})
    validated_generation = dict(validated_metadata.get("generation") or {})
    validated_generation.update({"cache_hit": True, "cache_scope": cache_scope})
    validated_metadata["generation"] = validated_generation
    validated_metadata["personalization_basis"] = {
        "mastery_bucket": context.mastery_bucket,
        "error_signature": context.error_signature,
        "cognitive_style": context.cognitive_style,
    }
    validated_metadata["difficulty_rationale"] = {
        "mastery": round(float(context.mastery), 3),
        "mastery_bucket": context.mastery_bucket,
        "learning_stage": context.learning_stage,
        "source": "cache_read",
    }
    return validated.model_copy(update={
        "difficulty": max(0.1, min(1.0, 1.0 - float(context.mastery))),
        "cognitive_style": context.cognitive_style,
        "metadata": validated_metadata,
    })


def _read_cached_card_for_get(
    repo: ResourceGenerationRepo,
    context: ResourceContext,
    card_type: str,
    *,
    allow_personal: bool,
) -> Optional[ResourceCard]:
    """Read matching cache records without table setup, writes, or job creation."""
    if allow_personal:
        personal_reader = getattr(repo, "read_personal_cache", None)
        if callable(personal_reader):
            personal = personal_reader(
                context.user_id,
                context.course_id,
                context.node_id,
                card_type,
                mastery_bucket=context.mastery_bucket,
                error_signature=context.error_signature,
                cognitive_style=context.cognitive_style,
                content_version=context.content_version,
                locale=context.locale,
                knowledge_index_version=context.knowledge_index_version,
            )
            card = _validated_cached_card(personal, context, card_type, cache_scope="personal")
            if card is not None:
                return card

    base_reader = getattr(repo, "read_base_cache", None)
    if not callable(base_reader):
        return None
    base = base_reader(
        context.course_id,
        context.node_id,
        card_type,
        content_version=context.content_version,
        locale=context.locale,
        knowledge_index_version=context.knowledge_index_version,
    )
    if not _is_generic_base_cache(base):
        return None
    return _validated_cached_card(base, context, card_type, cache_scope="course_base")


def get_node_resources(
    user_id: str,
    course_id: str = "data_structures",
    node_id: Optional[str] = None,
    *,
    card_types: Optional[Iterable[str]] = None,
    card_type: Optional[str] = None,
    include_legacy: bool = False,
    locale: str = "zh-CN",
    repo: Optional[ResourceGenerationRepo] = None,
) -> Dict[str, Any]:
    """Return persisted or validated cached cards without generating or persisting."""
    requested_types, error = _normalise_requested_types(card_types, card_type=card_type)
    if error:
        return {"error": error, "status_code": 400}
    session = _read_session(user_id, course_id)
    state = getattr(session, "agent_state", None)
    target_node = str(node_id or getattr(state, "current_node_id", "") or "")
    if not target_node:
        return {"error": "缺少学习节点标识。", "status_code": 400}
    cards = [
        card
        for card in (
            list(getattr(state, "generated_resources", {}).get(target_node, []))
            if state
            else []
        )
        if _resource_card_language_valid(card, locale)
    ]
    selected_by_type = {
        card.card_type: card
        for card in cards
        if card.card_type in (requested_types or [])
    }
    missing_types = [
        requested_type
        for requested_type in requested_types or []
        if requested_type not in selected_by_type
    ]
    if missing_types:
        try:
            context = _cache_read_context(user_id, course_id, target_node, state, locale=locale)
            repository = repo or get_resource_generation_repo()
            for requested_type in missing_types:
                if requested_type == "diagnostic_quiz":
                    # A quiz can only be graded from its server-owned copy in
                    # session state. A read-only cache hit has no such binding;
                    # leave it missing so the generation POST restores and
                    # persists the full card before it is shown.
                    continue
                cached = _read_cached_card_for_get(
                    repository,
                    context,
                    requested_type,
                    allow_personal=state is not None,
                )
                if cached is not None:
                    selected_by_type[requested_type] = cached
        except Exception:
            # Cache infrastructure is an acceleration path.  A read failure
            # must remain a cold read, not mutate session state or enqueue work.
            pass
    selected = [
        selected_by_type[requested_type]
        for requested_type in requested_types or []
        if requested_type in selected_by_type
    ]
    return _resource_payload(
        target_node,
        selected,
        requested_types=requested_types or [],
        include_legacy=include_legacy,
    )


def get_generation_job(
    job_id: str,
    *,
    user_id: Optional[str] = None,
    repo: Optional[ResourceGenerationRepo] = None,
) -> Optional[Dict[str, Any]]:
    """Read a job, optionally applying the caller's ownership boundary."""
    job = (repo or get_resource_generation_repo()).get_job(str(job_id))
    if job is None or (user_id is not None and str(job.get("user_id")) != str(user_id)):
        return None
    return job


def _public_generation_events(
    events: Iterable[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    public_events: list[Dict[str, Any]] = []
    for raw_event in events:
        event = dict(raw_event) if isinstance(raw_event, dict) else {}
        if event.get("event_type") == "card_ready":
            payload = event.get("payload")
            payload = dict(payload) if isinstance(payload, dict) else {}
            card = payload.get("card")
            if isinstance(card, dict):
                payload["card"] = public_resource_contract_dict(
                    card,
                    resource_type=str(
                        payload.get("card_type")
                        or card.get("resource_type")
                        or card.get("card_type")
                        or ""
                    ),
                )
            event["payload"] = payload
        public_events.append(event)
    return public_events


def list_generation_events(
    job_id: str,
    *,
    after_event_id: int = 0,
    limit: int = 100,
    user_id: Optional[str] = None,
    repo: Optional[ResourceGenerationRepo] = None,
    wake_wait_seconds: Optional[float] = None,
) -> list[Dict[str, Any]]:
    """Read reconnectable generation events without changing job state."""
    repository = repo or get_resource_generation_repo()
    if get_generation_job(job_id, user_id=user_id, repo=repository) is None:
        return []
    events = repository.list_events(
        str(job_id),
        after_event_id=after_event_id,
        limit=limit,
    )
    if events:
        return _public_generation_events(events)
    if wake_wait_seconds is None:
        try:
            wake_wait_seconds = float(
                os.environ.get(
                    "EDUAGENT_RESOURCE_EVENT_WAKE_WAIT_SECONDS",
                    "0",
                )
            )
        except (TypeError, ValueError):
            wake_wait_seconds = 0.0
    wait_seconds = max(0.0, min(1.0, float(wake_wait_seconds)))
    if wait_seconds <= 0:
        return []
    resource_event_notifier.wait(
        str(job_id),
        after_event_id=max(0, int(after_event_id)),
        timeout_seconds=wait_seconds,
    )
    # Redis is only a hint. Always replay the authoritative PostgreSQL ledger,
    # including after timeout or notifier failure.
    return _public_generation_events(
        repository.list_events(
            str(job_id),
            after_event_id=after_event_id,
            limit=limit,
        )
    )


def _generation_context(
    runtime: Any,
    state: Any,
    course_id: str,
    node_id: str,
    locale: str,
    *,
    allow_remote_retrieval: bool = True,
    content_version: str = "",
) -> tuple[Dict[str, Any], Any]:
    binding = _canonical_node_binding(runtime, course_id, node_id)
    context = build_resource_context(
        runtime,
        state,
        course_id,
        node_id,
        node_title=str(binding["title"]),
        locale=locale,
        allow_remote_retrieval=allow_remote_retrieval,
        content_version=content_version,
    )
    return binding, context


def _idempotency_key(
    *,
    user_id: str,
    course_id: str,
    node_id: str,
    card_types: Iterable[str],
    force: bool,
    use_cache: bool,
    priority: str,
    context: Any,
) -> str:
    request = {
        "user_id": str(user_id),
        "course_id": str(course_id),
        "node_id": str(node_id),
        "card_types": list(card_types),
        "force": bool(force),
        "use_cache": bool(use_cache),
        # Priority changes scheduling semantics. It is therefore part of the
        # request identity rather than something a later caller can silently
        # lose when joining an active low-priority job.
        "priority": str(priority or "normal"),
        "content_version": str(context.content_version),
        "knowledge_index_version": str(context.knowledge_index_version),
        "locale": str(context.locale),
        "personalization": str(context.personalization_cache_key),
    }
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest()


def _invalidate_requested_caches(
    repo: ResourceGenerationRepo,
    user_id: str,
    course_id: str,
    node_id: str,
    card_types: Iterable[str],
) -> None:
    for card_type in card_types:
        # A force refresh deliberately has card scope. A full refresh asks for
        # all five types and therefore invalidates the full node package.
        repo.delete_base_cache(course_id, node_id, resource_type=card_type)
        repo.delete_personal_cache(user_id, course_id, node_id, resource_type=card_type)


def _is_concept_priority_job(job: Optional[Dict[str, Any]]) -> bool:
    """Return whether a persisted job belongs on the reserved concept lane."""
    if not isinstance(job, dict):
        return False
    priority = str(job.get("priority") or "").strip().lower()
    card_types = [
        str(card_type)
        for card_type in job.get("card_types", [])
        if str(card_type) in CARD_TYPES
    ]
    # The explicit priority is durable and is the public scheduling contract.
    # A supporting bundle must never enter the reserved lane, even if an old
    # client labels a full-card request as ``concept_map``.
    return priority == "concept_map" and card_types == ["concept_map"]


def _generation_executor_for_job(job: Optional[Dict[str, Any]]) -> concurrent.futures.ThreadPoolExecutor:
    if _is_concept_priority_job(job):
        return _RESOURCE_CONCEPT_JOB_EXECUTOR
    # On an intentionally single-worker installation there is no background
    # pool. Both lanes share the one executor to retain the configured limit.
    return _RESOURCE_JOB_EXECUTOR or _RESOURCE_CONCEPT_JOB_EXECUTOR


def _submit_generation_job(
    job_id: str,
    *,
    repo: Optional[ResourceGenerationRepo] = None,
    replace_active: bool = False,
) -> None:
    repository = repo or get_resource_generation_repo()
    executor = _generation_executor_for_job(repository.get_job(job_id))

    def clear(completed: concurrent.futures.Future[Any]) -> None:
        with _RESOURCE_JOB_FUTURES_LOCK:
            if _RESOURCE_JOB_FUTURES.get(job_id) is completed:
                _RESOURCE_JOB_FUTURES.pop(job_id, None)

    with _RESOURCE_JOB_FUTURES_LOCK:
        existing = _RESOURCE_JOB_FUTURES.get(job_id)
        if existing is not None and not existing.done() and not replace_active:
            return
        future = executor.submit(run_generation_job, job_id, repo=repository)
        _RESOURCE_JOB_FUTURES[job_id] = future
    # ``Future.add_done_callback`` invokes immediately for a fast completed
    # task, so it must run after releasing the non-reentrant futures lock.
    future.add_done_callback(clear)


def _schedule_generation_job_retry(
    job_id: str,
    *,
    repo: ResourceGenerationRepo,
) -> None:
    """Resubmit a slot-contended job after a short worker-side delay."""
    normalized_job_id = str(job_id)

    def retry() -> None:
        with _RESOURCE_JOB_RETRY_TIMERS_LOCK:
            if _RESOURCE_JOB_RETRY_TIMERS.get(normalized_job_id) is timer:
                _RESOURCE_JOB_RETRY_TIMERS.pop(normalized_job_id, None)
        job = repo.get_job(normalized_job_id)
        if job is None or str(job.get("status") or "") not in {"queued", "retrying"}:
            return
        _submit_generation_job(normalized_job_id, repo=repo)

    with _RESOURCE_JOB_RETRY_TIMERS_LOCK:
        existing = _RESOURCE_JOB_RETRY_TIMERS.get(normalized_job_id)
        if existing is not None and existing.is_alive():
            return
        timer = threading.Timer(_resource_global_slot_retry_delay_seconds(), retry)
        timer.daemon = True
        _RESOURCE_JOB_RETRY_TIMERS[normalized_job_id] = timer
    timer.start()


def drain_generation_workers(timeout_seconds: float = 15.0) -> bool:
    """Cancel pending retries and wait until no background job is in flight.

    A completing job may enqueue follow-up work (a concept map fans out its
    supporting bundle), so the wait loops until both the retry timers and the
    submitted futures are empty. Returns False when work is still running at
    the deadline. Used by graceful shutdown and by the test suite to keep
    worker threads from leaking across test boundaries.
    """
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        with _RESOURCE_JOB_RETRY_TIMERS_LOCK:
            timers = list(_RESOURCE_JOB_RETRY_TIMERS.values())
            _RESOURCE_JOB_RETRY_TIMERS.clear()
        for timer in timers:
            timer.cancel()
        with _RESOURCE_JOB_FUTURES_LOCK:
            futures = list(_RESOURCE_JOB_FUTURES.values())
        if not futures and not timers:
            return True
        for future in futures:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                future.result(timeout=remaining)
            except concurrent.futures.TimeoutError:
                return False
            except Exception:
                # A failed job still counts as drained; its error is already
                # recorded on the job row by the worker.
                pass


def request_generation(
    user_id: str,
    course_id: str = "data_structures",
    node_id: Optional[str] = None,
    *,
    card_types: Optional[Iterable[str]] = None,
    force: bool = False,
    priority: str = "normal",
    locale: str = "zh-CN",
    use_cache: bool = True,
    submit: bool = True,
    repo: Optional[ResourceGenerationRepo] = None,
) -> Dict[str, Any]:
    """Create or merge a background generation job without doing model work."""
    requested_types, error = _normalise_requested_types(card_types)
    if error:
        return {"error": error, "status_code": 400}
    normalized_priority = str(priority or "normal").strip().lower() or "normal"
    session = get_session(user_id, course_id)
    state = session.agent_state
    target_node = str(node_id or state.current_node_id or (state.active_path[0] if state.active_path else "") or "")
    if not target_node:
        return {"error": "缺少学习节点标识。", "status_code": 400}

    active_retest_resource_id = _active_retest_resource_id(state, target_node)
    if force and active_retest_resource_id and "diagnostic_quiz" in (requested_types or []):
        if (requested_types or []) == ["diagnostic_quiz"]:
            return {
                "status": "review_retest_active",
                "error": "请先完成当前复习复测，再替换诊断测验。",
                "status_code": 409,
                "node_id": target_node,
                "retest_resource_id": active_retest_resource_id,
            }
        requested_types = [card_type for card_type in requested_types or [] if card_type != "diagnostic_quiz"]

    runtime = get_runtime()
    context_started = time.perf_counter()
    binding, context = _generation_context(
        runtime,
        state,
        course_id,
        target_node,
        locale,
        allow_remote_retrieval=False,
    )
    if binding.get("catalog_checked") and not binding.get("exists"):
        return {
            "error": "学习节点不存在或不属于当前课程。",
            "status_code": 404,
            "node_id": target_node,
        }
    observe_metric("resource.generation.context_ms", round((time.perf_counter() - context_started) * 1000, 3))
    existing_cards = [
        card
        for card in state.generated_resources.get(target_node, [])
        if _resource_card_language_valid(card, locale)
    ]
    # Template fallbacks count as missing so a later request retries them
    # with a fresh budget; the degraded card stays visible in the meantime.
    existing_types = {
        card.card_type
        for card in existing_cards
        if not _is_template_generated(card.metadata)
    }
    types_to_generate = list(requested_types or []) if force else [
        card_type for card_type in requested_types or [] if card_type not in existing_types
    ]
    # A cold-node concept request is the only request shape that fans out
    # automatically. Targeted force refreshes remain strictly card-scoped;
    # full refreshes retain their explicit all-card request.
    auto_supporting_card_types = (
        [
            card_type
            for card_type in RESOURCE_CARD_ORDER
            if card_type != "concept_map" and card_type not in existing_types
        ]
        if (
            not force
            and normalized_priority == "concept_map"
            and requested_types == ["concept_map"]
            and types_to_generate == ["concept_map"]
        )
        else []
    )
    existing_payload = _resource_payload(
        target_node,
        existing_cards,
        requested_types=requested_types or [],
    )
    if not types_to_generate:
        return {
            "job_id": None,
            "status": "completed",
            "task_status": "completed",
            "existing_resources": existing_payload["resources"],
            "resources": existing_payload["resources"],
            "missing_card_types": [],
            "requested_card_types": requested_types or [],
            "node_id": target_node,
            "created": False,
        }

    repository = repo or get_resource_generation_repo()
    if force:
        try:
            _invalidate_requested_caches(repository, user_id, course_id, target_node, types_to_generate)
        except Exception as exc:
            # Force jobs bypass cache reads, so an unavailable cache must not
            # prevent a fresh card from being created.
            state.record_error(f"resource_cache_invalidate_failed:{target_node}:{type(exc).__name__}")
            incr_metric("resource.generation.cache_invalidate_failed_total")
    key = _idempotency_key(
        user_id=user_id,
        course_id=course_id,
        node_id=target_node,
        card_types=types_to_generate,
        force=force,
        use_cache=use_cache,
        priority=normalized_priority,
        context=context,
    )
    existing_active = repository.get_active_job(
        user_id,
        course_id,
        target_node,
        key,
    )
    queue = repository.queue_snapshot()
    concept_lane = (
        normalized_priority in {"concept_map", "concept"}
        and types_to_generate == ["concept_map"]
    )
    if existing_active is None:
        if int(queue.get("depth") or 0) >= 5_000 and not concept_lane:
            return {
                "error": "学习资源生成队列暂时已满，请稍后重试。",
                "status_code": 503,
                "retry_after": 30,
                "queue_depth": int(queue.get("depth") or 0),
            }
        if (
            int(queue.get("depth") or 0) >= 4_000
            and normalized_priority in {"shadow", "supporting", "supporting_bundle"}
        ):
            return {
                "error": "低优先级学习资源生成暂时暂停，请稍后重试。",
                "status_code": 503,
                "retry_after": 15,
                "queue_depth": int(queue.get("depth") or 0),
            }
        if repository.active_job_count_for_user(user_id) >= 2:
            return {
                "error": "每位学习者最多只能同时运行两个资源生成任务。",
                "status_code": 429,
                "retry_after": 5,
            }

    rollout = resource_v4_rollout(
        user_id,
        course_id,
        target_node,
        requested_shadow=normalized_priority == "shadow",
    )
    deadline_seconds = (
        CONCEPT_DEADLINE_SECONDS if concept_lane else BUNDLE_DEADLINE_SECONDS
    )
    deadline_iso = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + deadline_seconds,
        tz=timezone.utc,
    ).isoformat()
    try:
        job, created = repository.create_or_get_active_job(
            user_id,
            course_id,
            target_node,
            key,
            card_types=types_to_generate,
            force=force,
            priority=normalized_priority,
            request_params={
                "requested_card_types": requested_types,
                "locale": context.locale,
                "use_cache": bool(use_cache),
                "auto_supporting_card_types": auto_supporting_card_types,
            },
            content_version=context.content_version,
            knowledge_index_version=context.knowledge_index_version,
            locale=context.locale,
            max_retries=1,
            pipeline_version=PIPELINE_VERSION if rollout.enabled else context.content_version,
            prompt_version=PROMPT_VERSION if rollout.enabled else context.content_version,
            blueprint_version=BLUEPRINT_VERSION if rollout.enabled else context.content_version,
            quality_version=QUALITY_VERSION if rollout.enabled else context.content_version,
            deadline_at=deadline_iso,
            token_budget_input=MAX_INPUT_TOKENS,
            token_budget_output=MAX_OUTPUT_TOKENS,
            generation_call_budget=MAX_GENERATION_CALLS,
            cost_budget_microunits=_resource_cost_setting(
                "EDUAGENT_RESOURCE_COST_BUDGET_MICROUNITS"
            ),
            exposure_mode=rollout.exposure_mode,
            trace_id=get_request_id() or uuid.uuid4().hex,
            release_version=str(os.environ.get("RELEASE_VERSION") or ""),
            cohort=rollout.cohort,
            enforce_admission=True,
            concept_lane=concept_lane,
        )
    except ResourceAdmissionError as exc:
        return exc.response_payload()
    if (
        submit
        and _in_process_resource_workers_enabled()
        and (created or str(job.get("status") or "") in {"queued", "retrying"})
    ):
        _submit_generation_job(str(job["job_id"]), repo=repository)
    result = {
        "job_id": job["job_id"],
        "status": job["status"],
        "task_status": job["status"],
        "existing_resources": existing_payload["resources"],
        "resources": existing_payload["resources"],
        "missing_card_types": types_to_generate,
        "requested_card_types": requested_types or [],
        "node_id": target_node,
        "created": created,
    }
    if active_retest_resource_id:
        result["preserved_retest_resource_id"] = active_retest_resource_id
    return result


def _start_job_heartbeat(
    repository: ResourceGenerationRepo,
    job_id: str,
    owner_id: str,
    *,
    interval_seconds: Optional[float] = None,
) -> Optional[threading.Thread]:
    """Renew an in-process worker lease until the job leaves ``running``.

    The compatibility claim in :func:`run_generation_job` executes the whole
    job on the claiming thread without the dedicated worker's heartbeat loop,
    so its 60-second lease used to expire mid-bundle (deadline 120s) and the
    stale sweep could steal a healthy job. The thread stops on its own once
    ``heartbeat_job`` reports the lease is gone (terminal status or takeover)
    and is hard-capped past the bundle deadline as a leak guard.
    """
    heartbeat = getattr(repository, "heartbeat_job", None)
    if not callable(heartbeat):
        return None
    interval = float(interval_seconds or max(5.0, DEFAULT_LEASE_SECONDS / 3.0))
    stop_after = time.monotonic() + BUNDLE_DEADLINE_SECONDS + DEFAULT_LEASE_SECONDS

    def renew() -> None:
        while time.monotonic() < stop_after:
            time.sleep(interval)
            try:
                if not heartbeat(job_id, owner_id, lease_seconds=DEFAULT_LEASE_SECONDS):
                    return
            except Exception:
                incr_metric("resource.generation.heartbeat_error_total")

    thread = threading.Thread(
        target=renew,
        name=f"resource-job-heartbeat-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return thread


def recover_pending_generation_jobs(
    job_ids: Optional[Iterable[str]] = None,
    *,
    repo: Optional[ResourceGenerationRepo] = None,
    stale_after_seconds: Optional[float] = None,
) -> list[str]:
    """Requeue pending jobs after a process restart or worker loss.

    The durable repository intentionally owns job discovery. It may expose a
    ``list_pending_jobs`` method in deployments with an external queue; this
    service also accepts explicit ids so a server lifespan hook can recover
    jobs it observed before shutdown without coupling to storage internals.
    """
    repository = repo or get_resource_generation_repo()
    if job_ids is None:
        recover_stale = getattr(repository, "recover_stale_running_jobs", None)
        if callable(recover_stale):
            if stale_after_seconds is None:
                lease_seconds = _resource_job_recovery_stale_seconds()
            else:
                try:
                    lease_seconds = max(0.0, float(stale_after_seconds))
                except (TypeError, ValueError):
                    lease_seconds = _resource_job_recovery_stale_seconds()
            recover_stale(stale_after_seconds=lease_seconds)
        list_pending = getattr(repository, "list_pending_jobs", None)
        jobs = list_pending() if callable(list_pending) else []
        job_ids = [job.get("job_id") for job in jobs if isinstance(job, dict)]
    recovered: list[str] = []
    for candidate in job_ids:
        job_id = str(candidate or "").strip()
        if not job_id:
            continue
        job = repository.get_job(job_id)
        if job is None or str(job.get("status") or "") not in {"queued", "retrying"}:
            continue
        _submit_generation_job(job_id, repo=repository)
        recovered.append(job_id)
    return recovered


def sweep_generation_jobs(*, repo: Optional[ResourceGenerationRepo] = None) -> Dict[str, int]:
    """Fail deadline-expired jobs, then requeue stale running work.

    In-process deployments have no dedicated worker loop, so this sweep is
    their only periodic recovery path; the server schedules it every
    ``EDUAGENT_RESOURCE_JOB_SWEEP_INTERVAL_SEC`` (default 60s). Expiry runs
    first so a running job past its end-to-end deadline fails cleanly instead
    of being requeued for a client that already gave up.
    """
    repository = repo or get_resource_generation_repo()
    expire = getattr(repository, "expire_deadline_jobs", None)
    expired = expire() if callable(expire) else []
    recovered = recover_pending_generation_jobs(repo=repository)
    return {"expired": len(expired or []), "recovered": len(recovered)}


def _cache_card_for_context(
    repo: ResourceGenerationRepo,
    context: Any,
    card_type: str,
) -> Optional[ResourceCard]:
    personal = repo.get_personal_cache(
        context.user_id,
        context.course_id,
        context.node_id,
        card_type,
        mastery_bucket=context.mastery_bucket,
        error_signature=context.error_signature,
        cognitive_style=context.cognitive_style,
        content_version=context.content_version,
        locale=context.locale,
        knowledge_index_version=context.knowledge_index_version,
    )
    card = _validated_cached_card(personal, context, card_type, cache_scope="personal")
    if card is not None:
        return card

    base = repo.get_base_cache(
        context.course_id,
        context.node_id,
        card_type,
        content_version=context.content_version,
        locale=context.locale,
        knowledge_index_version=context.knowledge_index_version,
    )
    if not _is_generic_base_cache(base):
        return None
    return _validated_cached_card(base, context, card_type, cache_scope="course_base")


def _is_generic_course_context(context: ResourceContext) -> bool:
    """Whether a generated card is safe to share through the course base cache.

    Resource prompts deliberately receive learner-specific state.  A course
    cache must therefore only store output made from the neutral baseline,
    otherwise adapted wording or diagnostic material can leak to another
    learner.  Personal cache entries retain every other generation.
    """
    try:
        mastery = float(context.mastery)
    except (TypeError, ValueError):
        return False
    if abs(mastery - 0.5) > 1e-9 or str(context.mastery_bucket) != "developing":
        return False
    if str(context.error_signature or "").strip().lower() not in {"", "none"}:
        return False
    if str(context.cognitive_style or "").strip().lower() not in {"", "textual"}:
        return False
    if context.completed_resource_types:
        return False
    if isinstance(context.recent_diagnostic, dict) and any(
        value not in (None, "", [], {}, ())
        for value in context.recent_diagnostic.values()
    ):
        return False
    return str(context.learning_stage or "").strip().upper() in {
        "",
        "PRACTICE",
        "STANDARD",
        "STANDARD_PATH",
    }


def _course_base_cache_card(context: ResourceContext, card: ResourceCard) -> Optional[ResourceCard]:
    """Strip learner-specific cache fields before storing a course-level card."""
    if not _is_generic_course_context(context):
        return None
    metadata = dict(card.metadata or {})
    structured_payload = metadata.get("structured_payload")
    if not isinstance(structured_payload, dict):
        return None
    base_payload = dict(structured_payload)
    if card.card_type == "interactive_exercise":
        # This is the only first-class learner signal in a card payload.  Do
        # not carry a previous learner's error signature into the base layer.
        base_payload["error_signature"] = "none"

    for key, value in base_payload.items():
        metadata[key] = value
    if card.card_type == "diagnostic_quiz":
        metadata["questions"] = list(base_payload.get("questions") or [])
        metadata["quiz_revision"] = 1
    generation = dict(metadata.get("generation") or {})
    generation.pop("job_id", None)
    metadata.update({
        "structured_payload": base_payload,
        "body_markdown": _truthful_generated_content(
            render_markdown(card.card_type, base_payload),
            generation,
        ),
        "generation": generation,
        "cache_scope": "course_base",
        "cache_policy": _COURSE_BASE_CACHE_POLICY,
        "personalization_basis": {
            "scope": "course_base",
            "policy": _COURSE_BASE_CACHE_POLICY,
        },
        "difficulty_rationale": {"source": "course_base_cache"},
    })
    return card.model_copy(update={
        "content": metadata["body_markdown"],
        "difficulty": 0.5,
        "cognitive_style": "textual",
        "metadata": metadata,
    })


def _store_card_in_caches(repo: ResourceGenerationRepo, context: Any, card: ResourceCard) -> None:
    metadata = dict(card.metadata or {})
    if _is_template_generated(metadata):
        # A template placeholder is regenerable locally for free; caching it
        # would turn one failed generation into a lasting cache hit.
        return
    payload = card.model_dump(mode="json")
    source_refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    cache_metadata = {
        "generation": metadata.get("generation", {}),
        "content_version": metadata.get("content_version", context.content_version),
        "knowledge_index_version": metadata.get("knowledge_index_version", context.knowledge_index_version),
    }
    base_card = _course_base_cache_card(context, card)
    if base_card is not None:
        base_metadata = dict(base_card.metadata or {})
        base_source_refs = (
            base_metadata.get("source_refs")
            if isinstance(base_metadata.get("source_refs"), list)
            else []
        )
        repo.upsert_base_cache(
            context.course_id,
            context.node_id,
            card.card_type,
            base_card.model_dump(mode="json"),
            content_version=context.content_version,
            locale=context.locale,
            knowledge_index_version=context.knowledge_index_version,
            source_refs=base_source_refs,
            metadata={
                "generation": base_metadata.get("generation", {}),
                "content_version": base_metadata.get("content_version", context.content_version),
                "knowledge_index_version": base_metadata.get(
                    "knowledge_index_version",
                    context.knowledge_index_version,
                ),
                "cache_scope": "course_base",
                "cache_policy": _COURSE_BASE_CACHE_POLICY,
            },
        )
    repo.upsert_personal_cache(
        context.user_id,
        context.course_id,
        context.node_id,
        card.card_type,
        payload,
        mastery_bucket=context.mastery_bucket,
        error_signature=context.error_signature,
        cognitive_style=context.cognitive_style,
        content_version=context.content_version,
        locale=context.locale,
        knowledge_index_version=context.knowledge_index_version,
        metadata={**cache_metadata, "cache_scope": "personal"},
    )


def _from_runtime_result(
    generator: ResourceGenerator,
    context: Any,
    card_type: str,
    result: Any,
) -> GeneratedResourcePayload:
    content, metadata = _generation_metadata(result)
    source = str(metadata.get("source") or "unknown")
    if isinstance(result, dict):
        input_tokens = result.get(
            "input_tokens",
            metadata.get("input_tokens", 0),
        )
        output_tokens = result.get(
            "output_tokens",
            metadata.get("output_tokens", 0),
        )
    else:
        input_tokens = getattr(
            result,
            "input_tokens",
            metadata.get("input_tokens", 0),
        )
        output_tokens = getattr(
            result,
            "output_tokens",
            metadata.get("output_tokens", 0),
        )
    raw_payload = (
        result.get("structured_payload") if isinstance(result, dict) else getattr(result, "structured_payload", None)
    )
    if isinstance(raw_payload, dict):
        generated = generator._result_from_payload(  # noqa: SLF001 - shared generator owns validation
            card_type,
            raw_payload,
            context,
            source=source,
            provider=metadata.get("provider"),
            model=metadata.get("model"),
            fallback_reason=metadata.get("fallback_reason"),
            elapsed_ms=float(metadata.get("elapsed_ms") or 0.0),
            input_tokens=max(0, int(input_tokens or 0)),
            output_tokens=max(0, int(output_tokens or 0)),
        )
        return replace(generated, attempt_count=int(metadata.get("attempt_count") or generated.attempt_count))
    fallback = generator.template(context, card_type, str(metadata.get("fallback_reason") or "legacy_unstructured_output"))
    return replace(
        fallback,
        body_markdown=_truthful_generated_content(content or fallback.body_markdown, metadata),
        source=source,
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        attempt_count=int(metadata.get("attempt_count") or 0),
        fallback_reason=metadata.get("fallback_reason") or fallback.fallback_reason,
        elapsed_ms=float(metadata.get("elapsed_ms") or 0.0),
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
    )


def _generate_phase(
    runtime: Any,
    context: Any,
    card_types: list[str],
) -> Dict[str, GeneratedResourcePayload]:
    if not card_types:
        return {}
    generator = ResourceGenerator()
    difficulty = max(0.1, 1.0 - float(context.mastery))
    runtime_generate = getattr(runtime, "generate_resource_contents", None)
    if callable(runtime_generate):
        kwargs: Dict[str, Any] = {}
        if _call_supports_keyword(runtime_generate, "course_id"):
            kwargs["course_id"] = context.course_id
        if _call_supports_keyword(runtime_generate, "node_title"):
            kwargs["node_title"] = context.node_title
        if _call_supports_keyword(runtime_generate, "resource_context"):
            kwargs["resource_context"] = context
        raw = runtime_generate(context.node_id, card_types, difficulty, **kwargs)
        if isinstance(raw, dict):
            return {
                card_type: _from_runtime_result(generator, context, card_type, raw.get(card_type))
                for card_type in card_types
                if raw.get(card_type) is not None
            }
    llm = runtime.get_llm() if callable(getattr(runtime, "get_llm", None)) else None
    if card_types == ["concept_map"]:
        # max_tokens 统一由 prompts.TOKEN_BUDGETS 决定，避免在调用点复制常量。
        return {"concept_map": generator.generate(llm, context, "concept_map", timeout_sec=18.0)}
    return generator.generate_bundle(llm, context, card_types, timeout_sec=20.0)


def _quiz_payload_with_stable_answers(payload: Dict[str, Any], node_id: str, revision: int) -> Dict[str, Any]:
    result = dict(payload)
    questions = []
    for index, value in enumerate(result.get("questions", []), start=1):
        question = dict(value) if isinstance(value, dict) else value
        if not isinstance(question, dict):
            questions.append(question)
            continue
        options = list(question.get("options") or [])
        try:
            original = int(question.get("answer_index", 0))
        except (TypeError, ValueError):
            original = 0
        if len(options) == 4 and 0 <= original < 4:
            desired = _server_option_index(
                node_id=node_id,
                revision=revision,
                item_index=index,
                item_id=str(question.get("id") or ""),
            )
            old_order = [option_index for option_index in range(4) if option_index != original]
            old_order.insert(desired, original)
            old_to_new = {
                old_index: new_index
                for new_index, old_index in enumerate(old_order)
            }
            question["options"] = [options[old_index] for old_index in old_order]
            question["answer_index"] = desired
            raw_tags = question.get("distractor_error_tags")
            if isinstance(raw_tags, dict):
                remapped_tags: Dict[str, Any] = {}
                for raw_index, tag in raw_tags.items():
                    try:
                        old_index = int(raw_index)
                    except (TypeError, ValueError):
                        continue
                    if old_index == original or old_index not in old_to_new:
                        continue
                    remapped_tags[str(old_to_new[old_index])] = tag
                question["distractor_error_tags"] = remapped_tags
        questions.append(question)
    result["questions"] = questions
    return result


def _resource_card_from_generated(
    generated: GeneratedResourcePayload,
    *,
    context: Any,
    binding: Dict[str, Any],
    existing_cards: list[ResourceCard],
    force: bool,
    job_id: str,
) -> ResourceCard:
    card_type = generated.card_type
    quiz_revision = _diagnostic_quiz_revision(existing_cards, force) if card_type == "diagnostic_quiz" else 1
    payload = dict(generated.structured_payload)
    if card_type == "diagnostic_quiz":
        payload = _quiz_payload_with_stable_answers(payload, context.node_id, quiz_revision)
    # Older extension runtimes can still return Markdown without the shared
    # structured payload. Non-graded cards preserve it for the semantic gate;
    # quizzes always render from the server-owned structured fallback so raw
    # provider text can never carry answer keys into the public body.
    if (
        generated.fallback_reason == "legacy_unstructured_output"
        and card_type != "diagnostic_quiz"
    ):
        body_markdown = generated.body_markdown
    else:
        body_markdown = render_markdown(card_type, payload)
    if generated.source == "template":
        body_markdown = _truthful_generated_content(body_markdown, {"source": "template"})
    source_ids = {str(value) for value in payload.get("source_ref_ids", [])}
    source_refs = [
        dict(ref) for ref in context.source_refs
        if not source_ids or str(ref.get("id") or "") in source_ids
    ]
    generation = generated.generation_metadata()
    generation.update({"job_id": job_id, "phase": "concept" if card_type == "concept_map" else "supporting_bundle"})
    metadata: Dict[str, Any] = {
        **payload,
        "structured_payload": dict(payload),
        "body_markdown": body_markdown,
        "title": str(payload.get("title") or binding["title"]),
        "render_type": card_type,
        "resource_type": card_type,
        "contract_version": 2,
        "source_refs": source_refs,
        "generation": generation,
        "content_version": context.content_version,
        "knowledge_index_version": context.knowledge_index_version,
        "locale": context.locale,
        "semantic_binding": dict(binding),
        "difficulty_rationale": {
            "mastery": round(float(context.mastery), 3),
            "mastery_bucket": context.mastery_bucket,
            "learning_stage": context.learning_stage,
        },
        "personalization_basis": {
            "mastery_bucket": context.mastery_bucket,
            "error_signature": context.error_signature,
            "cognitive_style": context.cognitive_style,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_bank": {
            "status": context.question_bank_status,
            "collection_version": context.question_bank_version,
            "quiz_revision": context.question_bank_revision,
            "candidate_ids": [
                str(candidate.get("id") or "")
                for candidate in context.question_bank_candidates
                if isinstance(candidate, dict) and str(candidate.get("id") or "")
            ],
            "issue": context.question_bank_issue,
        },
    }
    if card_type == "diagnostic_quiz":
        metadata["quiz_revision"] = quiz_revision
        metadata["questions"] = payload.get("questions", [])
        metadata["question_set_digest"] = hashlib.sha256(
            json.dumps(
                payload.get("questions", []),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    elif card_type == "interactive_exercise":
        if not context.content_version.startswith("resource-v4"):
            metadata.update(_interactive_exercise_metadata(context.node_id, str(binding["title"])))
    elif card_type == "code_snippet":
        practice = dict(context.code_practice) if isinstance(context.code_practice, dict) else {}
        if not practice:
            practice = problem_binding_for_node(context.node_id)
        metadata.update({
            "practice": practice,
            "practice_problem_id": practice["problem_id"],
            "practice_version": practice["version"],
            "starter_code": practice["starter_code"],
        })
    resource_id = f"{context.node_id}_{card_type}_supp"
    if card_type == "diagnostic_quiz":
        if context.question_bank_version:
            bank_tag = hashlib.sha256(
                context.question_bank_version.encode("utf-8")
            ).hexdigest()[:10]
            resource_id = f"{resource_id}_qb{bank_tag}"
        if quiz_revision > 1:
            resource_id = f"{resource_id}_r{quiz_revision}"
    return ResourceCard(
        resource_id=resource_id,
        node_id=context.node_id,
        card_type=card_type,
        content=body_markdown,
        difficulty=max(0.1, min(1.0, 1.0 - float(context.mastery))),
        cognitive_style=context.cognitive_style,
        metadata=metadata,
    )


def _persist_ready_card(
    *,
    repo: ResourceGenerationRepo,
    job_id: str,
    session: Any,
    context: Any,
    binding: Dict[str, Any],
    card: ResourceCard,
    owner_id: Optional[str] = None,
) -> tuple[Optional[ResourceCard], Optional[Dict[str, Any]]]:
    state = session.agent_state
    job = repo.get_job(job_id) or {}
    if (
        owner_id
        and str(job.get("lease_owner") or "") != owner_id
    ):
        return None, {"code": "worker_lease_lost"}
    pipeline_version = str(job.get("pipeline_version") or context.content_version)
    quality = None
    if pipeline_version.startswith("resource-v4"):
        structured_payload = (
            card.metadata.get("structured_payload")
            if isinstance(card.metadata, dict)
            else None
        )
        if not isinstance(structured_payload, dict):
            return None, {"code": "structured_payload_missing"}
        quality = evaluate_resource_quality(
            card.card_type,
            structured_payload,
            context,
        )
        if quality.hard_fail or quality.gate_status == "failed":
            fallback_generated = ResourceGenerator().template(
                context,
                card.card_type,
                "resource_quality_gate_failed",
            )
            fallback = _resource_card_from_generated(
                fallback_generated,
                context=context,
                binding=binding,
                existing_cards=list(state.generated_resources.get(context.node_id, [])),
                force=False,
                job_id=job_id,
            )
            fallback_metadata = dict(fallback.metadata or {})
            fallback_metadata["repair_request"] = {
                "attempt": 1,
                "fields": sorted({
                    issue.split(":", 1)[0]
                    for issue in quality.issue_codes
                }),
                "issue_codes": list(quality.issue_codes),
            }
            fallback = fallback.model_copy(update={
                "resource_id": card.resource_id,
                "metadata": fallback_metadata,
            })
            fallback_payload = fallback_metadata.get("structured_payload")
            quality = evaluate_resource_quality(
                card.card_type,
                fallback_payload if isinstance(fallback_payload, dict) else {},
                context,
            )
            if quality.hard_fail or quality.gate_status == "failed":
                repo.record_quality_evaluation(
                    job_id,
                    card.card_type,
                    quality_version=str(job.get("quality_version") or QUALITY_VERSION),
                    gate_status=quality.gate_status,
                    score=quality.score,
                    dimensions=quality.dimensions,
                    issue_codes=quality.issue_codes,
                    artifact_digest=quality.artifact_digest,
                    content_hash=content_hash(fallback_payload),
                )
                return None, {
                    "code": "quality_gate_failed",
                    "issues": list(quality.issue_codes),
                }
            card = fallback

        metadata = dict(card.metadata or {})
        payload = dict(metadata.get("structured_payload") or {})
        payload["quality_profile"] = quality.to_dict()
        metadata["structured_payload"] = payload
        metadata["quality_profile"] = quality.to_dict()
        metadata["quality_status"] = quality.gate_status
        rendered = render_markdown(card.card_type, payload)
        generation = metadata.get("generation")
        if isinstance(generation, dict):
            rendered = _truthful_generated_content(rendered, generation)
        card = card.model_copy(update={
            "content": rendered,
            "metadata": metadata,
        })

    validation_pipeline = get_validation_pipeline()
    validation_started = time.perf_counter()
    validated, validation = validation_pipeline.validate_resource_card(card)
    observe_metric(
        "resource.generation.validation_ms",
        round((time.perf_counter() - validation_started) * 1000, 3),
        card_type=card.card_type,
    )
    if validated is None:
        issue_codes = _record_resource_rejection(state, context.node_id, card.card_type, validation, stage="resource_job_output")
        fallback_generation = _fallback_generation(dict(card.metadata.get("generation") or {}), issue_codes)
        fallback_generated = replace(
            ResourceGenerator().template(
                context,
                card.card_type,
                str(fallback_generation.get("fallback_reason") or "resource_validation_failed"),
            ),
            fallback_reason=str(fallback_generation.get("fallback_reason") or "resource_validation_failed"),
            validation_issues=tuple(issue_codes),
        )
        fallback = _resource_card_from_generated(
            fallback_generated,
            context=context,
            binding=binding,
            existing_cards=list(state.generated_resources.get(context.node_id, [])),
            force=False,
            job_id=job_id,
        )
        fallback_metadata = dict(fallback.metadata or {})
        fallback_provenance = dict(fallback_metadata.get("generation") or {})
        fallback_provenance.update(fallback_generation)
        fallback_metadata["generation"] = fallback_provenance
        if card.card_type == "diagnostic_quiz":
            fallback_metadata["quiz_revision"] = int(card.metadata.get("quiz_revision") or 1)
        fallback = fallback.model_copy(update={"resource_id": card.resource_id, "metadata": fallback_metadata})
        validated, fallback_validation = validation_pipeline.validate_resource_card(fallback)
        if validated is None:
            fallback_codes = _record_resource_rejection(state, context.node_id, card.card_type, fallback_validation, stage="resource_job_template")
            return None, {"code": "validation_failed", "issues": issue_codes + fallback_codes}
    contract_payload = resource_contract_from_card(validated).model_dump()
    if pipeline_version.startswith("resource-v4"):
        structured_contract = contract_payload.get("structured_payload")
        structured_contract = (
            structured_contract
            if isinstance(structured_contract, dict)
            else {}
        )
        if (
            not contract_payload.get("source_refs")
            or not structured_contract.get("evidence_map")
        ):
            incr_metric(
                "resource_unattributed_publication_total",
                card_type=validated.card_type,
                gate_status="blocked",
            )
            return None, {
                "code": "publication_attribution_missing",
            }
    quality_result = quality.to_dict() if quality is not None else {}
    published = repo.mark_card_ready(
        job_id,
        validated.card_type,
        contract_payload,
        quality_result=quality_result,
        blueprint_snapshot=(
            validated.metadata.get("structured_payload", {}).get("learning_blueprint")
            if validated.card_type == "concept_map"
            else context.blueprint_snapshot
        ) or {},
        publication_version=pipeline_version,
        degraded_reason=(
            quality.gate_status
            if quality is not None and quality.gate_status != "normal"
            else None
        ),
        owner_id=owner_id,
    )
    if published is None:
        return None, {"code": "worker_lease_lost"}
    if quality is not None:
        repo.record_quality_evaluation(
            job_id,
            validated.card_type,
            quality_version=str(job.get("quality_version") or QUALITY_VERSION),
            gate_status=quality.gate_status,
            score=quality.score,
            dimensions=quality.dimensions,
            issue_codes=quality.issue_codes,
            artifact_digest=quality.artifact_digest,
            content_hash=content_hash(contract_payload),
        )
    shadow = str(job.get("exposure_mode") or "") == "shadow"
    if not shadow:
        started = time.perf_counter()
        try:
            upsert_resource_card(state, validated)
            persist_session(session)
            observe_metric(
                "resource.generation.persist_ms",
                round((time.perf_counter() - started) * 1000, 3),
            )
        except Exception as exc:
            # The normalized card ledger and SSE event are already committed.
            # Session projection failures are repairable and must not turn a
            # successfully published card into a contradictory card_failed.
            state.record_error(
                f"resource_session_projection_failed:{context.node_id}:"
                f"{card.card_type}:{type(exc).__name__}"
            )
            incr_metric(
                "resource.generation.session_projection_failed_total",
                card_type=card.card_type,
            )
        try:
            _store_card_in_caches(repo, context, validated)
        except Exception as exc:
            # Cache loss only costs a later cache miss; PostgreSQL remains the
            # authoritative publication ledger.
            state.record_error(
                f"resource_cache_write_failed:{context.node_id}:"
                f"{card.card_type}:{type(exc).__name__}"
            )
            incr_metric(
                "resource.generation.cache_write_failed_total",
                card_type=card.card_type,
            )
    return validated, None


def run_generation_job(job_id: str, *, repo: Optional[ResourceGenerationRepo] = None) -> Optional[Dict[str, Any]]:
    """Run one job under the cross-process generation capacity limit."""
    repository = repo or get_resource_generation_repo()
    normalized_job_id = str(job_id)
    queued_job = repository.get_job(normalized_job_id)
    if queued_job is None or str(queued_job.get("status") or "") not in {"queued", "retrying"}:
        return queued_job

    acquire_slot = getattr(repository, "try_acquire_generation_slot", None)
    release_slot = getattr(repository, "release_generation_slot", None)
    lease = None
    if callable(acquire_slot):
        lease = acquire_slot(
            _resource_global_generation_max_concurrency(),
            concept_priority=_is_concept_priority_job(queued_job),
        )
        if lease is None:
            incr_metric(
                "resource.generation.global_slot_contention_total",
                lane="concept" if _is_concept_priority_job(queued_job) else "supporting",
            )
            _schedule_generation_job_retry(normalized_job_id, repo=repository)
            return queued_job

    try:
        return _run_claimed_generation_job(normalized_job_id, repo=repository)
    finally:
        if lease is not None and callable(release_slot):
            release_slot(lease)


def _run_claimed_generation_job(
    job_id: str,
    *,
    repo: Optional[ResourceGenerationRepo] = None,
    claimed_job: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Claim a slot-admitted job, then persist and publish each card."""
    repository = repo or get_resource_generation_repo()
    compatibility_owner = (
        f"compat:{os.getpid()}:{uuid.uuid4().hex}"
        if claimed_job is None
        else None
    )
    job = claimed_job or repository.claim_job(
        str(job_id),
        owner_id=compatibility_owner,
        lease_seconds=DEFAULT_LEASE_SECONDS,
    )
    if job is None:
        return repository.get_job(str(job_id))
    lease_owner = str(job.get("lease_owner") or "") or None
    if compatibility_owner is not None and lease_owner:
        # The dedicated worker heartbeats its own claim; the in-process
        # compatibility path must renew the lease itself or a healthy
        # 120s bundle outlives its 60s lease and gets stolen by recovery.
        _start_job_heartbeat(repository, str(job_id), lease_owner)

    class WorkerLeaseLost(RuntimeError):
        pass

    def require_lease(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if lease_owner and result is None:
            raise WorkerLeaseLost(
                f"Resource worker lease lost for job {job_id}"
            )
        return result or {}

    def transition_pipeline(pipeline_state: str) -> None:
        require_lease(
            repository.transition_pipeline_state(
                str(job_id),
                pipeline_state,
                owner_id=lease_owner,
            )
        )

    user_id = str(job["user_id"])
    course_id = str(job["course_id"])
    try:
        # State inspection and card persistence remain serialized. Model work
        # deliberately sits outside this lock so a long supporting bundle does
        # not delay a concept-map job for the same learner and course.
        with _resource_session_lock(user_id, course_id):
            session = get_session(user_id, course_id)
            state = session.agent_state
            runtime = get_runtime()
            locale = str(job.get("locale") or "zh-CN")
            context_started = time.perf_counter()
            transition_pipeline("retrieving")
            binding, context = _generation_context(
                runtime,
                state,
                course_id,
                str(job["node_id"]),
                locale,
                content_version=str(job.get("pipeline_version") or ""),
            )
            expected_knowledge_version = str(
                job.get("knowledge_index_version") or ""
            )
            if (
                expected_knowledge_version
                and context.knowledge_index_version != expected_knowledge_version
            ):
                return require_lease(repository.mark_failed(
                    str(job_id),
                    {
                        "code": "knowledge_index_version_changed",
                        "expected": expected_knowledge_version,
                        "actual": context.knowledge_index_version,
                    },
                    owner_id=lease_owner,
                ))
            observe_metric("resource.generation.context_ms", round((time.perf_counter() - context_started) * 1000, 3))
            requested = [card_type for card_type in job.get("card_types", []) if card_type in CARD_TYPES]
            force = bool(job.get("force"))
            request_params = job.get("request_params") if isinstance(job.get("request_params"), dict) else {}
            use_cache = bool(request_params.get("use_cache", True))
            existing_cards = [
                card
                for card in state.generated_resources.get(context.node_id, [])
                if _resource_card_language_valid(card, locale)
            ]
            existing_by_type = {card.card_type: card for card in existing_cards}
            unresolved: list[str] = []
            for card_type in requested:
                existing_card = existing_by_type.get(card_type)
                if (
                    not force
                    and existing_card is not None
                    and not _is_template_generated(existing_card.metadata)
                ):
                    repo_card = resource_contract_from_card(existing_card).model_dump()
                    require_lease(repository.mark_card_ready(
                        str(job_id),
                        card_type,
                        repo_card,
                        owner_id=lease_owner,
                    ))
                    continue
                if not force and use_cache:
                    try:
                        cached = _cache_card_for_context(repository, context, card_type)
                    except Exception as exc:
                        state.record_error(f"resource_cache_read_failed:{context.node_id}:{card_type}:{type(exc).__name__}")
                        incr_metric("resource.generation.cache_read_failed_total", card_type=card_type)
                        cached = None
                    if cached is not None:
                        incr_metric("resource.generation.cache_hit_total", card_type=card_type)
                        persisted, error = _persist_ready_card(
                            repo=repository,
                            job_id=str(job_id),
                            session=session,
                            context=context,
                            binding=binding,
                            card=cached,
                            owner_id=lease_owner,
                        )
                        if persisted is None:
                            if (error or {}).get("code") == "worker_lease_lost":
                                raise WorkerLeaseLost(
                                    f"Resource worker lease lost for job {job_id}"
                                )
                            require_lease(repository.mark_card_failed(
                                str(job_id),
                                card_type,
                                error or {"code": "cache_card_invalid"},
                                owner_id=lease_owner,
                            ))
                        continue
                if force and card_type == "diagnostic_quiz" and _active_retest_resource_id(state, context.node_id):
                    require_lease(repository.mark_card_failed(
                        str(job_id),
                        card_type,
                        {"code": "review_retest_active"},
                        owner_id=lease_owner,
                    ))
                    continue
                unresolved.append(card_type)

        try:
            deadline = datetime.fromisoformat(
                str(job.get("deadline_at") or "").replace("Z", "+00:00")
            )
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            deadline = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + BUNDLE_DEADLINE_SECONDS,
                tz=timezone.utc,
            )
        generation_calls_used = 0
        input_tokens_used = 0
        output_tokens_used = 0
        generation_call_budget = max(
            0,
            int(job.get("generation_call_budget") or MAX_GENERATION_CALLS),
        )
        input_token_budget = max(
            0,
            int(job.get("token_budget_input") or MAX_INPUT_TOKENS),
        )
        output_token_budget = max(
            0,
            int(job.get("token_budget_output") or MAX_OUTPUT_TOKENS),
        )
        cost_budget_microunits = max(
            0,
            int(job.get("cost_budget_microunits") or 0),
        )
        cost_used_microunits = 0
        prompt_tokens_per_call = max(
            1,
            len(
                json.dumps(
                    context.to_prompt_dict(),
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            )
            // 4,
        )

        def external_generation_allowed(call_cost: int = 1) -> bool:
            projected_cost = _resource_cost_microunits(
                input_tokens_used + prompt_tokens_per_call * call_cost,
                output_tokens_used,
            )
            return (
                datetime.now(timezone.utc) < deadline
                and generation_calls_used + call_cost <= generation_call_budget
                and input_tokens_used + prompt_tokens_per_call * call_cost
                <= input_token_budget
                and output_tokens_used < output_token_budget
                and (
                    cost_budget_microunits <= 0
                    or projected_cost <= cost_budget_microunits
                )
            )

        def persist_budget_progress() -> None:
            nonlocal cost_used_microunits
            cost_used_microunits = _resource_cost_microunits(
                input_tokens_used,
                output_tokens_used,
            )
            forecast_ratio = (
                cost_used_microunits / cost_budget_microunits
                if cost_budget_microunits > 0
                else 0.0
            )
            set_metric(
                "resource_cost_forecast_ratio",
                forecast_ratio,
            )
            set_metric(
                "resource_cost_used_microunits",
                float(cost_used_microunits),
            )
            require_lease(repository.update_job(
                    str(job_id),
                    progress={
                        "generation_calls_used": generation_calls_used,
                        "generation_call_budget": generation_call_budget,
                        "input_tokens_used": input_tokens_used,
                        "input_token_budget": input_token_budget,
                        "output_tokens_used": output_tokens_used,
                        "output_token_budget": output_token_budget,
                        "cost_used_microunits": cost_used_microunits,
                        "cost_budget_microunits": cost_budget_microunits,
                        "cost_forecast_ratio": round(forecast_ratio, 6),
                        "deadline_at": deadline.isoformat(),
                    },
                    owner_id=lease_owner,
                )
            )

        def process(generated: GeneratedResourcePayload) -> bool:
            card_type = generated.card_type
            try:
                repository.record_attempt(
                    str(job_id),
                    card_type,
                    "generation",
                    provider=str(generated.provider or ""),
                    model=str(generated.model or ""),
                    input_tokens=max(0, int(generated.input_tokens or 0)),
                    output_tokens=max(0, int(generated.output_tokens or 0)),
                    elapsed_ms=float(generated.elapsed_ms or 0.0),
                    issue_code=str(generated.fallback_reason or ""),
                    artifact_version=str(job.get("prompt_version") or ""),
                    content_hash=content_hash(generated.structured_payload),
                )
                with _resource_session_lock(user_id, course_id):
                    state = session.agent_state
                    card = _resource_card_from_generated(
                        generated,
                        context=context,
                        binding=binding,
                        existing_cards=list(state.generated_resources.get(context.node_id, [])),
                        force=force,
                        job_id=str(job_id),
                    )
                    persisted, error = _persist_ready_card(
                        repo=repository,
                        job_id=str(job_id),
                        session=session,
                        context=context,
                        binding=binding,
                        card=card,
                        owner_id=lease_owner,
                    )
                    if persisted is None:
                        if (error or {}).get("code") == "worker_lease_lost":
                            raise WorkerLeaseLost(
                                f"Resource worker lease lost for job {job_id}"
                            )
                        require_lease(repository.mark_card_failed(
                            str(job_id),
                            card_type,
                            error or {"code": "card_persist_failed"},
                            owner_id=lease_owner,
                        ))
                        return False
                    return True
            except WorkerLeaseLost:
                raise
            except Exception as exc:
                with _resource_session_lock(user_id, course_id):
                    session.agent_state.record_error(
                        f"resource_generation_card_failed:{context.node_id}:{card_type}:{type(exc).__name__}"
                    )
                require_lease(repository.mark_card_failed(
                    str(job_id),
                    card_type,
                    {
                        "code": "card_exception",
                        "error": type(exc).__name__,
                    },
                    owner_id=lease_owner,
                ))
                return False

        completed_before_generation = set(
            (repository.get_job(str(job_id)) or {}).get("progress", {}).get("completed_card_types", [])
        )
        concept_ready = "concept_map" in completed_before_generation
        if "concept_map" in unresolved:
            transition_pipeline("blueprint")
            model_started = time.perf_counter()
            if external_generation_allowed():
                generated = _generate_phase(
                    runtime,
                    context,
                    ["concept_map"],
                ).get("concept_map")
                generation_calls_used += 1
                input_tokens_used += prompt_tokens_per_call
                if generated is not None:
                    output_tokens_used += max(
                        1,
                        len(
                            json.dumps(
                                generated.structured_payload,
                                ensure_ascii=False,
                                default=str,
                            ).encode("utf-8")
                        )
                        // 4,
                    )
            else:
                generated = ResourceGenerator().template(
                    context,
                    "concept_map",
                    "budget_or_deadline_exhausted",
                )
            persist_budget_progress()
            observe_metric("resource.generation.model_ms", round((time.perf_counter() - model_started) * 1000, 3), card_type="concept_map")
            if generated is None:
                require_lease(repository.mark_card_failed(
                    str(job_id),
                    "concept_map",
                    {"code": "generator_returned_no_card"},
                    owner_id=lease_owner,
                ))
            else:
                transition_pipeline("concept")
                concept_ready = process(generated)
                blueprint = generated.structured_payload.get("learning_blueprint")
                if concept_ready and isinstance(blueprint, dict):
                    context = replace(
                        context,
                        blueprint_snapshot=dict(blueprint),
                    )
        supporting = [card_type for card_type in unresolved if card_type != "concept_map"]
        if supporting:
            transition_pipeline("supporting")
            model_started = time.perf_counter()
            supporting_call_cost = sum((
                bool({"code_snippet", "video_summary"}.intersection(supporting)),
                "interactive_exercise" in supporting,
                "diagnostic_quiz" in supporting,
            ))
            if external_generation_allowed(supporting_call_cost):
                generated_cards = _generate_phase(runtime, context, supporting)
                generation_calls_used += supporting_call_cost
                input_tokens_used += (
                    prompt_tokens_per_call * supporting_call_cost
                )
                output_tokens_used += sum(
                    max(
                        1,
                        len(
                            json.dumps(
                                generated.structured_payload,
                                ensure_ascii=False,
                                default=str,
                            ).encode("utf-8")
                        )
                        // 4,
                    )
                    for generated in generated_cards.values()
                )
            else:
                generated_cards = {
                    card_type: ResourceGenerator().template(
                        context,
                        card_type,
                        "budget_or_deadline_exhausted",
                    )
                    for card_type in supporting
                }
            persist_budget_progress()
            observe_metric("resource.generation.model_ms", round((time.perf_counter() - model_started) * 1000, 3), card_type="supporting_bundle")
            transition_pipeline("validating")
            for card_type in supporting:
                generated = generated_cards.get(card_type)
                if generated is None:
                    require_lease(repository.mark_card_failed(
                        str(job_id),
                        card_type,
                        {"code": "generator_returned_no_card"},
                        owner_id=lease_owner,
                    ))
                else:
                    process(generated)

        follow_up_payload: Dict[str, Any] = {}
        auto_supporting_card_types = [
            card_type
            for card_type in request_params.get("auto_supporting_card_types", [])
            if card_type in CARD_TYPES and card_type != "concept_map"
        ]
        if concept_ready and auto_supporting_card_types:
            try:
                require_lease(repository.update_job(
                    str(job_id),
                    progress={},
                    owner_id=lease_owner,
                ))
                supporting_job = request_generation(
                    user_id,
                    course_id,
                    context.node_id,
                    card_types=auto_supporting_card_types,
                    force=False,
                    priority="supporting_bundle",
                    locale=context.locale,
                    use_cache=use_cache,
                    repo=repository,
                )
                follow_up_job_id = str(supporting_job.get("job_id") or "")
                if follow_up_job_id:
                    follow_up_payload = {
                        "follow_up_job_id": follow_up_job_id,
                        "follow_up_card_types": auto_supporting_card_types,
                    }
            except WorkerLeaseLost:
                raise
            except Exception as exc:
                with _resource_session_lock(user_id, course_id):
                    session.agent_state.record_error(
                        f"resource_supporting_bundle_enqueue_failed:{context.node_id}:{type(exc).__name__}"
                    )
                follow_up_payload = {"follow_up_error": type(exc).__name__}
                incr_metric("resource.generation.supporting_enqueue_failed_total")
        terminal_job = repository.get_job(str(job_id)) or {}
        terminal_progress = terminal_job.get("progress")
        terminal_progress = terminal_progress if isinstance(terminal_progress, dict) else {}
        if terminal_progress.get("failed_card_types"):
            return require_lease(
                repository.mark_partial(
                    str(job_id),
                    progress=terminal_progress,
                    event_payload=follow_up_payload,
                    owner_id=lease_owner,
                )
            )
        return require_lease(
            repository.mark_completed(
                str(job_id),
                event_payload=follow_up_payload,
                owner_id=lease_owner,
            )
        )
    except WorkerLeaseLost:
        log_event(
            "resource_worker.lease_fenced",
            level="warning",
            job_id=str(job_id),
            owner_id=lease_owner,
        )
        return repository.get_job(str(job_id))
    except Exception as exc:
        error = {"code": "job_exception", "error": type(exc).__name__}
        current = repository.get_job(str(job_id)) or {}
        if int(current.get("retry_count") or 0) < int(current.get("max_retries") or 0):
            retried = repository.retry_job(
                str(job_id),
                error=error,
                owner_id=lease_owner,
            )
            if retried is not None:
                if claimed_job is None:
                    _submit_generation_job(
                        str(job_id),
                        repo=repository,
                        replace_active=True,
                    )
                return retried
        return repository.mark_failed(
            str(job_id),
            error,
            owner_id=lease_owner,
        )


def _repair_legacy_cards(
    session: Any,
    runtime: Any,
    course_id: str,
    node_id: str,
    requested_types: list[str],
) -> bool:
    """Repair older persisted cards only for synchronous compatibility calls."""
    state = session.agent_state
    binding = _canonical_node_binding(runtime, course_id, node_id)
    pipeline = get_validation_pipeline()
    repaired = False
    for existing in list(state.generated_resources.get(node_id, [])):
        if existing.card_type not in requested_types:
            continue
        bound = _with_semantic_binding(existing, binding)
        bound = _refresh_unconsumed_diagnostic_metadata(state, bound, binding)
        bound, practice_changed = _refresh_interactive_exercise_metadata(bound, binding)
        validated, validation = pipeline.validate_resource_card(bound)
        if validated is not None:
            if practice_changed or validated.metadata != existing.metadata:
                upsert_resource_card(state, validated)
                repaired = repaired or practice_changed
            continue
        issue_codes = _record_resource_rejection(state, node_id, existing.card_type, validation, stage="legacy_resource_read")
        fallback = _resource_card(
            resource_id=existing.resource_id,
            binding=binding,
            card_type=existing.card_type,
            content=_bound_template_content(binding, existing.card_type),
            difficulty=existing.difficulty,
            cognitive_style=existing.cognitive_style,
            quiz_revision=int((existing.metadata or {}).get("quiz_revision", 1) or 1),
            generation=_fallback_generation(dict((existing.metadata or {}).get("generation") or {}), issue_codes),
        )
        validated, fallback_validation = pipeline.validate_resource_card(fallback)
        if validated is not None:
            upsert_resource_card(state, validated)
            repaired = True
        else:
            _record_resource_rejection(state, node_id, existing.card_type, fallback_validation, stage="legacy_resource_template")
    if repaired:
        persist_session(session)
    return repaired


def generate_current_node_resources(
    user_id: str,
    course_id: str = "data_structures",
    node_id: Optional[str] = None,
    force: bool = False,
    include_legacy: bool = False,
    card_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous compatibility bridge over the job-based generation path."""
    requested_types, error = _normalise_requested_types(card_type=card_type)
    if error:
        return {"error": error, "status_code": 400}
    session = get_session(user_id, course_id)
    target_node = str(node_id or session.agent_state.current_node_id or (session.agent_state.active_path[0] if session.agent_state.active_path else "") or "")
    if not target_node:
        return {"error": "缺少学习节点标识。", "status_code": 400}
    repaired = False
    if not force:
        repaired = _repair_legacy_cards(session, get_runtime(), course_id, target_node, requested_types or [])
    requested = request_generation(
        user_id,
        course_id,
        target_node,
        card_types=requested_types,
        force=force,
        priority="legacy_sync",
        use_cache=False,
        submit=False,
    )
    if requested.get("status_code"):
        return requested
    job_id = requested.get("job_id")
    if job_id:
        run_generation_job(str(job_id))
    visible_types = requested.get("requested_card_types") or requested_types or []
    payload = get_node_resources(
        user_id,
        course_id,
        target_node,
        card_types=visible_types,
        include_legacy=include_legacy,
    )
    if payload.get("status_code"):
        return payload
    payload["status"] = "repaired_fallback" if repaired else ("generated" if job_id else "already_exists")
    generations = {
        card.card_type: dict((card.metadata or {}).get("generation") or {})
        for card in session.agent_state.generated_resources.get(target_node, [])
        if card.card_type in visible_types
    }
    _attach_generation_summary(payload, generations)
    if requested.get("preserved_retest_resource_id"):
        payload["preserved_retest_resource_id"] = requested["preserved_retest_resource_id"]
    return payload
