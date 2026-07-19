"""Direct assertions for the concurrency/reliability guarantees of the async
resource generation subsystem.

These lock down behaviors that were implemented but only exercised indirectly:
  R1 - a global slot cap limits concurrency and reserves a lane for concept
       maps, and a slot-contended job reschedules instead of blocking a worker.
  R2 - an identical in-flight request merges via the idempotency key instead of
       creating a duplicate job.
  R3 - each card is persisted independently, so one card's failure never
       discards an already-completed card.
"""

from __future__ import annotations

from dataclasses import replace

from src.application import resource_service
from src.database.resource_generation_repo import (
    MemoryResourceGenerationRepo,
    _MemoryGenerationStore,
)
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


def _fresh_repo() -> MemoryResourceGenerationRepo:
    # An isolated store keeps slot/job state out of the process-global default.
    return MemoryResourceGenerationRepo(store=_MemoryGenerationStore())


# --- R1: global concurrency cap + reserved concept lane -----------------------


def test_global_slot_cap_blocks_a_second_job_until_the_first_releases() -> None:
    repo = _fresh_repo()

    first = repo.try_acquire_generation_slot(1, concept_priority=True)
    assert first is not None and first.slot == 0

    # The single global slot is taken; a second acquisition must not succeed.
    assert repo.try_acquire_generation_slot(1, concept_priority=True) is None

    assert repo.release_generation_slot(first) is True
    reacquired = repo.try_acquire_generation_slot(1, concept_priority=True)
    assert reacquired is not None and reacquired.slot == 0


def test_supporting_bundle_cannot_take_the_reserved_concept_slot() -> None:
    repo = _fresh_repo()

    # With two slots, supporting bundles may only use slot 1; slot 0 is reserved.
    supporting = repo.try_acquire_generation_slot(2, concept_priority=False)
    assert supporting is not None and supporting.slot == 1

    # No non-reserved slot remains, so a second supporting bundle is refused.
    assert repo.try_acquire_generation_slot(2, concept_priority=False) is None

    # A concept-priority job is still admitted onto the reserved slot 0.
    concept = repo.try_acquire_generation_slot(2, concept_priority=True)
    assert concept is not None and concept.slot == 0


def test_slot_contention_reschedules_without_running_or_blocking(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    monkeypatch.setenv("EDUAGENT_RESOURCE_GLOBAL_MAX_CONCURRENCY", "1")
    repo = _fresh_repo()

    session = runtime.get_session("slot-user", "course1")
    session.agent_state.current_node_id = "N01"
    queued = resource_service.request_generation(
        "slot-user",
        "course1",
        "N01",
        card_types=["concept_map"],
        priority="concept_map",
        submit=False,
        repo=repo,
    )
    job_id = queued["job_id"]

    # Saturate the only global slot so the worker cannot claim one.
    held = repo.try_acquire_generation_slot(1, concept_priority=True)
    assert held is not None

    rescheduled: list[str] = []
    monkeypatch.setattr(
        resource_service,
        "_schedule_generation_job_retry",
        lambda jid, *, repo: rescheduled.append(jid),
    )

    result = resource_service.run_generation_job(job_id, repo=repo)

    # The worker returned immediately, left the job queued, and requested a retry
    # instead of doing any model work.
    assert result["status"] == "queued"
    assert rescheduled == [job_id]
    assert session.agent_state.generated_resources.get("N01", []) == []
    progress = repo.get_job(job_id)["progress"]
    assert progress.get("completed_card_types", []) == []


# --- R2: idempotent merge of identical in-flight requests ---------------------


def test_duplicate_request_merges_into_the_existing_job(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    repo = _fresh_repo()

    session = runtime.get_session("dedup-user", "course1")
    session.agent_state.current_node_id = "N01"

    first = resource_service.request_generation(
        "dedup-user",
        "course1",
        "N01",
        card_types=["concept_map"],
        submit=False,
        repo=repo,
    )
    second = resource_service.request_generation(
        "dedup-user",
        "course1",
        "N01",
        card_types=["concept_map"],
        submit=False,
        repo=repo,
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["job_id"] == first["job_id"]
    # The duplicate attached to the in-flight job; no second row was created.
    assert list(repo._store.jobs.keys()) == [first["job_id"]]


def test_worker_rejects_a_job_when_the_knowledge_version_changes(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        resource_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    repo = _fresh_repo()
    session = runtime.get_session("version-race-user", "course1")
    session.agent_state.current_node_id = "N01"
    queued = resource_service.request_generation(
        "version-race-user",
        "course1",
        "N01",
        card_types=["concept_map"],
        submit=False,
        repo=repo,
    )
    original_context = resource_service._generation_context

    def changed_context(*args, **kwargs):
        binding, context = original_context(*args, **kwargs)
        return binding, replace(
            context,
            knowledge_index_version=f"{context.knowledge_index_version}-changed",
        )

    monkeypatch.setattr(resource_service, "_generation_context", changed_context)

    result = resource_service.run_generation_job(queued["job_id"], repo=repo)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "knowledge_index_version_changed"
    assert session.agent_state.generated_resources.get("N01", []) == []


# --- R3: independent per-card persistence and failure isolation ---------------


def test_one_card_failure_keeps_the_completed_card_persisted(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    repo = _fresh_repo()

    session = runtime.get_session("isolation-user", "course1")
    session.agent_state.current_node_id = "N01"

    # Drop the supporting card so it fails to generate, while concept_map is fine.
    real_generate_phase = resource_service._generate_phase

    def flaky_generate_phase(runtime_arg, context, card_types):
        generated = real_generate_phase(runtime_arg, context, card_types)
        generated.pop("code_snippet", None)
        return generated

    monkeypatch.setattr(resource_service, "_generate_phase", flaky_generate_phase)

    queued = resource_service.request_generation(
        "isolation-user",
        "course1",
        "N01",
        card_types=["concept_map", "code_snippet"],
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(queued["job_id"], repo=repo)

    persisted = session.agent_state.generated_resources.get("N01", [])
    persisted_types = {card.card_type for card in persisted}
    assert "concept_map" in persisted_types
    assert "code_snippet" not in persisted_types

    concept_card = next(card for card in persisted if card.card_type == "concept_map")
    # The offline fallback keeps its explicit template provenance marker.
    assert concept_card.metadata["generation"]["source"] == "template"

    progress = repo.get_job(queued["job_id"])["progress"]
    assert "concept_map" in progress["completed_card_types"]
    assert "code_snippet" in progress["failed_card_types"]
