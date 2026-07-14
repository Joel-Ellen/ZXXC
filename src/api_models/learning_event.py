# -*- coding: utf-8 -*-
"""Canonical learning-event DTOs used at the public session boundary.

The client may report an interaction, but it may not report a mastery score.
Only a terminal event carrying evidence that the server can independently
verify is eligible to affect mastery.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class LearningEventType(str, Enum):
    """The complete, stable vocabulary for learner activity."""

    LESSON_OPENED = "lesson_opened"
    CONTENT_VIEWED = "content_viewed"
    HINT_REQUESTED = "hint_requested"
    ANSWER_SELECTED = "answer_selected"
    ANSWER_SUBMITTED = "answer_submitted"
    CODE_RUN = "code_run"
    CODE_SUBMITTED = "code_submitted"
    LESSON_COMPLETED = "lesson_completed"
    REVIEW_COMPLETED = "review_completed"
    TUTOR_QUESTION = "tutor_question"


class QuizAnswer(BaseModel):
    """One selected option, later checked against a server-owned answer key."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    question_id: str = Field(
        default="",
        max_length=256,
        validation_alias=AliasChoices("question_id", "questionId", "id"),
    )
    answer_index: int = Field(
        default=-1,
        validation_alias=AliasChoices(
            "answer_index",
            "answerIndex",
            "selected_index",
            "selectedIndex",
            "selected_option_index",
            "selectedOptionIndex",
        ),
    )

    @field_validator("question_id", mode="before")
    @classmethod
    def normalize_question_id(cls, value: object) -> str:
        return str(value or "").strip()


