"""Fast local validation for structured generated resource payloads."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.validation.language import non_chinese_resource_fields

from .context import ResourceContext
from .schemas import CARD_TYPES, coerce_payload


# The schema caps snippets at 12,000 characters. These secondary limits keep
# parser work bounded even for multi-byte input or very many tiny lines.
_MAX_PYTHON_SOURCE_BYTES = 16 * 1024
_MAX_PYTHON_SOURCE_LINES = 600

_MERMAID_SHAPED_NODE_RE = re.compile(
    r"(?<![\w-])([A-Za-z][A-Za-z0-9_-]*)\s*(?=\[|\(\(|\{|\(\s)"
)
_MERMAID_EDGE_RE = re.compile(
    r"(?P<source>[A-Za-z][A-Za-z0-9_-]*)\s*(?:-->\|[^|\r\n]{1,120}\||-->|-\.->|==>|---)\s*"
    r"(?P<target>[A-Za-z][A-Za-z0-9_-]*)"
)
_MERMAID_LABELED_EDGE_RE = re.compile(r"-->(?:\|[^|\r\n]{1,120}\|)")


def _mermaid_graph_metrics(source: str) -> tuple[set[str], list[tuple[str, str]], int]:
    """Extract bounded structural metrics without trying to execute Mermaid."""
    nodes = set(_MERMAID_SHAPED_NODE_RE.findall(source))
    edges = [
        (match.group("source"), match.group("target"))
        for match in _MERMAID_EDGE_RE.finditer(source)
    ]
    labeled_edges = len(_MERMAID_LABELED_EDGE_RE.findall(source))
    return nodes, edges, labeled_edges


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: str = ""


@dataclass(frozen=True)
class ResourcePayloadValidation:
    payload: dict[str, Any] | None
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.payload is not None and not self.issues


def _source_ids(context: ResourceContext) -> set[str]:
    return {
        str(ref.get("id") or "")
        for ref in context.source_refs
        if isinstance(ref, dict) and ref.get("id")
    }


def _validate_python(code: str) -> ValidationIssue | None:
    if len(code.encode("utf-8")) > _MAX_PYTHON_SOURCE_BYTES:
        return ValidationIssue(
            "code_too_large",
            "Generated Python exceeds the local validation size limit.",
            "code",
        )
    if code.count("\n") + 1 > _MAX_PYTHON_SOURCE_LINES:
        return ValidationIssue(
            "code_too_many_lines",
            "Generated Python exceeds the local validation line limit.",
            "code",
        )
    try:
        # ast.parse checks syntax only; generated code is never imported or
        # executed by the validation path.
        ast.parse(code, filename="<generated-resource>", mode="exec")
    except SyntaxError as exc:
        return ValidationIssue(
            "code_syntax_invalid",
            f"Generated Python does not parse: {exc.msg}",
            "code",
        )
    except (MemoryError, OverflowError, RecursionError, ValueError, TypeError) as exc:
        return ValidationIssue(
            "code_syntax_validation_failed",
            f"Generated Python could not be safely parsed: {type(exc).__name__}",
            "code",
        )
    return None


def _validate_semantics(
    card_type: str,
    payload: dict[str, Any],
    context: ResourceContext,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if context.locale.lower().startswith("zh"):
        for field_name in non_chinese_resource_fields(payload):
            issues.append(ValidationIssue(
                "learner_content_not_chinese",
                "Learner-visible resource prose must be Chinese; code, formulas and proper names are exempt.",
                field_name,
            ))
    ref_ids = payload.get("source_ref_ids") or []
    known_refs = _source_ids(context)
    grounding_ids = set(context.grounding_ref_ids)
    if not grounding_ids and not context.knowledge_refs:
        pass  # development / in-memory mode: skip source-ref checks
    else:
        if not ref_ids:
            issues.append(ValidationIssue("source_refs_missing", "At least one source reference is required.", "source_ref_ids"))
        elif any(ref_id not in known_refs for ref_id in ref_ids):
            issues.append(ValidationIssue("source_ref_unknown", "A source reference is not in the generation context.", "source_ref_ids"))

    if grounding_ids and not grounding_ids.intersection(str(ref_id) for ref_id in ref_ids):
        issues.append(ValidationIssue(
            "knowledge_source_required",
            "At least one citation must reference supplied knowledge-base evidence.",
            "source_ref_ids",
        ))

    if context.content_version.startswith("resource-v4"):
        objective_ids = [
            str(value)
            for value in payload.get("objective_ids", [])
            if str(value).strip()
        ]
        evidence_map = payload.get("evidence_map")
        evidence_map = evidence_map if isinstance(evidence_map, dict) else {}
        if not objective_ids:
            issues.append(ValidationIssue(
                "objective_ids_missing",
                "v4 cards must bind at least one blueprint objective.",
                "objective_ids",
            ))
        if str(payload.get("content_language") or "") != context.locale:
            issues.append(ValidationIssue(
                "content_language_mismatch",
                "Learner-visible content must use the requested locale.",
                "content_language",
            ))
        mapped_ids = {
            str(ref_id)
            for values in evidence_map.values()
            if isinstance(values, list)
            for ref_id in values
        }
        if not evidence_map:
            issues.append(ValidationIssue(
                "evidence_map_missing",
                "v4 cards require field-level evidence mappings.",
                "evidence_map",
            ))
        elif any(ref_id not in known_refs for ref_id in mapped_ids):
            issues.append(ValidationIssue(
                "evidence_map_unknown",
                "Evidence maps may only use real source ids from the context.",
                "evidence_map",
            ))
        required_evidence_fields = {
            "concept_map": {"definition", "constraints", "mechanism"},
            "code_snippet": {"scenario", "explanation", "complexity_notes"},
            "interactive_exercise": {"goal", "prompt", "solution_outline"},
            "video_summary": {"summary", "key_points"},
            "diagnostic_quiz": {"questions", "after_quiz_guidance"},
        }[card_type]
        if not required_evidence_fields.issubset(evidence_map):
            issues.append(ValidationIssue(
                "factual_field_unmapped",
                "Every factual v4 field must map to evidence.",
                "evidence_map",
            ))

    if card_type == "concept_map":
        raw_diagram = str(payload.get("mermaid_source") or "")
        diagram = raw_diagram.lstrip().lower()
        if not (diagram.startswith("graph td") or diagram.startswith("flowchart td")):
            issues.append(ValidationIssue("mermaid_invalid", "Concept map Mermaid must start with graph TD or flowchart TD.", "mermaid_source"))
        elif context.content_version.startswith("resource-v4"):
            node_ids, edges, labeled_edges = _mermaid_graph_metrics(raw_diagram)
            edge_nodes = {node_id for edge in edges for node_id in edge}
            outgoing: dict[str, int] = {}
            for source, _target in edges:
                outgoing[source] = outgoing.get(source, 0) + 1
            if len(node_ids) < 8:
                issues.append(ValidationIssue(
                    "mermaid_too_shallow",
                    "v4 concept maps need at least eight labeled semantic nodes.",
                    "mermaid_source",
                ))
            if len(node_ids) > 14:
                issues.append(ValidationIssue(
                    "mermaid_too_dense",
                    "Concept maps must stay within fourteen nodes so the learner can scan them.",
                    "mermaid_source",
                ))
            if len(edges) < 7:
                issues.append(ValidationIssue(
                    "mermaid_edges_missing",
                    "v4 concept maps need at least seven directed relationships.",
                    "mermaid_source",
                ))
            if max(outgoing.values(), default=0) < 3:
                issues.append(ValidationIssue(
                    "mermaid_branch_missing",
                    "The core concept must branch into at least three learning relationships.",
                    "mermaid_source",
                ))
            if labeled_edges < 5:
                issues.append(ValidationIssue(
                    "mermaid_relation_labels_missing",
                    "At least five Mermaid edges must state the relationship between nodes.",
                    "mermaid_source",
                ))
            if not edge_nodes.issubset(node_ids):
                issues.append(ValidationIssue(
                    "mermaid_dangling_node",
                    "Every Mermaid edge endpoint must have a labeled node declaration.",
                    "mermaid_source",
                ))
        if context.content_version.startswith("resource-v4"):
            blueprint = payload.get("learning_blueprint")
            if not isinstance(blueprint, dict):
                issues.append(ValidationIssue(
                    "learning_blueprint_missing",
                    "The concept phase must emit a LearningBlueprint.",
                    "learning_blueprint",
                ))
            else:
                blueprint_objectives = {
                    str(value.get("id") or "")
                    for value in blueprint.get("objectives", [])
                    if isinstance(value, dict)
                }
                if not set(payload.get("objective_ids") or []).issubset(blueprint_objectives):
                    issues.append(ValidationIssue(
                        "objective_not_in_blueprint",
                        "Card objectives must be declared by the blueprint.",
                        "objective_ids",
                    ))
                for claim in blueprint.get("claims", []):
                    if not isinstance(claim, dict):
                        continue
                    claim_refs = {
                        str(value)
                        for value in claim.get("evidence_ids", [])
                    }
                    if not claim_refs or not claim_refs.issubset(known_refs):
                        issues.append(ValidationIssue(
                            "claim_evidence_invalid",
                            "Every blueprint claim must cite real evidence.",
                            "learning_blueprint.claims",
                        ))
    elif card_type == "code_snippet":
        if payload.get("language") == "python":
            syntax_issue = _validate_python(str(payload.get("code") or ""))
            if syntax_issue:
                issues.append(syntax_issue)
        if (
            context.content_version.startswith("resource-v4")
            and str(payload.get("example_binding") or "")
            == str(payload.get("practice_id") or "")
        ):
            issues.append(ValidationIssue(
                "code_example_leaks_practice",
                "The resource example must use a different binding from formal practice.",
                "example_binding",
            ))
    elif card_type == "interactive_exercise":
        if context.content_version.startswith("resource-v4"):
            if not payload.get("rubric"):
                issues.append(ValidationIssue(
                    "exercise_rubric_missing",
                    "v4 exercises require a scoring rubric.",
                    "rubric",
                ))
            if not payload.get("structured_checkpoints"):
                issues.append(ValidationIssue(
                    "exercise_checkpoints_missing",
                    "v4 exercises require structured checkpoints.",
                    "structured_checkpoints",
                ))
            hint_levels = payload.get("hint_levels")
            if not isinstance(hint_levels, dict) or set(hint_levels) != {
                "level_1",
                "level_2",
                "level_3",
            }:
                issues.append(ValidationIssue(
                    "exercise_hint_levels_invalid",
                    "v4 exercises require exactly three progressive hint levels.",
                    "hint_levels",
                ))
    elif card_type == "video_summary":
        url = str(payload.get("video_url") or "").strip()
        if url:
            trusted_refs = [
                ref
                for ref in context.knowledge_refs
                if isinstance(ref, dict)
            ]
            trusted_urls = {str(ref.get("video_url") or "").strip() for ref in trusted_refs}
            source_id = str(payload.get("video_source_id") or "").strip()
            matching_ref = next((ref for ref in trusted_refs if str(ref.get("video_url") or "").strip() == url), None)
            known_source_ids = {
                str(ref.get("video_source_id") or ref.get("id") or "").strip()
                for ref in trusted_refs
            }
            if url not in trusted_urls or matching_ref is None:
                issues.append(ValidationIssue(
                    "video_url_untrusted",
                    "Video links must come from the trusted video index in context.",
                    "video_url",
                ))
            elif not source_id or source_id not in known_source_ids:
                issues.append(ValidationIssue(
                    "video_source_missing",
                    "Video links must identify their trusted video-index source.",
                    "video_source_id",
                ))
            elif source_id not in {
                str(matching_ref.get("video_source_id") or matching_ref.get("id") or "").strip()
            }:
                issues.append(ValidationIssue(
                    "video_source_mismatch",
                    "The video source id does not match the trusted video link.",
                    "video_source_id",
                ))
            else:
                metadata = (
                    matching_ref.get("metadata")
                    if isinstance(matching_ref.get("metadata"), dict)
                    else {}
                )
                trusted_duration = int(
                    matching_ref.get("duration_minutes")
                    or metadata.get("duration_minutes")
                    or 0
                )
                trusted_timeline = (
                    matching_ref.get("timeline")
                    or metadata.get("timeline")
                    or []
                )
                if int(payload.get("duration_minutes") or 0) != trusted_duration:
                    issues.append(ValidationIssue(
                        "video_duration_mismatch",
                        "Video duration must come from the trusted video index.",
                        "duration_minutes",
                    ))
                if payload.get("timeline") != trusted_timeline:
                    issues.append(ValidationIssue(
                        "video_timeline_mismatch",
                        "Video timestamps must come from the trusted video index.",
                        "timeline",
                    ))
        if context.content_version.startswith("resource-v4"):
            media_status = str(payload.get("media_status") or "")
            if media_status == "no_trusted_video":
                if payload.get("timeline") or payload.get("video_url") or payload.get("video_source_id"):
                    issues.append(ValidationIssue(
                        "video_metadata_fabricated",
                        "No-video cards must not contain URL, source id or timeline.",
                        "media_status",
                    ))
                if not payload.get("reading_sequence"):
                    issues.append(ValidationIssue(
                        "reading_sequence_missing",
                        "No-video cards require a reading sequence.",
                        "reading_sequence",
                    ))
    elif card_type == "diagnostic_quiz":
        questions = payload.get("questions", [])
        levels = {str(question.get("level") or "") for question in questions}
        question_ids: set[str] = set()
        normalized_prompts: set[str] = set()
        known_bank_ids = {
            str(candidate.get("id") or "")
            for candidate in context.question_bank_candidates
            if isinstance(candidate, dict) and str(candidate.get("id") or "")
        }
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            question_id = str(question.get("id") or "").strip()
            if question_id in question_ids:
                issues.append(ValidationIssue(
                    "quiz_question_id_duplicate",
                    "Diagnostic question ids must be unique within one quiz.",
                    f"questions.{index}.id",
                ))
            question_ids.add(question_id)
            normalized_prompt = re.sub(
                r"\W+",
                "",
                str(question.get("prompt") or "").casefold(),
                flags=re.UNICODE,
            )
            if normalized_prompt in normalized_prompts:
                issues.append(ValidationIssue(
                    "quiz_question_duplicate",
                    "Diagnostic questions must not repeat the same normalized prompt.",
                    f"questions.{index}.prompt",
                ))
            normalized_prompts.add(normalized_prompt)
            source_question_ids = {
                str(value).strip()
                for value in question.get("source_question_ids", [])
                if str(value).strip()
            }
            if source_question_ids and not source_question_ids.issubset(known_bank_ids):
                issues.append(ValidationIssue(
                    "quiz_question_bank_source_unknown",
                    "Question-bank provenance may only reference supplied candidate ids.",
                    f"questions.{index}.source_question_ids",
                ))
            visible_text = "\n".join([
                str(question.get("prompt") or ""),
                *[str(option) for option in question.get("options", [])],
            ])
            if "[OBJECT]" in visible_text.upper():
                issues.append(ValidationIssue(
                    "quiz_missing_asset_placeholder",
                    "Questions with missing image or formula placeholders cannot be published.",
                    f"questions.{index}",
                ))
        required = {"concept", "understanding", "application"}
        if not required.issubset(levels):
            issues.append(ValidationIssue(
                "quiz_levels_missing",
                "Diagnostic quiz must cover concept, understanding and application levels.",
                "questions",
            ))
        if context.content_version.startswith("resource-v4"):
            required_v4 = {
                "concept",
                "understanding",
                "application",
                "boundary",
                "transfer",
            }
            if not 5 <= len(questions) <= 7 or not required_v4.issubset(levels):
                issues.append(ValidationIssue(
                    "quiz_v4_coverage_invalid",
                    "v4 diagnostics require 5-7 questions covering all five levels.",
                    "questions",
                ))
            for index, question in enumerate(questions):
                tags = (
                    question.get("distractor_error_tags")
                    if isinstance(question, dict)
                    else {}
                )
                try:
                    answer_index = int(question.get("answer_index"))
                except (TypeError, ValueError, AttributeError):
                    answer_index = -1
                expected_tag_keys = {
                    str(option_index)
                    for option_index in range(4)
                    if option_index != answer_index
                }
                if not isinstance(tags, dict) or set(tags) != expected_tag_keys:
                    issues.append(ValidationIssue(
                        "quiz_distractor_tags_missing",
                        "Every diagnostic distractor, and only distractors, must map to an error tag.",
                        f"questions.{index}.distractor_error_tags",
                    ))
            # Detect generic / meta-cognitive distractors that are not
            # topic-specific technical claims.
            _GENERIC_DISTRACTOR_RE = re.compile(
                r"只背诵|套用.*模板|忽略.*状态变化|直接套用"
                r"|以上都不对|以上全对"
                r"|^与.{0,8}无关[，。]?$"
                r"|^所有.*都是.{0,10}$|^总是最优$|^仅适用于.{0,10}$"
                r"|不检查.*条件|猜测结果",
            )
            for q_idx, question in enumerate(questions):
                if not isinstance(question, dict):
                    continue
                answer_index = question.get("answer_index")
                for o_idx, option in enumerate(question.get("options", []) or []):
                    if o_idx == answer_index:
                        continue
                    option_str = str(option).strip()
                    if _GENERIC_DISTRACTOR_RE.search(option_str):
                        issues.append(ValidationIssue(
                            "quiz_distractor_generic",
                            f"Option at questions.{q_idx}.options[{o_idx}] appears "
                            f"generic or meta-cognitive: '{option_str[:80]}'",
                            f"questions.{q_idx}.options.{o_idx}",
                        ))
    return issues


def validate_resource_payload(
    card_type: str,
    payload: Any,
    context: ResourceContext,
) -> ResourcePayloadValidation:
    """Validate schema and local semantic constraints without another LLM call."""
    if card_type not in CARD_TYPES:
        return ResourcePayloadValidation(
            payload=None,
            issues=[ValidationIssue("unsupported_card_type", f"Unsupported card type: {card_type}")],
        )
    try:
        normalized = coerce_payload(card_type, payload)
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                "schema_invalid",
                error.get("msg", "Invalid structured payload"),
                ".".join(str(part) for part in error.get("loc", ())),
            )
            for error in exc.errors()[:8]
        ]
        return ResourcePayloadValidation(payload=None, issues=issues)
    except (TypeError, ValueError) as exc:
        return ResourcePayloadValidation(
            payload=None,
            issues=[ValidationIssue("schema_invalid", str(exc))],
        )
    issues = _validate_semantics(card_type, normalized, context)
    return ResourcePayloadValidation(payload=normalized if not issues else None, issues=issues)
