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


class LearningObjective(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=500)


class AtomicClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=700)
    critical: bool = True
    evidence_ids: list[str] = Field(default_factory=list, min_length=1, max_length=5)


class LearningBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: str = "resource-blueprint-v1"
    objectives: list[LearningObjective] = Field(min_length=1, max_length=8)
    claims: list[AtomicClaim] = Field(min_length=1, max_length=16)
    terms: list[str] = Field(default_factory=list, max_length=16)
    misconceptions: list[str] = Field(default_factory=list, max_length=10)
    examples: list[str] = Field(default_factory=list, max_length=8)
    boundaries: list[str] = Field(default_factory=list, max_length=8)
    difficulty_strategy: str = Field(min_length=1, max_length=800)
    card_roles: dict[str, str] = Field(default_factory=dict)


class ResourcePayload(BaseModel):
    """Fields shared by every generated card."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    render_type: str
    title: str = Field(min_length=1, max_length=160)
    source_ref_ids: list[str] = Field(default_factory=list, max_length=5)
    objective_ids: list[str] = Field(default_factory=list, max_length=8)
    evidence_map: dict[str, list[str]] = Field(default_factory=dict)
    language: str = Field(default="zh-CN", min_length=2, max_length=32)
    content_language: str = Field(default="zh-CN", min_length=2, max_length=32)
    quality_profile: dict[str, Any] = Field(default_factory=dict)


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
    learning_blueprint: LearningBlueprint | None = None


class BoundaryTest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    input: str = Field(min_length=1, max_length=600)
    expected: str = Field(min_length=1, max_length=600)


class CodeSnippetPayload(ResourcePayload):
    render_type: Literal["code_snippet"] = "code_snippet"
    # Generated examples and the bound practice runner use the same C
    # contract.  Keeping this literal prevents a provider from silently
    # returning a different language that the learner cannot execute.
    language: Literal["c"] = "c"
    scenario: str = Field(min_length=1, max_length=1000)
    prerequisites: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    code: str = Field(min_length=1, max_length=12000)
    boundary_tests: list[BoundaryTest] = Field(default_factory=list, min_length=1, max_length=8)
    walkthrough_steps: list[str] = Field(default_factory=list, min_length=1, max_length=10)
    explanation: str = Field(min_length=1, max_length=1800)
    complexity_notes: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    pitfalls: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    experiments: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    example_binding: str = Field(default="", max_length=160)
    practice_id: str = Field(default="", max_length=160)
    verification: dict[str, Any] = Field(default_factory=dict)


class ExerciseRubricItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion: str = Field(min_length=1, max_length=300)
    points: int = Field(ge=1, le=100)
    evidence: str = Field(min_length=1, max_length=500)


class ExerciseCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=500)
    expected_signal: str = Field(min_length=1, max_length=500)


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
    rubric: list[ExerciseRubricItem] = Field(default_factory=list, max_length=8)
    structured_checkpoints: list[ExerciseCheckpoint] = Field(default_factory=list, max_length=8)
    hint_levels: dict[str, str] = Field(default_factory=dict)


class VideoTimelineItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=800)


class VideoSummaryPayload(ResourcePayload):
    render_type: Literal["video_summary"] = "video_summary"
    summary: str = Field(min_length=1, max_length=1300)
    key_points: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    timeline: list[VideoTimelineItem] = Field(default_factory=list, max_length=8)
    watch_focus: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    review_questions: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    duration_minutes: int = Field(default=0, ge=0, le=240)
    video_url: str | None = None
    video_source_id: str | None = None
    media_status: Literal["trusted_video", "no_trusted_video"] = "no_trusted_video"
    reading_sequence: list[str] = Field(default_factory=list, max_length=8)


class DiagnosticQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=120)
    level: Literal["concept", "understanding", "application", "boundary", "transfer"]
    prompt: str = Field(min_length=1, max_length=1200)
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3, strict=True)
    explanation: str = Field(min_length=1, max_length=1300)
    skill_tag: str = Field(min_length=1, max_length=160)
    error_tags: list[str] = Field(default_factory=list, max_length=5)
    distractor_error_tags: dict[str, str] = Field(default_factory=dict)
    source_question_ids: list[str] = Field(default_factory=list, max_length=3)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    @field_validator("options")
    @classmethod
    def options_are_distinct(cls, options: list[str]) -> list[str]:
        normalized = [option.strip() for option in options]
        folded = ["".join(option.casefold().split()) for option in normalized]
        if any(not option for option in normalized) or len(set(folded)) != 4:
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