class QuizCompletionEvidence(BaseModel):
    """Quiz evidence whose answer key remains under server control."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    evidence_type: str = Field(
        default="diagnostic_quiz",
        max_length=64,
        validation_alias=AliasChoices("evidence_type", "evidenceType", "type"),
    )
    resource_id: str = Field(
        default="",
        max_length=256,
        validation_alias=AliasChoices("resource_id", "resourceId"),
    )
    answers: list[QuizAnswer] = Field(default_factory=list, max_length=200)

    @field_validator("evidence_type", mode="before")
    @classmethod
    def normalize_evidence_type(cls, value: object) -> str:
        return str(value or "diagnostic_quiz").strip().lower().replace("-", "_")

    @field_validator("resource_id", mode="before")
    @classmethod
    def normalize_resource_id(cls, value: object) -> str:
        return str(value or "").strip()


class LearningEventRequest(BaseModel):
    """One normalized learner event.

    ``result`` deliberately contains concrete interaction evidence instead of a
    client-computed score.  For example, a completed diagnostic quiz should
    send ``{"answers": [{"question_id": "...", "selected_option_index": 1}]}``.
    Code runs may carry ``test_results`` for auditability, but client-reported
    test summaries are not sufficient to update mastery.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_id: str = Field(
        default="",
        max_length=128,
        validation_alias=AliasChoices("event_id", "eventId", "id"),
    )
    event_type: LearningEventType = Field(
        default=LearningEventType.LESSON_OPENED,
        validation_alias=AliasChoices("event_type", "eventType"),
    )
    user_id: str = Field(
        default="",
        max_length=128,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    course_id: str = Field(
        default="",
        max_length=128,
        validation_alias=AliasChoices("course_id", "courseId"),
    )
    node_id: str = Field(
        default="",
        max_length=256,
        validation_alias=AliasChoices("node_id", "nodeId", "current_node_id", "currentNodeId"),
    )
    resource_id: str = Field(
        default="",
        max_length=256,
        validation_alias=AliasChoices("resource_id", "resourceId"),
    )
    question_id: str = Field(
        default="",
        max_length=256,
        validation_alias=AliasChoices("question_id", "questionId"),
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        le=86_400_000,
        validation_alias=AliasChoices("duration_ms", "durationMs"),
    )
    attempt_number: int = Field(
        default=1,
        ge=1,
        le=10_000,
        validation_alias=AliasChoices("attempt_number", "attemptNumber"),
    )
    used_hint: bool = Field(
        default=False,
        validation_alias=AliasChoices("used_hint", "usedHint"),
    )
    result: dict[str, Any] = Field(default_factory=dict, max_length=128)
    completion_evidence: Optional[QuizCompletionEvidence] = Field(
        default=None,
        validation_alias=AliasChoices("completion_evidence", "completionEvidence", "evidence"),
    )

    # Compatibility is deliberately isolated here.  New callers must emit a
    # canonical event_type; legacy advancement calls still map safely to a
    # non-scoring event or a completed lesson with verifiable evidence.
    _LEGACY_EVENT_ALIASES: ClassVar[dict[str, LearningEventType]] = {
        "browse_node": LearningEventType.LESSON_OPENED,
        "browse": LearningEventType.LESSON_OPENED,
        "load_node": LearningEventType.LESSON_OPENED,
        "complete_learning": LearningEventType.LESSON_COMPLETED,
        "completed_learning": LearningEventType.LESSON_COMPLETED,
        "complete": LearningEventType.LESSON_COMPLETED,
        "diagnostic": LearningEventType.LESSON_COMPLETED,
        "tutor": LearningEventType.TUTOR_QUESTION,
    }

    _TERMINAL_EVENT_TYPES: ClassVar[frozenset[LearningEventType]] = frozenset({
        LearningEventType.LESSON_COMPLETED,
        LearningEventType.REVIEW_COMPLETED,
    })

    @model_validator(mode="before")
    @classmethod
    def normalize_envelope(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        has_canonical_type = "event_type" in payload or "eventType" in payload
        if not has_canonical_type:
            legacy_type = str(
                payload.get("interaction_type", payload.get("interactionType", "")) or ""
            ).strip().lower().replace("-", "_")
            if legacy_type:
                mapped = cls._LEGACY_EVENT_ALIASES.get(legacy_type)
                if mapped is not None:
                    payload["event_type"] = mapped.value

        raw_result = payload.get("result")
        if raw_result is None:
            raw_result = {}
        if not isinstance(raw_result, dict):
            raise ValueError("result must be an object")
        result = dict(raw_result)

        # Accept the old flat quiz payload, but place it in the canonical
        # result/evidence location.  Raw correctness/score remains ignored.
        if "answers" in payload and "answers" not in result:
            result["answers"] = payload.get("answers")
        if "test_results" in payload and "test_results" not in result:
            result["test_results"] = payload.get("test_results")
        if "testResults" in payload and "test_results" not in result:
            result["test_results"] = payload.get("testResults")
        payload["result"] = result

        has_evidence = any(
            key in payload for key in ("completion_evidence", "completionEvidence", "evidence")
        )
        if not has_evidence:
            nested_evidence = result.get("evidence")
            if isinstance(nested_evidence, dict):
                payload["completion_evidence"] = nested_evidence
                has_evidence = True

        if not has_evidence and result.get("answers") is not None:
            payload["completion_evidence"] = {
                "evidence_type": result.get("evidence_type", result.get("evidenceType", "diagnostic_quiz")),
                "resource_id": payload.get("resource_id", payload.get("resourceId", "")),
                "answers": result.get("answers", []),
            }

        return payload

    @field_validator(
        "event_id",
        "user_id",
        "course_id",
        "node_id",
        "resource_id",
        "question_id",
        mode="before",
    )
    @classmethod
    def normalize_identifier(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: object) -> object:
        if isinstance(value, LearningEventType):
            return value
        return str(value or LearningEventType.LESSON_OPENED.value).strip().lower().replace("-", "_")

    @property
    def is_terminal(self) -> bool:
        return self.event_type in self._TERMINAL_EVENT_TYPES

    @property
    def operation_type(self) -> str:
        """Translate a canonical event into the legacy orchestration action."""
        if self.is_terminal:
            return "complete_learning"
        return "browse_node"

    def orchestration_payload(self) -> dict[str, Any]:
        """Return the narrow evidence-only payload accepted by orchestration."""
        payload: dict[str, Any] = {
            "interaction_type": self.operation_type,
            "current_node_id": self.node_id or None,
        }
        if self.completion_evidence is not None:
            payload["completion_evidence"] = self.completion_evidence.model_dump(mode="json")
        return payload
