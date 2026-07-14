# -*- coding: utf-8 -*-
"""Tutor request DTOs shared by HTTP and application boundaries."""

from __future__ import annotations

from typing import ClassVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class TutorRequest(BaseModel):
    """A normalized Tutor request independent from transport field casing."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    question: str = Field(
        default="",
        max_length=4000,
        validation_alias=AliasChoices("question", "query", "tutor_query"),
    )
    context_type: str = Field(
        default="general",
        max_length=32,
        validation_alias=AliasChoices("context_type", "contextType"),
    )
    code_snippet: str = Field(
        default="",
        max_length=64 * 1024,
        validation_alias=AliasChoices("code_snippet", "codeSnippet"),
    )
    error_message: str = Field(
        default="",
        max_length=8 * 1024,
        validation_alias=AliasChoices("error_message", "errorMessage"),
    )
    stream: bool = False

    _CONTEXT_ALIASES: ClassVar[dict[str, str]] = {
        "general": "general",
        "study_advice": "general",
        "study-advice": "general",
        "concept": "concept",
        "conceptual": "concept",
        "problem": "problem_solving",
        "problem_solving": "problem_solving",
        "problem-solving": "problem_solving",
        "code": "code_debug",
        "debug": "code_debug",
        "code_debug": "code_debug",
        "code-debug": "code_debug",
        "exam": "exam_prep",
        "exam_prep": "exam_prep",
        "exam-prep": "exam_prep",
    }

    @field_validator("question", "code_snippet", "error_message", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("context_type", mode="before")
    @classmethod
    def normalize_context_type(cls, value: object) -> str:
        normalized = str(value or "general").strip().lower().replace(" ", "_")
        mapped = cls._CONTEXT_ALIASES.get(normalized)
        if mapped is None:
            supported = ", ".join(sorted(set(cls._CONTEXT_ALIASES.values())))
            raise ValueError(f"Unsupported context_type '{value}'. Supported values: {supported}")
        return mapped
