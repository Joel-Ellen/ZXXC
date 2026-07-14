# -*- coding: utf-8 -*-
"""Output validation gate."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from src.agents.validator_node import EntityExtractor, Pole1Gate, Pole2Gate
from src.llm.content_filter import ContentFilter
from src.state.agent_state import ResourceCard

from .result import ValidationDecision, ValidationResult


_SEMANTIC_SCOPE_LIMIT = 1600


def _normalize_semantic_text(value: object) -> str:
    """Normalize headings and keywords without depending on a tokenizer."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def validate_resource_semantic_binding(card: ResourceCard) -> ValidationResult:
    """Verify model text against the canonical node identity set by the server.

    A resource card does not prove its topic merely by carrying ``card.node_id``:
    that field is attached after generation.  The resource service therefore
    supplies a server-owned binding with the canonical course, node and title.
    The generated text must name that canonical title near the beginning before
    it can be persisted. A related keyword is not sufficient because an
    off-topic resource can mention terms such as time complexity in passing.
    """
    result = ValidationResult()
    metadata = card.metadata if isinstance(card.metadata, dict) else {}
    binding = metadata.get("semantic_binding")
    if not isinstance(binding, dict):
        # Older validator call sites do not yet have a course catalog binding.
        # The official resource service always supplies one and is fail-closed.
        result.metadata["semantic_binding"] = {"status": "not_requested"}
        return result

    course_id = str(binding.get("course_id") or "").strip()
    expected_node_id = str(binding.get("node_id") or "").strip()
    title = str(binding.get("title") or "").strip()
    verification = {
        "status": "rejected",
        "course_id": course_id,
        "node_id": expected_node_id,
        "title": title,
        "matched_by": "",
    }
    result.metadata["semantic_binding"] = verification

    if not course_id or not expected_node_id or not title:
        result.add_issue(
            "resource_semantic_binding_incomplete",
            "Resource semantic binding must include course_id, node_id and title.",
            field=card.card_type,
        )
        return result
    if expected_node_id != str(card.node_id or "").strip():
        result.add_issue(
            "resource_semantic_node_mismatch",
            "Resource node_id does not match its server-owned semantic binding.",
            field=card.card_type,
            expected_node_id=expected_node_id,
            actual_node_id=card.node_id,
        )
        return result

    searchable = _normalize_semantic_text(str(card.content or "")[:_SEMANTIC_SCOPE_LIMIT])
    normalized_title = _normalize_semantic_text(title)
    if normalized_title and normalized_title in searchable:
        verification.update({"status": "verified", "matched_by": "canonical_title"})
        return result

    result.add_issue(
        "resource_semantic_mismatch",
        f"Generated resource does not name node {expected_node_id} ({title}) in course {course_id}.",
        field=card.card_type,
        expected_course_id=course_id,
        expected_node_id=expected_node_id,
        expected_title=title,
    )
    return result


class OutputGuard:
    def __init__(self, nli_fn=None) -> None:
        self._pole1 = Pole1Gate()
        self._pole2 = Pole2Gate()
        self._nli_fn = nli_fn

    def validate_text(
        self,
        text: str,
        output_type: str = "text",
        ground_truth_context: str = "",
        allow_refinement: bool = True,
    ) -> ValidationResult:
        result = ValidationResult()
        text = str(text or "")
        is_safe, reason = ContentFilter.check_content(text)
        if not is_safe:
            sanitized = ContentFilter.sanitize(text)
            result.add_issue("unsafe_content", reason or "Unsafe content detected", field=output_type)
            result.sanitized_text = sanitized
            result.refined_text = sanitized
            result.decision = ValidationDecision.REFINED if allow_refinement and sanitized != text else ValidationDecision.REJECTED
            result.passed = bool(allow_refinement and sanitized != text)
            return result

        pole1 = self._pole1.validate(text, output_type)
        result.metadata["pole1"] = pole1.model_dump()
        if not pole1.passed:
            for err in pole1.code_ast_errors:
                result.add_issue("code_syntax_error", err, field=output_type)
            for err in pole1.formula_syntax_errors:
                result.add_issue("formula_syntax_error", err, field=output_type)
            return result

        if ground_truth_context:
            pole2 = self._pole2.validate(text, ground_truth_context, nli_fn=self._nli_fn)
            result.metadata["pole2"] = pole2.model_dump()
            if not pole2.passed:
                hallucinated = [chunk for chunk in pole2.chunk_results if chunk.is_hallucination]
                refined, rounds = self._pole2.refine(text, hallucinated, ground_truth_context)
                if allow_refinement and rounds > 0 and refined != text:
                    result.decision = ValidationDecision.REFINED
                    result.refined_text = refined
                    result.metadata["refinement_rounds"] = rounds
                    return result
                result.add_issue("factual_consistency_failed", pole2.diagnostic or "Factual consistency check failed", field=output_type)
                return result

        result.sanitized_text = text
        return result

    def validate_resource(self, card: ResourceCard, ground_truth_context: str = "") -> ValidationResult:
        result = self.validate_text(card.content, output_type=card.card_type, ground_truth_context=ground_truth_context)
        result.merge(validate_resource_semantic_binding(card))
        result.metadata["resource_id"] = card.resource_id
        result.metadata["node_id"] = card.node_id
        result.metadata["resource_type"] = card.card_type
        return result
