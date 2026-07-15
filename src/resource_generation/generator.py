"""Structured model invocation, parsing and deterministic fallback generation."""

from __future__ import annotations

import json
import inspect
import re
import time
from dataclasses import dataclass
from typing import Any

from .context import ResourceContext
from .prompts import TOKEN_BUDGETS, build_card_messages, build_supporting_bundle_messages, render_markdown
from .validator import ResourcePayloadValidation, validate_resource_payload


_TEMPLATE_NOTICE = "> Generation status: local fallback template. This card was not produced by a model response.\n\n"


@dataclass(frozen=True)
class GeneratedResourcePayload:
    card_type: str
    structured_payload: dict[str, Any]
    body_markdown: str
    source: str
    provider: str | None = None
    model: str | None = None
    attempt_count: int = 1
    fallback_reason: str | None = None
    validation_issues: tuple[str, ...] = ()
    elapsed_ms: float = 0.0

    def generation_metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "attempt_count": self.attempt_count,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.provider:
            data["provider"] = self.provider
        if self.model:
            data["model"] = self.model
        if self.fallback_reason:
            data["fallback_reason"] = self.fallback_reason
        if self.validation_issues:
            data["validation_issue_codes"] = list(self.validation_issues)
        return data


def extract_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _model_name(llm: Any) -> str | None:
    config = getattr(llm, "config", None)
    if isinstance(config, dict):
        name = str(config.get("model") or "").strip()
        return name or None
    return None


def _source_ref_ids(context: ResourceContext) -> list[str]:
    return context.grounding_ref_ids[:3] or [f"course:{context.course_id}:{context.node_id}"]


def _bind_source_ref_ids(payload: dict[str, Any], context: ResourceContext) -> list[str]:
    """Retain only server-known citations and require supplied grounding refs.

    A provider may select among retrieved source IDs, but it cannot replace
    those citations with the synthetic course-node ID or an invented reference.
    When it fails to nominate a retrieved source, the service attaches the
    bounded default evidence set instead of allowing a weak ``setdefault``
    escape hatch.
    """
    raw_ids = payload.get("source_ref_ids")
    proposed = raw_ids if isinstance(raw_ids, list) else []
    known = set(context.grounding_ref_ids)
    selected = list(dict.fromkeys(
        str(ref_id).strip()
        for ref_id in proposed
        if str(ref_id).strip() in known
    ))
    if known:
        return selected[:5] or _source_ref_ids(context)

    # A context without retrieved evidence remains compatible with legacy
    # course-node-only generation, but unknown provider IDs are still removed.
    course_id = f"course:{context.course_id}:{context.node_id}"
    return [course_id] if course_id in {
        str(ref.get("id") or "").strip()
        for ref in context.source_refs
        if isinstance(ref, dict)
    } else _source_ref_ids(context)


