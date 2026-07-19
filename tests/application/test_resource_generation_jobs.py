from __future__ import annotations

import concurrent.futures
import json
import threading

from src.application import resource_service
from src.database.resource_generation_repo import MemoryResourceGenerationRepo
from src.orchestration_runtime import ResourceGenerationResult
from src.resource_generation import ResourceGenerator
from src.validation.language import is_chinese_learning_content
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


def _event_types(repo: MemoryResourceGenerationRepo, job_id: str) -> list[str]:
    return [event["event_type"] for event in repo.list_events(job_id)]


def test_historical_quiz_event_replay_redacts_raw_markdown() -> None:
    historical_event = {
        "event_id": 1,
        "event_type": "card_ready",
        "payload": {
            "card_type": "diagnostic_quiz",
            "card": {
                "resource_id": "legacy-quiz",
                "node_id": "N01",
                "resource_type": "diagnostic_quiz",
                "body_markdown": (
                    '{"answer_index":0,"distractor_error_tags":{"1":"错"},'
                    '"explanation":"服务端解析","source_answer_label":"A"}'
                ),
                "structured_payload": {
                    "title": "诊断测验",
                    "questions": [{
                        "id": "q1",
                        "prompt": "队列遵循哪种顺序？",
                        "options": ["先进先出", "后进先出", "随机", "排序"],
                        "answer_index": 0,
                        "explanation": "服务端解析",
                        "distractor_error_tags": {"1": "错"},
                        "source_answer_label": "A",
                    }],
                },
            },
        },
    }

    class HistoricalRepo:
        @staticmethod
        def get_job(job_id):
            return {"job_id": job_id, "user_id": "event-user"}

        @staticmethod
        def list_events(job_id, after_event_id=0, limit=100):
            del job_id, after_event_id, limit
            return [historical_event]

    events = resource_service.list_generation_events(
        "legacy-job",
        user_id="event-user",
        repo=HistoricalRepo(),
    )
    serialized = json.dumps(events, ensure_ascii=False)

    assert "answer_index" not in serialized
    assert "distractor_error_tags" not in serialized
    assert "服务端解析" not in serialized
    assert "source_answer_label" not in serialized
    assert "队列遵循哪种顺序" in events[0]["payload"]["card"]["body_markdown"]


