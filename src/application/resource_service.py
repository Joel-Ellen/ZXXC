# -*- coding: utf-8 -*-
"""Resource lookup and regeneration for the current learning node."""

from __future__ import annotations

import inspect
import re
import time
from typing import Any, Dict, Optional

from src.adapters.domain_to_response import resource_response
from src.adapters.state_to_domain import resource_contract_from_card
from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.state.agent_state import ResourceCard
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


_TEMPLATE_FALLBACK_NOTICE = (
    "> Generation status: local fallback template. "
    "This card was not produced by a model response.\n\n"
)

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
    get_local_graph = getattr(kg, "get_local_graph", None)
    if callable(get_local_graph):
        try:
            nodes, _ = get_local_graph(course_id)
            canonical_node = next(
                (node for node in nodes if str(getattr(node, "node_id", "")) == node_id),
                None,
            )
        except Exception:
            canonical_node = None

    if canonical_node is None:
        get_node_by_id = getattr(kg, "get_node_by_id", None)
        if callable(get_node_by_id):
            try:
                canonical_node = get_node_by_id(node_id, course_id)
            except TypeError:
                canonical_node = get_node_by_id(node_id)
            except Exception:
                canonical_node = None

    title = str(getattr(canonical_node, "title", "") or "").strip()
    canonical_course_id = str(getattr(canonical_node, "course_id", "") or course_id).strip()
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
    }


def _bound_template_content(binding: Dict[str, Any], card_type: str) -> str:
    """Return a deterministic template whose topic is the canonical node."""
    node_id = str(binding.get("node_id") or "")
    title = str(binding.get("title") or node_id)
    templates = {
        "concept_map": (
            f"## {title}\n\n"
            f"### Learning focus\n- Define the core idea of {title}.\n"
            f"- Identify its assumptions, constraints, and boundary cases.\n"
            f"- Apply the idea in one small example for node {node_id}."
        ),
        "code_snippet": (
            f"## {title}\n\n"
            f"```python\n# Practice scaffold for {title} ({node_id})\npass\n```"
        ),
        "interactive_exercise": (
            f"## {title}\n\n"
            f"Explain one defining property of {title}, then apply it to a small example."
        ),
        "video_summary": (
            f"## {title}\n\n"
            f"Review the definition, one representative example, and the main boundary of {title}."
        ),
        "diagnostic_quiz": (
            f"## {title}\n\n"
            f"1. Which statement best captures the defining constraint of {title}?"
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


def _requested_card_types(card_type: Optional[str]) -> tuple[Optional[list[str]], Optional[str]]:
    if card_type is None or not str(card_type).strip():
        return list(RESOURCE_CARD_ORDER), None
    normalized = str(card_type).strip()
    if normalized not in RESOURCE_CARD_ORDER:
        return None, f"Unsupported card_type '{normalized}'"
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
        correct_index = (sum(ord(char) for char in node_id) + index) % 4
        options = list(distractors)
        options.insert(correct_index, correct_option)
        questions.append(
            {
                "id": f"{node_id}-q{index}",
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
        "title": f"{title} diagnostic quiz",
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
    correct_index = (sum(ord(char) for char in node_id) + revision) % 4
    options = list(distractors)
    options.insert(correct_index, correct_option)
    return {
        "render_type": "targeted_practice",
        "practice_revision": revision,
        "questions": [
            {
                "id": f"{node_id}-targeted-practice-q1-v{revision}",
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
    for field_name in ("provider", "model", "attempt_count", "fallback_reason", "elapsed_ms"):
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


def generate_current_node_resources(
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
            return {"error": "node_id is required", "status_code": 400}

        requested_types, card_type_error = _requested_card_types(card_type)
        if card_type_error:
            return {"error": card_type_error, "status_code": 400}

        active_retest_resource_id = _active_retest_resource_id(state, target_node)
        if force and active_retest_resource_id and "diagnostic_quiz" in (requested_types or []):
            if str(card_type or "").strip() == "diagnostic_quiz":
                return {
                    "status": "review_retest_active",
                    "error": "An active review retest must be completed before replacing its diagnostic quiz.",
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

        existing_types = {card.card_type for card in existing}
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