def _template_payload(context: ResourceContext, card_type: str) -> dict[str, Any]:
    title = context.node_title
    refs = _source_ref_ids(context)
    common = {"title": title, "source_ref_ids": refs}
    if card_type == "concept_map":
        return {
            **common,
            "render_type": card_type,
            "summary": f"Use {title} to reason about the stated course constraint before selecting an implementation.",
            "definition": f"{title} is the current course concept and should be explained from its invariant and use conditions.",
            "constraints": ["State the input assumptions before applying the concept."],
            "mechanism": ["Track the state that makes the concept valid."],
            "prerequisites": [item.get("title") or "Course prerequisite" for item in context.prerequisite_nodes[:2]] or ["The preceding course node"],
            "learning_objectives": [f"Explain the constraint behind {title}."],
            "sections": [{"heading": "Mechanism", "body": f"Relate each operation in {title} to the invariant it preserves."}],
            "bullets": ["Check assumptions, state, and boundary cases."],
            "common_misconceptions": ["Memorizing an operation without checking its precondition."],
            "counterexamples": ["A case that violates the prerequisite must not use the same method."],
            "transfer_questions": [f"Which new problem has the same core constraint as {title}?"],
            "review_prompts": ["Name the invariant and test one boundary case."],
            "mermaid_source": "graph TD\nA[Prerequisites] --> B[Definition]\nB --> C[Constraint]\nC --> D[Mechanism]\nD --> E[Application]",
        }
    if card_type == "code_snippet":
        return {
            **common,
            "render_type": card_type,
            "language": "python",
            "scenario": f"A small executable scaffold for tracing {title}.",
            "prerequisites": ["Read the input contract before execution."],
            "code": "def apply_concept(items):\n    if items is None:\n        return []\n    return list(items)",
            "boundary_tests": [
                {"name": "empty input", "input": "[]", "expected": "[]"},
            ],
            "walkthrough_steps": ["Check the input boundary before transforming data."],
            "explanation": "The fallback keeps an explicit input contract and a deterministic output.",
            "complexity_notes": ["Copying the sequence takes O(n) time and O(n) additional space."],
            "pitfalls": ["Assuming input exists without checking the contract."],
            "experiments": ["Add a test with one element and explain the invariant."],
        }
    if card_type == "interactive_exercise":
        return {
            **common,
            "render_type": card_type,
            "goal": f"Practice selecting {title} from its constraint rather than a memorized template.",
            "error_signature": context.error_signature,
            "prompt": f"Write the invariant for {title}, then test it on one normal and one boundary input.",
            "steps": ["State the input assumptions.", "Name the invariant.", "Trace one normal case.", "Trace one boundary case."],
            "checkpoints": ["The invariant remains true after every step."],
            "hints": ["Begin with the state that must be preserved.", "Compare the boundary case with the normal trace."],
            "solution_outline": "Map the condition to the invariant, then verify it with a trace.",
            "expected_outcome": "A short, checkable explanation of when the concept applies.",
        }
    if card_type == "video_summary":
        return {
            **common,
            "render_type": card_type,
            "summary": f"Review {title} by locating its definition, state changes and boundaries in a trusted course video.",
            "key_points": ["Watch for the invariant before the implementation details."],
            "timeline": [{"label": "00:00", "summary": "Identify the problem constraint and definition."}],
            "watch_focus": ["Pause when the state changes and predict the next step."],
            "review_questions": [f"Which condition determines whether {title} applies?"],
            "duration_minutes": 0,
            "video_url": None,
            "video_source_id": None,
        }
    return {
        **common,
        "render_type": "diagnostic_quiz",
        "questions": [
            {
                "id": f"{context.node_id}-concept-v1",
                "level": "concept",
                "prompt": f"Which statement best identifies the governing constraint of {title}?",
                "options": ["The stated course invariant", "Any memorized template", "The longest input", "A random operation order"],
                "answer_index": 0,
                "explanation": "The correct choice names the constraint that must remain true.",
                "skill_tag": "definition_and_constraint",
                "error_tags": ["definition"],
                "difficulty": "easy",
            },
            {
                "id": f"{context.node_id}-understanding-v1",
                "level": "understanding",
                "prompt": "What should be checked before applying the method?",
                "options": ["Its preconditions", "Only the final answer", "A preferred color", "The number of comments"],
                "answer_index": 0,
                "explanation": "Preconditions determine whether a method can preserve its invariant.",
                "skill_tag": "preconditions",
                "error_tags": ["precondition"],
                "difficulty": "medium",
            },
            {
                "id": f"{context.node_id}-application-v1",
                "level": "application",
                "prompt": "A boundary case violates a required assumption. What is the best response?",
                "options": ["Handle the boundary explicitly", "Apply the same method unchanged", "Ignore the input", "Guess the output"],
                "answer_index": 0,
                "explanation": "A violated assumption requires an explicit boundary decision.",
                "skill_tag": "boundary_reasoning",
                "error_tags": ["boundary"],
                "difficulty": "hard",
            },
        ],
        "pass_threshold": 0.65,
        "after_quiz_guidance": "Review the concept map and trace one boundary case before retrying.",
    }


