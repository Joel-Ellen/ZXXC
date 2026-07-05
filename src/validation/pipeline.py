# -*- coding: utf-8 -*-
"""Unified validation pipeline entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.state.agent_state import ResourceCard

from .input_guard import InputGuard
from .output_guard import OutputGuard
from .result import ValidationDecision, ValidationResult


@dataclass
class ValidationPipeline:
    nli_fn: Any = None

    def __post_init__(self) -> None:
        self.input_guard = InputGuard()
        self.output_guard = OutputGuard(nli_fn=self.nli_fn)

    def validate_input(self, text: str = "", payload: Optional[Dict[str, Any]] = None, field: str = "input") -> ValidationResult:
        result = ValidationResult()
        if payload is not None:
            result.merge(self.input_guard.validate_payload(payload))
        if text:
            result.merge(self.input_guard.validate_text(text, field=field))
        return result

    def validate_output_text(self, text: str, output_type: str = "text", ground_truth_context: str = "") -> ValidationResult:
        return self.output_guard.validate_text(text, output_type=output_type, ground_truth_context=ground_truth_context)

    def validate_resource_card(self, card: ResourceCard, ground_truth_context: str = "") -> Tuple[Optional[ResourceCard], ValidationResult]:
        result = self.output_guard.validate_resource(card, ground_truth_context=ground_truth_context)
        metadata = dict(card.metadata or {})
        metadata["validation"] = result.to_contract_validation()
        metadata.setdefault("safety", {"status": "safe" if result.passed else "flagged", "issues": [issue.model_dump() for issue in result.issues]})

        if result.passed:
            if result.decision == ValidationDecision.REFINED and result.refined_text:
                card = card.model_copy(update={"content": result.refined_text, "metadata": metadata})
            else:
                card = card.model_copy(update={"metadata": metadata})
            return card, result

        metadata["rejected"] = True
        rejected_card = card.model_copy(update={"metadata": metadata})
        return None, result

    def validate_tutor_response(self, response: Dict[str, Any]) -> Tuple[Dict[str, Any], ValidationResult]:
        text = str((response or {}).get("text_explanation") or "")
        result = self.validate_output_text(text, output_type="tutor_response")
        next_response = dict(response or {})
        next_response["validation"] = result.to_contract_validation()
        if result.passed and result.refined_text:
            next_response["text_explanation"] = result.refined_text
        elif not result.passed:
            next_response["text_explanation"] = "Tutor response was blocked by validation. Please rephrase the question or try a narrower learning topic."
            next_response["blocked"] = True
        return next_response, result


_pipeline: Optional[ValidationPipeline] = None


def get_validation_pipeline(nli_fn: Any = None) -> ValidationPipeline:
    global _pipeline
    if _pipeline is None or nli_fn is not None:
        _pipeline = ValidationPipeline(nli_fn=nli_fn)
    return _pipeline
