from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import src.resource_generation.quality as resource_quality
import src.resource_generation.services as resource_services
from src.application import resource_service
from src.api_models.learning_event import LearningEventRequest
from src.application.resource_service import _quiz_payload_with_stable_answers
from src.database.resource_generation_repo import (
    MemoryResourceGenerationRepo,
    _MemoryGenerationStore,
)
from src.orchestration_core import _verify_quiz_completion
from src.resource_generation.context import ResourceContext
from src.resource_generation.generator import ResourceGenerator
from src.resource_generation.quality import evaluate_resource_quality
from src.resource_generation.validator import validate_resource_payload
from src.state.agent_state import AgentState, ResourceCard
from tests.helpers import FakeValidationPipeline


def _context(*, question_bank: bool = False) -> ResourceContext:
    candidates = [{"id": "bank-q1", "text": "队列遵循什么访问顺序？"}] if question_bank else []
    return ResourceContext(
        user_id="learner",
        course_id="course-a",
        node_id="N01",
        node_title="队列",
        capability_target="解释先进先出约束",
        knowledge_refs=[{
            "id": "kb-queue",
            "type": "knowledge_base",
            "title": "队列定义",
            "excerpt": "队列遵循先进先出约束，删除最早进入的元素。",
            "course_id": "course-a",
            "node_ids": ["N01"],
        }],
        content_version="resource-v4",
        question_bank_candidates=candidates,
        question_bank_status="matched" if candidates else "empty",
    )


@pytest.mark.parametrize("original_answer", range(4))
@pytest.mark.parametrize("revision", range(1, 5))
def test_quiz_shuffle_keeps_answer_and_distractor_tags_bound_to_option_text(
    original_answer: int,
    revision: int,
) -> None:
    options = ["选项甲", "选项乙", "选项丙", "选项丁"]
    payload = {
        "questions": [{
            "id": "q1",
            "options": options,
            "answer_index": original_answer,
            "distractor_error_tags": {
                str(index): f"错误:{option}"
                for index, option in enumerate(options)
                if index != original_answer
            },
        }],
    }

    shuffled = _quiz_payload_with_stable_answers(payload, "N04", revision)
    question = shuffled["questions"][0]

    assert question["options"][question["answer_index"]] == options[original_answer]
    assert set(question["distractor_error_tags"]) == {
        str(index) for index in range(4) if index != question["answer_index"]
    }
    for index, option in enumerate(question["options"]):
        if index == question["answer_index"]:
            continue
        assert question["distractor_error_tags"][str(index)] == f"错误:{option}"


def test_quiz_shuffle_depends_on_a_server_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EDUAGENT_QUIZ_SHUFFLE_SECRET", raising=False)
    payload = {
        "questions": [
            {
                "id": f"q{index}",
                "options": ["甲", "乙", "丙", "丁"],
                "answer_index": index % 4,
            }
            for index in range(1, 9)
        ],
    }

    monkeypatch.setattr(resource_service, "_QUIZ_SHUFFLE_EPHEMERAL_KEY", b"a" * 32)
    first = _quiz_payload_with_stable_answers(payload, "N04", revision=1)
    repeated = _quiz_payload_with_stable_answers(payload, "N04", revision=1)
    monkeypatch.setattr(resource_service, "_QUIZ_SHUFFLE_EPHEMERAL_KEY", b"b" * 32)
    second = _quiz_payload_with_stable_answers(payload, "N04", revision=1)

    first_indexes = [question["answer_index"] for question in first["questions"]]
    assert first_indexes == [
        question["answer_index"] for question in repeated["questions"]
    ]
    assert first_indexes != [
        question["answer_index"] for question in second["questions"]
    ]


def test_legacy_unstructured_quiz_markdown_is_never_published() -> None:
    context = _context()
    generated = replace(
        ResourceGenerator().template(context, "diagnostic_quiz"),
        source="llm",
        fallback_reason="legacy_unstructured_output",
        body_markdown=(
            "## 泄漏测验\n\n"
            '答案字段：{"answer_index":0,"explanation":"正确答案解析",'
            '"source_answer_label":"A"}'
        ),
    )

    card = resource_service._resource_card_from_generated(  # noqa: SLF001
        generated,
        context=context,
        binding={
            "course_id": context.course_id,
            "node_id": context.node_id,
            "title": context.node_title,
        },
        existing_cards=[],
        force=False,
        job_id="legacy-quiz-job",
    )

    assert "answer_index" not in card.content
    assert "正确答案解析" not in card.content
    assert "source_answer_label" not in card.content


