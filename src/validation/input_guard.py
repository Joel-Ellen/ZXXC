# -*- coding: utf-8 -*-
"""Input validation gate."""

from __future__ import annotations

from typing import Any, Dict

from src.auth.prompt_defense import get_prompt_defense

from .result import ValidationDecision, ValidationResult


MAX_PAYLOAD_DEPTH = 8
MAX_PROMPT_LENGTH = 8000


def _payload_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_PAYLOAD_DEPTH:
        return depth
    if isinstance(value, dict):
        return max([depth, *(_payload_depth(v, depth + 1) for v in value.values())])
    if isinstance(value, list):
        return max([depth, *(_payload_depth(v, depth + 1) for v in value)])
    return depth


class InputGuard:
    def validate_text(self, text: str, field: str = "input", max_length: int = MAX_PROMPT_LENGTH) -> ValidationResult:
        result = ValidationResult()
        text = str(text or "")
        if len(text) > max_length:
            result.add_issue("input_too_long", f"{field} exceeds maximum length {max_length}", field=field, length=len(text))
            result.sanitized_text = text[:max_length]
            return result

        is_injection, reason = get_prompt_defense().detect_injection(text)
        if is_injection:
            result.add_issue("prompt_injection", reason or "Potential prompt injection detected", field=field)
            result.sanitized_text = get_prompt_defense().sanitize(text)
            return result

        result.sanitized_text = text
        return result

    def validate_payload(self, payload: Dict[str, Any], max_depth: int = MAX_PAYLOAD_DEPTH) -> ValidationResult:
        result = ValidationResult()
        if not isinstance(payload, dict):
            result.add_issue("invalid_payload", "Payload must be an object", field="payload")
            return result
        depth = _payload_depth(payload)
        if depth > max_depth:
            result.add_issue("payload_too_deep", f"Payload nesting depth {depth} exceeds {max_depth}", field="payload")
        return result
