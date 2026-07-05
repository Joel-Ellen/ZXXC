# -*- coding: utf-8 -*-
"""Output validation gate."""

from __future__ import annotations

from typing import Optional

from src.agents.validator_node import EntityExtractor, Pole1Gate, Pole2Gate
from src.llm.content_filter import ContentFilter
from src.state.agent_state import ResourceCard

from .result import ValidationDecision, ValidationResult


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
        result.metadata["resource_id"] = card.resource_id
        result.metadata["node_id"] = card.node_id
        result.metadata["resource_type"] = card.card_type
        return result