class ResourceGenerator:
    """One structured generator shared by synchronous compatibility and jobs."""

    def _bind_context(self, payload: dict[str, Any], context: ResourceContext, card_type: str) -> dict[str, Any]:
        bound = dict(payload or {})
        bound["render_type"] = card_type
        bound.setdefault("title", context.node_title)
        bound["source_ref_ids"] = _bind_source_ref_ids(bound, context)
        return bound

    def _result_from_payload(
        self,
        card_type: str,
        payload: dict[str, Any],
        context: ResourceContext,
        *,
        source: str,
        provider: str | None = None,
        model: str | None = None,
        fallback_reason: str | None = None,
        elapsed_ms: float = 0.0,
    ) -> GeneratedResourcePayload:
        bound = self._bind_context(payload, context, card_type)
        validation: ResourcePayloadValidation = validate_resource_payload(card_type, bound, context)
        if validation.valid and validation.payload is not None:
            markdown = render_markdown(card_type, validation.payload)
            if source == "template":
                markdown = _TEMPLATE_NOTICE + markdown
            return GeneratedResourcePayload(
                card_type=card_type,
                structured_payload=validation.payload,
                body_markdown=markdown,
                source=source,
                provider=provider,
                model=model,
                fallback_reason=fallback_reason,
                elapsed_ms=elapsed_ms,
            )
        codes = tuple(issue.code for issue in validation.issues)
        fallback = _template_payload(context, card_type)
        fallback_validation = validate_resource_payload(card_type, fallback, context)
        # Template payloads are authored locally and kept valid. This guard
        # prevents a malformed future template from leaking an invalid card.
        if not fallback_validation.valid or fallback_validation.payload is None:
            raise RuntimeError(f"Local fallback validation failed for {card_type}: {codes}")
        return GeneratedResourcePayload(
            card_type=card_type,
            structured_payload=fallback_validation.payload,
            body_markdown=_TEMPLATE_NOTICE + render_markdown(card_type, fallback_validation.payload),
            source="template",
            fallback_reason=fallback_reason or "local_validation_failed",
            validation_issues=codes,
            elapsed_ms=elapsed_ms,
        )

    def template(self, context: ResourceContext, card_type: str, reason: str = "no_eligible_provider") -> GeneratedResourcePayload:
        return self._result_from_payload(
            card_type,
            _template_payload(context, card_type),
            context,
            source="template",
            fallback_reason=reason,
        )

    @staticmethod
    def _chat_sync(
        llm: Any,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        timeout_sec: float | None,
    ) -> Any:
        call = llm.chat_sync
        kwargs: dict[str, Any] = {
            "temperature": 0.25,
            "max_tokens": max_tokens,
            "json_mode": True,
        }
        try:
            parameters = inspect.signature(call).parameters.values()
            if timeout_sec is not None and any(
                parameter.name == "timeout_sec" or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            ):
                kwargs["timeout_sec"] = timeout_sec
        except (TypeError, ValueError):
            pass
        return call(messages, **kwargs)

    def generate(
        self,
        llm: Any,
        context: ResourceContext,
        card_type: str,
        *,
        max_tokens: int | None = None,
        timeout_sec: float | None = 18.0,
    ) -> GeneratedResourcePayload:
        started = time.monotonic()
        try:
            result = self._chat_sync(
                llm,
                build_card_messages(context, card_type),
                max_tokens=max_tokens or TOKEN_BUDGETS[card_type],
                timeout_sec=timeout_sec,
            )
            content = result.get("content", "") if isinstance(result, dict) else result
            payload = extract_json_object(content)
            if payload is None:
                return self.template(context, card_type, "invalid_json")
            return self._result_from_payload(
                card_type,
                payload,
                context,
                source="llm",
                provider=str(getattr(llm, "provider", "") or "") or None,
                model=_model_name(llm),
                elapsed_ms=round((time.monotonic() - started) * 1000, 3),
            )
        except Exception as exc:
            return self.template(context, card_type, f"provider_error:{type(exc).__name__}")

    def generate_bundle(
        self,
        llm: Any,
        context: ResourceContext,
        card_types: list[str],
        *,
        max_tokens: int | None = None,
        timeout_sec: float | None = 20.0,
    ) -> dict[str, GeneratedResourcePayload]:
        requested = list(dict.fromkeys(card_type for card_type in card_types if card_type != "concept_map"))
        if not requested:
            return {}
        started = time.monotonic()
        try:
            result = self._chat_sync(
                llm,
                build_supporting_bundle_messages(context, requested),
                max_tokens=max_tokens or TOKEN_BUDGETS["supporting_bundle"],
                timeout_sec=timeout_sec,
            )
            content = result.get("content", "") if isinstance(result, dict) else result
            raw_bundle = extract_json_object(content) or {}
        except Exception:
            raw_bundle = {}
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        provider = str(getattr(llm, "provider", "") or "") or None
        model = _model_name(llm)
        outputs: dict[str, GeneratedResourcePayload] = {}
        for card_type in requested:
            payload = raw_bundle.get(card_type)
            if not isinstance(payload, dict):
                outputs[card_type] = self.template(context, card_type, "bundle_missing_card")
                continue
            outputs[card_type] = self._result_from_payload(
                card_type,
                payload,
                context,
                source="llm",
                provider=provider,
                model=model,
                elapsed_ms=elapsed_ms,
            )
        return outputs
