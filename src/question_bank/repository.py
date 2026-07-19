"""Read-only access to the normalized data-structures question bank."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_QUESTION_BANK_PATH = Path(__file__).with_name("data_structures_questions.json")
MAX_BANK_BYTES = 16 * 1024 * 1024
MAX_BANK_QUESTIONS = 20_000
MAX_PROMPT_CANDIDATES = 10
MAX_PROMPT_TEXT_CHARS = 1_600
MAX_QUESTION_ID_CHARS = 128
MAX_SOURCE_NUMBER_CHARS = 32
MAX_SOURCE_NUMBER_ABS = 1_000_000_000
QUESTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
GENERATION_QUESTION_TYPES = {
    "multiple_choice",
    "open_response",
    "fill_blank",
    "true_false",
}
ANSWER_KEY_STATUSES = {"source_embedded_unverified", "missing"}


def _enabled() -> bool:
    value = str(os.environ.get("EDUAGENT_QUESTION_BANK_ENABLED", "true")).strip().lower()
    return value not in {"0", "false", "off", "no"}


def _bounded_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 6
    return max(0, min(MAX_PROMPT_CANDIDATES, parsed))


@dataclass(frozen=True)
class QuestionBankSelection:
    status: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    collection_version: str = ""
    issue: str = ""

    @property
    def candidate_ids(self) -> list[str]:
        return [
            str(candidate.get("id") or "")
            for candidate in self.candidates
            if str(candidate.get("id") or "")
        ]


class QuestionBankRepository:
    """Lazy, thread-safe reader with deterministic per-revision selection."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = str(os.environ.get("EDUAGENT_QUESTION_BANK_PATH") or "").strip()
        self.path = Path(path or configured or DEFAULT_QUESTION_BANK_PATH)
        self._lock = threading.RLock()
        self._cache_key: tuple[int, int] | None = None
        self._bank: dict[str, Any] | None = None
        self._questions_by_id: dict[str, dict[str, Any]] = {}

    def _load(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        try:
            stat_result = self.path.stat()
        except OSError as exc:
            raise ValueError(f"question_bank_unavailable:{type(exc).__name__}") from exc
        if not self.path.is_file():
            raise ValueError("question_bank_path_not_file")
        if stat_result.st_size <= 0 or stat_result.st_size > MAX_BANK_BYTES:
            raise ValueError("question_bank_size_invalid")
        cache_key = (stat_result.st_mtime_ns, stat_result.st_size)
        with self._lock:
            if self._bank is not None and self._cache_key == cache_key:
                return self._bank, self._questions_by_id
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                RecursionError,
            ) as exc:
                raise ValueError(f"question_bank_invalid:{type(exc).__name__}") from exc
            if not isinstance(value, dict):
                raise ValueError("question_bank_root_invalid")
            if str(value.get("schema_version") or "") != "1.0":
                raise ValueError("question_bank_schema_unsupported")
            if str(value.get("course_id") or "") != "data_structures":
                raise ValueError("question_bank_course_invalid")
            questions = value.get("questions")
            node_index = value.get("node_index")
            if not isinstance(questions, list) or not isinstance(node_index, dict):
                raise ValueError("question_bank_shape_invalid")
            if len(questions) > MAX_BANK_QUESTIONS:
                raise ValueError("question_bank_question_count_invalid")
            by_id: dict[str, dict[str, Any]] = {}
            for question in questions:
                if not isinstance(question, dict):
                    raise ValueError("question_bank_question_invalid")
                question_id = str(question.get("id") or "").strip()
                if (
                    not question_id
                    or len(question_id) > MAX_QUESTION_ID_CHARS
                    or QUESTION_ID_RE.fullmatch(question_id) is None
                    or question_id in by_id
                ):
                    raise ValueError("question_bank_question_id_invalid")
                by_id[question_id] = question
            for node_id, ids in node_index.items():
                if not isinstance(node_id, str) or not isinstance(ids, list):
                    raise ValueError("question_bank_node_index_invalid")
                if any(not isinstance(question_id, str) or question_id not in by_id for question_id in ids):
                    raise ValueError("question_bank_node_reference_invalid")
                for question_id in ids:
                    question = by_id[question_id]
                    question_nodes = question.get("node_ids")
                    if (
                        str(question.get("course_id") or "") != "data_structures"
                        or not isinstance(question_nodes, list)
                        or node_id not in question_nodes
                        or question.get("usable_for_generation") is not True
                        or str(question.get("question_type") or "")
                        not in GENERATION_QUESTION_TYPES
                    ):
                        raise ValueError("question_bank_node_scope_invalid")
            digest_payload = {
                "questions": questions,
                "node_index": dict(sorted(node_index.items())),
            }
            try:
                digest = hashlib.sha256(
                    json.dumps(
                        digest_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            except (TypeError, ValueError, RecursionError) as exc:
                raise ValueError("question_bank_digest_invalid") from exc
            expected_version = f"ds-qbank-v1-{digest[:16]}"
            if str(value.get("collection_version") or "") != expected_version:
                raise ValueError("question_bank_version_mismatch")
            self._cache_key = cache_key
            self._bank = value
            self._questions_by_id = by_id
            return value, by_id

    @staticmethod
    def _rank(question: dict[str, Any], seed: str) -> tuple[int, int, int]:
        answer = question.get("source_answer")
        answer = answer if isinstance(answer, dict) else {}
        answer_rank = 0 if answer.get("status") == "source_embedded_unverified" else 1
        question_type = str(question.get("question_type") or "")
        type_rank = {
            "multiple_choice": 0,
            "open_response": 1,
            "fill_blank": 2,
            "true_false": 3,
        }.get(question_type, 4)
        tie_breaker = int.from_bytes(
            hashlib.sha256(f"{seed}|{question.get('id', '')}".encode("utf-8")).digest()[:8],
            "big",
        )
        return answer_rank, type_rank, tie_breaker

    @staticmethod
    def _prompt_candidate(question: dict[str, Any]) -> dict[str, Any]:
        source = question.get("source") if isinstance(question.get("source"), dict) else {}
        answer = question.get("source_answer") if isinstance(question.get("source_answer"), dict) else {}
        question_type = str(question.get("question_type") or "").strip()
        if question_type not in GENERATION_QUESTION_TYPES:
            question_type = "unknown"
        answer_status = str(answer.get("status") or "missing").strip()
        if answer_status not in ANSWER_KEY_STATUSES:
            answer_status = "missing"
        candidate: dict[str, Any] = {
            "id": str(question.get("id") or "")[:MAX_QUESTION_ID_CHARS],
            "question_type": question_type,
            "text": str(question.get("prompt_text") or question.get("text") or "")[:MAX_PROMPT_TEXT_CHARS],
            "source": {
                "title": str(source.get("title") or "")[:160],
                "section": str(source.get("section") or "")[:120],
            },
            "answer_key_status": answer_status,
        }
        source_number = source.get("number")
        if (
            isinstance(source_number, int)
            and not isinstance(source_number, bool)
            and abs(source_number) <= MAX_SOURCE_NUMBER_ABS
        ):
            candidate["source"]["number"] = source_number
        elif isinstance(source_number, str):
            bounded_number = source_number.strip()[:MAX_SOURCE_NUMBER_CHARS]
            if bounded_number:
                candidate["source"]["number"] = bounded_number
        # This hint is sent only to the server-side LLM and is never copied to
        # the public resource contract.  The prompt explicitly requires the
        # model to verify it against course evidence before using it.
        source_answer_label = str(answer.get("label") or "").strip().upper()
        if (
            answer_status == "source_embedded_unverified"
            and re.fullmatch(r"[A-D]", source_answer_label)
        ):
            candidate["source_answer_label"] = source_answer_label
        return candidate

    def select(
        self,
        course_id: str,
        node_id: str,
        *,
        limit: int = 6,
        seed: str = "",
    ) -> QuestionBankSelection:
        if not _enabled():
            return QuestionBankSelection(status="disabled")
        if str(course_id or "").strip() != "data_structures":
            return QuestionBankSelection(status="not_applicable")
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return QuestionBankSelection(status="empty", issue="node_id_missing")
        safe_limit = _bounded_limit(limit)
        if safe_limit == 0:
            return QuestionBankSelection(status="empty", issue="candidate_limit_zero")
        try:
            bank, questions_by_id = self._load()
        except ValueError as exc:
            return QuestionBankSelection(status="unavailable", issue=str(exc)[:160])
        node_index = bank.get("node_index") if isinstance(bank.get("node_index"), dict) else {}
        question_ids = node_index.get(normalized_node_id)
        if not isinstance(question_ids, list) or not question_ids:
            return QuestionBankSelection(
                status="empty",
                collection_version=str(bank.get("collection_version") or ""),
                issue="node_has_no_candidates",
            )
        eligible = [
            questions_by_id[question_id]
            for question_id in question_ids
            if question_id in questions_by_id
            and questions_by_id[question_id].get("usable_for_generation") is True
            and not str(questions_by_id[question_id].get("duplicate_of") or "")
            and str(questions_by_id[question_id].get("prompt_text") or "").strip()
        ]
        if not eligible:
            return QuestionBankSelection(
                status="empty",
                collection_version=str(bank.get("collection_version") or ""),
                issue="node_candidates_filtered",
            )
        ranked = sorted(eligible, key=lambda item: self._rank(item, seed or normalized_node_id))

        # First take one candidate from each available source type, then fill
        # by quality rank. This prevents a node with many rote multiple-choice
        # items from starving application-style source material.
        chosen: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for question_type in ("multiple_choice", "open_response", "fill_blank", "true_false"):
            candidate = next(
                (item for item in ranked if item.get("question_type") == question_type),
                None,
            )
            if candidate is None:
                continue
            chosen.append(candidate)
            used_ids.add(str(candidate.get("id") or ""))
            if len(chosen) >= safe_limit:
                break
        for candidate in ranked:
            candidate_id = str(candidate.get("id") or "")
            if candidate_id in used_ids:
                continue
            chosen.append(candidate)
            used_ids.add(candidate_id)
            if len(chosen) >= safe_limit:
                break
        return QuestionBankSelection(
            status="matched",
            candidates=[self._prompt_candidate(candidate) for candidate in chosen],
            collection_version=str(bank.get("collection_version") or ""),
        )


_DEFAULT_REPOSITORY: QuestionBankRepository | None = None
_DEFAULT_REPOSITORY_KEY = ""
_DEFAULT_REPOSITORY_LOCK = threading.Lock()


def get_question_bank_repository() -> QuestionBankRepository:
    """Return a process-local repository, refreshing when its path changes."""
    global _DEFAULT_REPOSITORY, _DEFAULT_REPOSITORY_KEY
    configured = str(os.environ.get("EDUAGENT_QUESTION_BANK_PATH") or "").strip()
    key = configured or str(DEFAULT_QUESTION_BANK_PATH)
    with _DEFAULT_REPOSITORY_LOCK:
        if _DEFAULT_REPOSITORY is None or _DEFAULT_REPOSITORY_KEY != key:
            _DEFAULT_REPOSITORY = QuestionBankRepository(configured or None)
            _DEFAULT_REPOSITORY_KEY = key
        return _DEFAULT_REPOSITORY