def test_generation_job_is_idempotent_and_publishes_incremental_cards(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    state = runtime.get_session("job-user", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()

    first = resource_service.request_generation(
        "job-user",
        "course1",
        "N01",
        card_types=["concept_map", "diagnostic_quiz"],
        submit=False,
        repo=repo,
    )
    duplicate = resource_service.request_generation(
        "job-user",
        "course1",
        "N01",
        card_types=["concept_map", "diagnostic_quiz"],
        submit=False,
        repo=repo,
    )

    assert first["job_id"] == duplicate["job_id"]
    assert duplicate["created"] is False
    resource_service.run_generation_job(first["job_id"], repo=repo)

    events = repo.list_events(first["job_id"])
    assert [event["event_type"] for event in events][:2] == ["queued", "running"]
    assert _event_types(repo, first["job_id"])[-1] == "completed"
    ready_events = [event for event in events if event["event_type"] == "card_ready"]
    assert [event["payload"]["card_type"] for event in ready_events] == ["concept_map", "diagnostic_quiz"]
    quiz = ready_events[-1]["payload"]["card"]
    assert "answer_index" not in quiz["structured_payload"]["questions"][0]
    assert {card.card_type for card in state.generated_resources["N01"]} == {"concept_map", "diagnostic_quiz"}


def test_legacy_unstructured_english_output_falls_back_before_publication(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    runtime.kg = type(
        "EnglishTitleKnowledgeGraph",
        (),
        {"get_node_title": lambda _self, _node_id: "Queue invariants"},
    )()
    state = runtime.get_session("legacy-english-job-user", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    english_explanation = "This lesson is entirely in English and must not reach the learner."

    def generate_resource_contents(
        node_id,
        card_types,
        _difficulty,
        *,
        node_title="",
        **_kwargs,
    ):
        title = node_title or node_id
        return {
            card_type: ResourceGenerationResult(
                content=f"## {title}\n\n{english_explanation}",
                source="llm",
                provider="legacy-test-provider",
            )
            for card_type in card_types
        }

    runtime.generate_resource_contents = generate_resource_contents
    requested = resource_service.request_generation(
        "legacy-english-job-user",
        "course1",
        "N01",
        card_types=["interactive_exercise"],
        use_cache=False,
        submit=False,
        repo=repo,
    )

    resource_service.run_generation_job(requested["job_id"], repo=repo)

    card = next(
        value
        for value in state.generated_resources["N01"]
        if value.card_type == "interactive_exercise"
    )
    generation = card.metadata["generation"]
    assert english_explanation not in card.content
    assert generation["source"] == "template"
    assert generation["rejected_source"] == "llm"
    assert "learner_content_not_chinese" in generation["validation_issue_codes"]

    ready_event = next(
        event
        for event in repo.list_events(requested["job_id"])
        if event["event_type"] == "card_ready"
    )
    assert english_explanation not in ready_event["payload"]["card"]["body_markdown"]


def test_legacy_bound_template_does_not_reinsert_an_english_canonical_title() -> None:
    content = resource_service._bound_template_content(  # noqa: SLF001
        {
            "course_id": "course1",
            "node_id": "N01",
            "title": "Queue invariants",
        },
        "concept_map",
    )

    assert "Queue invariants" not in content
    assert "当前知识点（N01）" in content
    assert is_chinese_learning_content(content)


def test_one_failed_card_does_not_discard_ready_cards(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    state = runtime.get_session("job-failure", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    calls = {"count": 0}

    class FailSecondCard(FakeValidationPipeline):
        def validate_resource_card(self, card, ground_truth_context=""):
            calls["count"] += 1
            if card.card_type == "diagnostic_quiz":
                return None, super().validate_resource_card(card)[1]
            return super().validate_resource_card(card, ground_truth_context)

    monkeypatch.setattr(resource_service, "get_validation_pipeline", FailSecondCard)
    request = resource_service.request_generation(
        "job-failure",
        "course1",
        "N01",
        card_types=["concept_map", "diagnostic_quiz"],
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(request["job_id"], repo=repo)

    events = repo.list_events(request["job_id"])
    assert any(event["event_type"] == "card_ready" and event["payload"]["card_type"] == "concept_map" for event in events)
    assert any(event["event_type"] == "card_failed" and event["payload"]["card_type"] == "diagnostic_quiz" for event in events)
    assert [card.card_type for card in state.generated_resources["N01"]] == ["concept_map"]


def test_force_refresh_only_targets_requested_card_type(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    state = runtime.get_session("job-force", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    initial = resource_service.request_generation(
        "job-force",
        "course1",
        "N01",
        card_types=["concept_map", "code_snippet"],
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(initial["job_id"], repo=repo)
    original_code = next(card for card in state.generated_resources["N01"] if card.card_type == "code_snippet")

    refresh = resource_service.request_generation(
        "job-force",
        "course1",
        "N01",
        card_types=["concept_map"],
        force=True,
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(refresh["job_id"], repo=repo)

    code_after = next(card for card in state.generated_resources["N01"] if card.card_type == "code_snippet")
    assert code_after.resource_id == original_code.resource_id


def test_concept_priority_uses_the_reserved_executor_lane(monkeypatch) -> None:
    concept_executor = object()
    supporting_executor = object()
    monkeypatch.setattr(resource_service, "_RESOURCE_CONCEPT_JOB_EXECUTOR", concept_executor)
    monkeypatch.setattr(resource_service, "_RESOURCE_JOB_EXECUTOR", supporting_executor)

    assert resource_service._generation_executor_for_job({
        "priority": "concept_map",
        "card_types": ["concept_map"],
    }) is concept_executor
    assert resource_service._generation_executor_for_job({
        "priority": "supporting_bundle",
        "card_types": ["code_snippet"],
    }) is supporting_executor
    assert resource_service._generation_executor_for_job({
        "priority": "concept_map",
        "card_types": ["concept_map", "code_snippet"],
    }) is supporting_executor
    assert resource_service._generation_executor_for_job({
        "priority": "normal",
        "card_types": ["concept_map"],
    }) is supporting_executor


def test_concept_priority_is_an_idempotency_boundary(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    state = runtime.get_session("job-priority", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()

    normal = resource_service.request_generation(
        "job-priority",
        "course1",
        "N01",
        card_types=["concept_map"],
        priority="normal",
        submit=False,
        repo=repo,
    )
    prioritized = resource_service.request_generation(
        "job-priority",
        "course1",
        "N01",
        card_types=["concept_map"],
        priority="concept_map",
        submit=False,
        repo=repo,
    )

    assert prioritized["job_id"] != normal["job_id"]
    assert repo.get_job(prioritized["job_id"])["priority"] == "concept_map"


def test_concept_job_enqueues_supporting_bundle_without_an_sse_consumer(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    state = runtime.get_session("job-follow-up", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    submitted: list[str] = []

    def record_submission(job_id, *, repo=None, replace_active=False):
        submitted.append(job_id)

    monkeypatch.setattr(resource_service, "_submit_generation_job", record_submission)
    concept = resource_service.request_generation(
        "job-follow-up",
        "course1",
        "N01",
        card_types=["concept_map"],
        priority="concept_map",
        submit=False,
        repo=repo,
    )

    resource_service.run_generation_job(concept["job_id"], repo=repo)

    completed = next(event for event in repo.list_events(concept["job_id"]) if event["event_type"] == "completed")
    follow_up_job_id = completed["payload"]["follow_up_job_id"]
    follow_up = repo.get_job(follow_up_job_id)
    assert follow_up is not None
    assert follow_up["card_types"] == [
        "code_snippet",
        "interactive_exercise",
        "video_summary",
        "diagnostic_quiz",
    ]
    assert follow_up["priority"] == "supporting_bundle"
    assert submitted == [follow_up_job_id]


def test_fast_submission_clears_its_future_without_locking_up(monkeypatch) -> None:
    class CompletedExecutor:
        def submit(self, *_args, **_kwargs):
            future = concurrent.futures.Future()
            future.set_result(None)
            return future

    repo = MemoryResourceGenerationRepo()
    job, _ = repo.create_or_get_active_job(
        "fast-job-user",
        "course1",
        "N01",
        "fast-job-key",
        card_types=["code_snippet"],
        priority="supporting_bundle",
    )
    monkeypatch.setattr(resource_service, "_RESOURCE_JOB_EXECUTOR", CompletedExecutor())

    resource_service._submit_generation_job(job["job_id"], repo=repo)

    assert job["job_id"] not in resource_service._RESOURCE_JOB_FUTURES


def test_supporting_model_call_does_not_hold_session_lock(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    state = runtime.get_session("job-lock", "course1").agent_state
    state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    supporting_started = threading.Event()
    supporting_release = threading.Event()
    concept_started = threading.Event()

    def fake_generate_phase(_runtime, context, card_types):
        if card_types == ["code_snippet"]:
            supporting_started.set()
            assert supporting_release.wait(timeout=3)
        elif card_types == ["concept_map"]:
            concept_started.set()
        return {
            card_type: ResourceGenerator().template(context, card_type, "test")
            for card_type in card_types
        }

    monkeypatch.setattr(resource_service, "_generate_phase", fake_generate_phase)
    supporting = resource_service.request_generation(
        "job-lock",
        "course1",
        "N01",
        card_types=["code_snippet"],
        priority="supporting_bundle",
        use_cache=False,
        submit=False,
        repo=repo,
    )
    concept = resource_service.request_generation(
        "job-lock",
        "course1",
        "N02",
        card_types=["concept_map"],
        priority="concept_map",
        use_cache=False,
        submit=False,
        repo=repo,
    )

    supporting_worker = threading.Thread(
        target=resource_service.run_generation_job,
        args=(supporting["job_id"],),
        kwargs={"repo": repo},
    )
    supporting_worker.start()
    assert supporting_started.wait(timeout=1)

    concept_worker = threading.Thread(
        target=resource_service.run_generation_job,
        args=(concept["job_id"],),
        kwargs={"repo": repo},
    )
    concept_worker.start()
    assert concept_started.wait(timeout=1)

    supporting_release.set()
    supporting_worker.join(timeout=3)
    concept_worker.join(timeout=3)
    assert not supporting_worker.is_alive()
    assert not concept_worker.is_alive()
    assert repo.get_job(supporting["job_id"])["status"] == "completed"
    assert repo.get_job(concept["job_id"])["status"] == "completed"


def test_generation_request_defers_remote_knowledge_retrieval_to_the_worker(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    runtime.get_session("job-context", "course1").agent_state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    remote_flags: list[bool] = []
    original_context_builder = resource_service.build_resource_context

    def record_context(*args, **kwargs):
        remote_flags.append(bool(kwargs.get("allow_remote_retrieval", True)))
        return original_context_builder(*args, **kwargs)

    monkeypatch.setattr(resource_service, "build_resource_context", record_context)
    requested = resource_service.request_generation(
        "job-context",
        "course1",
        "N01",
        card_types=["code_snippet"],
        submit=False,
        repo=repo,
    )

    assert remote_flags == [False]

    resource_service.run_generation_job(requested["job_id"], repo=repo)

    assert remote_flags == [False, True]


def test_slot_contention_keeps_the_job_queued_and_uses_a_worker_side_retry(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    runtime.get_session("slot-contention", "course1").agent_state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    requested = resource_service.request_generation(
        "slot-contention",
        "course1",
        "N01",
        card_types=["code_snippet"],
        submit=False,
        repo=repo,
    )
    blocker = repo.try_acquire_generation_slot(1, concept_priority=False)
    assert blocker is not None
    retries: list[str] = []
    monkeypatch.setenv("EDUAGENT_RESOURCE_GLOBAL_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(
        resource_service,
        "_schedule_generation_job_retry",
        lambda job_id, *, repo: retries.append(job_id),
    )

    result = resource_service.run_generation_job(requested["job_id"], repo=repo)

    assert result is not None and result["status"] == "queued"
    assert retries == [requested["job_id"]]
    assert repo.get_job(requested["job_id"])["status"] == "queued"
    assert repo.release_generation_slot(blocker) is True


def test_worker_releases_the_global_slot_after_generation(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    runtime.get_session("slot-release", "course1").agent_state.current_node_id = "N01"
    repo = MemoryResourceGenerationRepo()
    monkeypatch.setenv("EDUAGENT_RESOURCE_GLOBAL_MAX_CONCURRENCY", "1")
    requested = resource_service.request_generation(
        "slot-release",
        "course1",
        "N01",
        card_types=["code_snippet"],
        submit=False,
        repo=repo,
    )

    resource_service.run_generation_job(requested["job_id"], repo=repo)

    assert repo.get_job(requested["job_id"])["status"] == "completed"
    next_lease = repo.try_acquire_generation_slot(1, concept_priority=False)
    assert next_lease is not None
    assert repo.release_generation_slot(next_lease) is True
