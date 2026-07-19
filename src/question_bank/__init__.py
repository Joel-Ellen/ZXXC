"""Local, bounded question-bank access for adaptive quiz generation."""

from .repository import (
    QuestionBankRepository,
    QuestionBankSelection,
    get_question_bank_repository,
)

__all__ = [
    "QuestionBankRepository",
    "QuestionBankSelection",
    "get_question_bank_repository",
]