def test_validator_rejects_duplicate_questions_and_unknown_bank_provenance() -> None:
    context = _context(question_bank=True)
    payload = ResourceGenerator().template(context, "diagnostic_quiz").structured_payload
    payload = copy.deepcopy(payload)
    payload["questions"][1]["id"] = payload["questions"][0]["id"]
    payload["questions"][1]["prompt"] = payload["questions"][0]["prompt"]
    payload["questions"][0]["source_question_ids"] = ["invented-bank-id"]

    validation = validate_resource_payload("diagnostic_quiz", payload, context)
    codes = {issue.code for issue in validation.issues}

    assert validation.valid is False
    assert "quiz_question_id_duplicate" in codes
    assert "quiz_question_duplicate" in codes
    assert "quiz_question_bank_source_unknown" in codes


class _UnavailableNli:
    def entailment(self, *_args, **_kwargs):
        from src.resource_generation.services import ServiceUnavailable

        raise ServiceUnavailable("offline")


class _MatchingVerifier:
    def verify(self, questions):
        return {
            "protocol_version": "diagnostic-blind-v2",
            "agreement": 1.0,
            "answers": [
                {"id": question["id"], "selected_index": question["answer_index"]}
                for question in questions
            ],
        }


class _MismatchingVerifier:
    def verify(self, questions):
        return {
            "protocol_version": "diagnostic-blind-v2",
            "agreement": 1.0,
            "answers": [
                {
                    "id": question["id"],
                    "selected_index": (question["answer_index"] + 1) % len(question["options"]),
                }
                for question in questions
            ],
        }


class _MatchingNli:
    def entailment(self, *_args, **_kwargs):
        return {
            "passed": True,
            "entailment": 0.99,
            "contradiction": 0.0,
            "artifact_digest": "sha256:test",
        }


def test_quality_checks_generic_distractors_using_actual_answer_index() -> None:
    context = _context()
    payload = ResourceGenerator().template(context, "diagnostic_quiz").structured_payload
    payload = _quiz_payload_with_stable_answers(payload, "N01", revision=1)
    question = payload["questions"][0]
    distractor_index = next(index for index in range(4) if index != question["answer_index"])
    question["options"][distractor_index] = "只背诵术语，不检查输入条件"

    evaluation = evaluate_resource_quality(
        "diagnostic_quiz",
        payload,
        context,
        nli=_UnavailableNli(),
        diagnostic_verifier=_MatchingVerifier(),
    )

    assert "diagnostic_generic_distractors" in evaluation.issue_codes


def test_blind_verifier_must_match_each_server_answer_even_with_high_agreement() -> None:
    context = _context()
    payload = ResourceGenerator().template(context, "diagnostic_quiz").structured_payload

    evaluation = evaluate_resource_quality(
        "diagnostic_quiz",
        payload,
        context,
        nli=_UnavailableNli(),
        diagnostic_verifier=_MismatchingVerifier(),
    )

    assert evaluation.hard_fail is True
    assert "diagnostic_answer_inconsistent" in evaluation.issue_codes


class _UnversionedMatchingVerifier:
    def verify(self, questions):
        return {
            "agreement": 1.0,
            "answers": [
                {"id": question["id"], "selected_index": question["answer_index"]}
                for question in questions
            ],
        }


def _llm_quiz_payload(context: ResourceContext) -> dict:
    payload = copy.deepcopy(
        ResourceGenerator().template(context, "diagnostic_quiz").structured_payload
    )
    payload["quality_profile"] = {
        "generation_source": "llm",
        "status": "pending",
    }
    return payload


def test_blind_verifier_requires_explicit_v2_protocol_version() -> None:
    context = _context()
    payload = _llm_quiz_payload(context)

    evaluation = evaluate_resource_quality(
        "diagnostic_quiz",
        payload,
        context,
        nli=_UnavailableNli(),
        diagnostic_verifier=_UnversionedMatchingVerifier(),
    )

    assert evaluation.hard_fail is True
    assert "diagnostic_blind_verifier_protocol_unsupported" in evaluation.issue_codes


