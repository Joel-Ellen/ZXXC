from __future__ import annotations

from src.application import resource_service
from src.application import _common
from src.database.resource_generation_repo import MemoryResourceGenerationRepo, ResourceGenerationRepo
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


def test_get_resources_serves_a_validated_generic_cache_without_creating_a_session(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    repo = MemoryResourceGenerationRepo()

    source_session = runtime.get_session("cache-source", "course1")
    source_session.agent_state.current_node_id = "N01"
    generated = resource_service.request_generation(
        "cache-source",
        "course1",
        "N01",
        card_types=["concept_map"],
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(generated["job_id"], repo=repo)

    base = repo.get_base_cache(
        "course1",
        "N01",
        "concept_map",
        content_version="resource-v3",
        knowledge_index_version="course-catalog-v1",
    )
    assert base is not None
    assert base["metadata"]["cache_scope"] == "course_base"
    assert base["payload"]["metadata"]["cache_scope"] == "course_base"

    def must_not_persist(*_args, **_kwargs):
        raise AssertionError("GET cache reads must not persist a session")

    def must_not_enqueue(*_args, **_kwargs):
        raise AssertionError("GET cache reads must not enqueue generation")

    monkeypatch.setattr(resource_service, "persist_session", must_not_persist)
    monkeypatch.setattr(resource_service, "request_generation", must_not_enqueue)

    result = resource_service.get_node_resources(
        "cache-reader",
        "course1",
        "N01",
        card_types=["concept_map"],
        repo=repo,
    )

    assert runtime.peek_session("cache-reader", "course1") is None
    assert result["missing_card_types"] == []
    assert [card["resource_type"] for card in result["resources"]] == ["concept_map"]
    assert result["resources"][0]["generation"]["cache_hit"] is True
    assert result["resources"][0]["generation"]["cache_scope"] == "course_base"
    assert result["resources"][0]["personalization_basis"]["cognitive_style"] == "textual"


def test_personalized_generation_never_populates_the_course_base_cache(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    repo = MemoryResourceGenerationRepo()

    source_session = runtime.get_session("cache-source", "course1")
    source_session.agent_state.current_node_id = "N01"
    source_session.agent_state.internal_state["recent_error_signature"] = "off_by_one"
    generated = resource_service.request_generation(
        "cache-source",
        "course1",
        "N01",
        card_types=["interactive_exercise"],
        submit=False,
        repo=repo,
    )
    resource_service.run_generation_job(generated["job_id"], repo=repo)

    base = repo.get_base_cache(
        "course1",
        "N01",
        "interactive_exercise",
        content_version="resource-v3",
        knowledge_index_version="course-catalog-v1",
    )
    personal = repo.get_personal_cache(
        "cache-source",
        "course1",
        "N01",
        "interactive_exercise",
        mastery_bucket="developing",
        error_signature="off_by_one",
        cognitive_style="textual",
        content_version="resource-v3",
        knowledge_index_version="course-catalog-v1",
    )
    assert base is None
    assert personal is not None
    assert personal["payload"]["metadata"]["structured_payload"]["error_signature"] == "off_by_one"

    result = resource_service.get_node_resources(
        "cache-reader",
        "course1",
        "N01",
        card_types=["interactive_exercise"],
        repo=repo,
    )

    assert result["resources"] == []
    assert result["missing_card_types"] == ["interactive_exercise"]


def test_course_cache_rejects_records_without_the_generic_context_policy() -> None:
    assert resource_service._is_generic_base_cache({
        "metadata": {"cache_scope": "course_base"},
    }) is False


def test_generic_base_cache_read_executes_only_a_select_without_schema_setup() -> None:
    row = {
        "course_id": "course1",
        "node_id": "N01",
        "resource_type": "concept_map",
        "content_version": "resource-v3",
        "locale": "zh-CN",
        "knowledge_index_version": "course-catalog-v1",
        "payload": {},
        "source_refs": [],
        "metadata": {"cache_scope": "course_base"},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    class Cursor:
        def fetchone(self):
            return row

    class ReadOnlyDatabase:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement, _params=()):
            self.statements.append(statement)
            return Cursor()

        def commit(self):
            raise AssertionError("a pure cache read must not commit")

    database = ReadOnlyDatabase()
    repo = ResourceGenerationRepo(database=database, allow_memory_fallback=False)

    result = repo.read_base_cache(
        "course1",
        "N01",
        "concept_map",
        content_version="resource-v3",
        knowledge_index_version="course-catalog-v1",
    )

    assert result is not None
    assert len(database.statements) == 1
    assert database.statements[0].lstrip().upper().startswith("SELECT")


def test_resource_read_does_not_hydrate_a_missing_persisted_runtime_session(monkeypatch) -> None:
    class Runtime:
        def peek_session(self, _user_id, _course_id):
            return None

        def replace_session_state(self, *_args, **_kwargs):
            raise AssertionError("resource GET must not replace runtime session state")

    runtime = Runtime()
    monkeypatch.setattr(resource_service, "get_runtime", lambda: runtime)

    def must_not_restore(*_args, **_kwargs):
        raise AssertionError("resource GET must not load and hydrate a persisted session")

    monkeypatch.setattr(_common, "load_persisted_session", must_not_restore)

    assert resource_service._read_session("read-only-user", "course1") is None
