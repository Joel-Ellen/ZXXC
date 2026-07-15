"""Pydantic contracts for the five learning-resource cards.

These schemas are deliberately compatible with the existing ResourceCanvas
payload field names while making the previously implicit teaching requirements
explicit.  The renderer consumes the same payloads, so Markdown is never the
source of truth.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


CARD_TYPES = (
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "video_summary",
    "diagnostic_quiz",
)
CONTENT_VERSION = "resource-v3"


class ResourcePayload(BaseModel):
    """Fields shared by every generated card."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    render_type: str
    title: str = Field(min_length=1, max_length=160)
    source_ref_ids: list[str] = Field(default_factory=list, max_length=5)


class ConceptSection(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    heading: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=1200)


class ConceptMapPayload(ResourcePayload):
    render_type: Literal["concept_map"] = "concept_map"
    summary: str = Field(min_length=1, max_length=1000)
    definition: str = Field(min_length=1, max_length=900)
    constraints: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    mechanism: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    prerequisites: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    learning_objectives: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    sections: list[ConceptSection] = Field(default_factory=list, min_length=1, max_length=8)
    bullets: list[str] = Field(default_factory=list, min_length=1, max_length=10)
    common_misconceptions: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    counterexamples: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    transfer_questions: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    review_prompts: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    mermaid_source: str = Field(min_length=1, max_length=6000)


class BoundaryTest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    input: str = Field(min_length=1, max_length=600)
    expected: str = Field(min_length=1, max_length=600)


class CodeSnippetPayload(ResourcePayload):
    render_type: Literal["code_snippet"] = "code_snippet"
    # Code-practice execution and the local syntax gate are Python-only.  Do
    # not advertise languages whose generated examples cannot be verified.
    language: Literal["python"] = "python"
    scenario: str = Field(min_length=1, max_length=1000)
    prerequisites: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    code: str = Field(min_length=1, max_length=12000)
    boundary_tests: list[BoundaryTest] = Field(default_factory=list, min_length=1, max_length=8)
    walkthrough_steps: list[str] = Field(default_factory=list, min_length=1, max_length=10)
    explanation: str = Field(min_length=1, max_length=1800)
    complexity_notes: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    pitfalls: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    experiments: list[str] = Field(default_factory=list, min_length=1, max_length=8)


class InteractiveExercisePayload(ResourcePayload):
    render_type: Literal["interactive_exercise"] = "interactive_exercise"
    goal: str = Field(min_length=1, max_length=900)
    error_signature: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1, max_length=1800)
    steps: list[str] = Field(default_factory=list, min_length=1, max_length=10)
    checkpoints: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    hints: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    solution_outline: str = Field(min_length=1, max_length=1600)
    expected_outcome: str = Field(min_length=1, max_length=900)


class VideoTimelineItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=800)


class VideoSummaryPayload(ResourcePayload):
    render_type: Literal["video_summary"] = "video_summary"
    summary: str = Field(min_length=1, max_length=1300)
    key_points: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    timeline: list[VideoTimelineItem] = Field(default_factory=list, min_length=1, max_length=8)
    watch_focus: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    review_questions: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    duration_minutes: int = Field(default=0, ge=0, le=240)
    video_url: str | None = None
    video_source_id: str | None = None


class DiagnosticQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=120)
    level: Literal["concept", "understanding", "application"]
    prompt: str = Field(min_length=1, max_length=1200)
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=1300)
    skill_tag: str = Field(min_length=1, max_length=160)
    error_tags: list[str] = Field(default_factory=list, max_length=5)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    @field_validator("options")
    @classmethod
    def options_are_distinct(cls, options: list[str]) -> list[str]:
        normalized = [option.strip() for option in options]
        if any(not option for option in normalized) or len(set(normalized)) != 4:
            raise ValueError("questions require four distinct non-empty options")
        return normalized


class DiagnosticQuizPayload(ResourcePayload):
    render_type: Literal["diagnostic_quiz"] = "diagnostic_quiz"
    questions: list[DiagnosticQuestion] = Field(default_factory=list, min_length=3, max_length=8)
    pass_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    after_quiz_guidance: str = Field(min_length=1, max_length=1000)


PayloadModel: TypeAlias = Union[
    ConceptMapPayload,
    CodeSnippetPayload,
    InteractiveExercisePayload,
    VideoSummaryPayload,
    DiagnosticQuizPayload,
]

PAYLOAD_MODELS: dict[str, type[ResourcePayload]] = {
    "concept_map": ConceptMapPayload,
    "code_snippet": CodeSnippetPayload,
    "interactive_exercise": InteractiveExercisePayload,
    "video_summary": VideoSummaryPayload,
    "diagnostic_quiz": DiagnosticQuizPayload,
}


def payload_model_for(card_type: str) -> type[ResourcePayload]:
    try:
        return PAYLOAD_MODELS[card_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported resource card type: {card_type}") from exc


def coerce_payload(card_type: str, value: Any) -> dict[str, Any]:
    """Validate a provider value and return its normalized JSON-safe shape."""
    return payload_model_for(card_type).model_validate(value).model_dump(mode="json")
