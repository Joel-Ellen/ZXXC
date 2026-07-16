"""Fast local validation for structured generated resource payloads."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .context import ResourceContext
from .schemas import CARD_TYPES, coerce_payload


# The schema caps snippets at 12,000 characters. These secondary limits keep
# parser work bounded even for multi-byte input or very many tiny lines.
_MAX_PYTHON_SOURCE_BYTES = 16 * 1024
_MAX_PYTHON_SOURCE_LINES = 600


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
    ref_ids = payload.get("source_ref_ids") or []
    known_refs = _source_ids(context)
    if not ref_ids:
        issues.append(ValidationIssue("source_refs_missing", "At least one source reference is required.", "source_ref_ids"))
    elif any(ref_id not in known_refs for ref_id in ref_ids):
        issues.append(ValidationIssue("source_ref_unknown", "A source reference is not in the generation context.", "source_ref_ids"))

    grounding_ids = set(context.grounding_ref_ids)
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
        diagram = str(payload.get("mermaid_source") or "").lstrip().lower()
        if not (diagram.startswith("graph td") or diagram.startswith("flowchart td")):
            issues.append(ValidationIssue("mermaid_invalid", "Concept map Mermaid must start with graph TD or flowchart TD.", "mermaid_source"))
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
        levels = {str(question.get("level") or "") for question in payload.get("questions", [])}
        required = {"concept", "understanding", "application"}
        if not required.issubset(levels):
            issues.append(ValidationIssue(
                "quiz_levels_missing",
                "Diagnostic quiz must cover concept, understanding and application levels.",
                "questions",
            ))
        if context.content_version.startswith("resource-v4"):
            questions = payload.get("questions", [])
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
                if not isinstance(tags, dict) or len(tags) != 3:
                    issues.append(ValidationIssue(
                        "quiz_distractor_tags_missing",
                        "Every diagnostic distractor must map to an error tag.",
                        f"questions.{index}.distractor_error_tags",
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