def test_legacy_blind_verifier_response_fails_closed_with_v2_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            # Legacy sidecars only returned an aggregate score, which cannot
            # prove that every server-owned answer key was independently checked.
            return {"agreement": 1.0}

    def fake_post(url, *, json, headers, timeout):
        captured.update({
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        })
        return Response()

    monkeypatch.setenv("DIAGNOSTIC_VERIFIER_URL", "http://verifier.internal")
    monkeypatch.setattr(resource_services.httpx, "post", fake_post)
    context = _context()
    payload = _llm_quiz_payload(context)

    evaluation = evaluate_resource_quality(
        "diagnostic_quiz",
        payload,
        context,
        nli=_MatchingNli(),
    )

    request_payload = captured["json"]
    assert request_payload["protocol_version"] == "diagnostic-blind-v2"
    assert request_payload["response_schema"]["protocol_version"] == (
        "diagnostic-blind-v2"
    )
    assert "answer_index" not in request_payload["questions"][0]
    assert evaluation.hard_fail is True
    assert evaluation.gate_status == "failed"
    assert evaluation.issue_codes == (
        "diagnostic_blind_verifier_protocol_unsupported",
    )


def test_unsupported_blind_protocol_triggers_safe_template_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"blind": 0}

    class LegacyBlindVerifier:
        def verify(self, questions):
            calls["blind"] += 1
            return {"agreement": 1.0}

    monkeypatch.setattr(resource_quality, "NLIServiceClient", _MatchingNli)
    monkeypatch.setattr(
        resource_quality,
        "DiagnosticBlindVerifierClient",
        LegacyBlindVerifier,
    )
    monkeypatch.setattr(
        resource_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    monkeypatch.setattr(resource_service, "persist_session", lambda _session: None)

    context = _context()
    state = AgentState(
        user_id=context.user_id,
        course_id=context.course_id,
        current_node_id=context.node_id,
    )
    session = SimpleNamespace(agent_state=state)
    binding = {
        "course_id": context.course_id,
        "node_id": context.node_id,
        "title": context.node_title,
    }
    template_generated = ResourceGenerator().template(context, "diagnostic_quiz")
    generated = replace(
        template_generated,
        structured_payload=_llm_quiz_payload(context),
        source="llm",
        fallback_reason=None,
    )
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job, _created = repo.create_or_get_active_job(
        context.user_id,
        context.course_id,
        context.node_id,
        "legacy-blind-protocol",
        card_types=["diagnostic_quiz"],
        pipeline_version="resource-v4",
        quality_version="resource-quality-v4.1",
    )
    card = resource_service._resource_card_from_generated(  # noqa: SLF001
        generated,
        context=context,
        binding=binding,
        existing_cards=[],
        force=False,
        job_id=job["job_id"],
    )

    persisted, error = resource_service._persist_ready_card(  # noqa: SLF001
        repo=repo,
        job_id=job["job_id"],
        session=session,
        context=context,
        binding=binding,
        card=card,
    )

    assert error is None
    assert persisted is not None
    assert calls["blind"] == 2
    assert persisted.metadata["generation"]["source"] == "template"
    assert persisted.metadata["generation"]["fallback_reason"] == (
        "resource_quality_gate_failed"
    )
    assert persisted.metadata["quality_status"] == "degraded"
    assert persisted.metadata["repair_request"]["issue_codes"] == [
        "diagnostic_blind_verifier_protocol_unsupported"
    ]


def _quiz_state(answer_index: int) -> AgentState:
    state = AgentState(user_id="u1", course_id="course-a", current_node_id="N01")
    state.generated_resources["N01"] = [ResourceCard(
        resource_id="quiz-1",
        node_id="N01",
        card_type="diagnostic_quiz",
        content="## 诊断",
        metadata={
            "structured_payload": {
                "questions": [{
                    "id": "q1",
                    "prompt": "队列遵循什么顺序？",
                    "options": ["先进先出", "后进先出", "随机访问", "按值排序"],
                    "answer_index": answer_index,
                }],
            },
        },
    )]
    return state


def _event(selected_index: int) -> LearningEventRequest:
    return LearningEventRequest.model_validate({
        "event_type": "lesson_completed",
        "node_id": "N01",
        "resource_id": "quiz-1",
        "result": {
            "evidence_type": "diagnostic_quiz",
            "answers": [{"question_id": "q1", "answer_index": selected_index}],
        },
    })


def test_verifier_rejects_server_and_client_indexes_outside_options() -> None:
    accepted, _, reason, _ = _verify_quiz_completion(
        _quiz_state(answer_index=4),
        "N01",
        _event(0),
    )
    assert accepted is False
    assert reason == "diagnostic_quiz_has_invalid_answer_key"

    accepted, _, reason, _ = _verify_quiz_completion(
        _quiz_state(answer_index=0),
        "N01",
        _event(4),
    )
    assert accepted is False
    assert reason == "invalid_quiz_answer_index"


def test_quiz_answer_rejects_bool_and_numeric_strings() -> None:
    for invalid in (True, "1"):
        with pytest.raises(ValidationError):
            _event(invalid)  # type: ignore[arg-type]
