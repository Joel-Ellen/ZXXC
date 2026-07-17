import json

from src.application import _common, profile_service, resource_service, session_service, tutor_service
from tests.helpers import FakeValidationPipeline, install_fake_runtime


class _AuditStore:
    def __init__(self):
        self.snapshots = {}
        self.states = {}
        self.sessions = {}
        self.deleted_snapshots = []
        self.deleted_states = []
        self.deleted_sessions = []


def _as_payload(value):
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _install_audit_repos(monkeypatch):
    store = _AuditStore()

    class AuditSessionRepo:
        @staticmethod
        def build_session_id(user_id, course_id):
            return f"{user_id}:{course_id}"

        def upsert(self, user_id, course_id, **kwargs):
            key = (user_id, course_id)
            current = dict(store.sessions.get(key, {}))
            current.update({"user_id": user_id, "course_id": course_id, **kwargs})
            store.sessions[key] = current
            return current

        def delete(self, user_id, course_id):
            store.deleted_sessions.append((user_id, course_id))
            store.sessions.pop((user_id, course_id), None)

    class AuditSnapshotRepo:
        def get_latest(self, user_id, course_id):
            items = store.snapshots.get((user_id, course_id), [])
            return items[-1] if items else None

        def next_version(self, user_id, course_id):
            latest = self.get_latest(user_id, course_id)
            return int(latest["version"] if latest else 0) + 1

        def save_snapshot(
            self,
            user_id,
            course_id,
            state_json,
            cold_state_json=None,
            path_json=None,
            profile_json=None,
            resource_bundle_json=None,
            assessment_json=None,
            pipeline_log_json=None,
        ):
            version = self.next_version(user_id, course_id)
            snapshot = {
                "session_id": AuditSessionRepo.build_session_id(user_id, course_id),
                "user_id": user_id,
                "course_id": course_id,
                "version": version,
                "state_json": _as_payload(state_json),
                "cold_state_json": _as_payload(cold_state_json),
                "path_json": path_json or {},
                "profile_json": profile_json or {},
                "resource_bundle_json": resource_bundle_json or {},
                "assessment_json": assessment_json or {},
                "pipeline_log_json": pipeline_log_json or [],
            }
            store.snapshots.setdefault((user_id, course_id), []).append(snapshot)
            AuditSessionRepo().upsert(
                user_id,
                course_id,
                current_node_id=snapshot["state_json"].get("current_node_id"),
                target_node_id=snapshot["state_json"].get("target_node_id"),
                snapshot_version=version,
                profile_version=version,
                path_version=version,
                resource_bundle_version=version,
                assessment_version=version,
            )
            return snapshot

        def delete_for_session(self, user_id, course_id):
            store.deleted_snapshots.append((user_id, course_id))
            store.snapshots.pop((user_id, course_id), None)

    class AuditStateRepo:
        def save_state(self, user_id, course_id, state_json, cold_state_json=None):
            store.states[(user_id, course_id)] = {
                "state_json": _as_payload(state_json),
                "cold_state_json": _as_payload(cold_state_json),
            }

        def load_state(self, user_id, course_id):
            return store.states.get((user_id, course_id))

        def delete_state(self, user_id, course_id):
            store.deleted_states.append((user_id, course_id))
            store.states.pop((user_id, course_id), None)

    monkeypatch.setattr(_common, "SessionRepo", AuditSessionRepo)
    monkeypatch.setattr(_common, "SessionSnapshotRepo", AuditSnapshotRepo)
    monkeypatch.setattr(_common, "StateRepo", AuditStateRepo)
    return store


def _latest(store, user_id, course_id):
    return store.snapshots[(user_id, course_id)][-1]


def _audit_context(monkeypatch):
    fake_runtime = install_fake_runtime(monkeypatch)
    store = _install_audit_repos(monkeypatch)
    monkeypatch.setattr(resource_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    monkeypatch.setattr(tutor_service, "get_validation_pipeline", lambda: FakeValidationPipeline())
    return fake_runtime, store


def test_session_create_always_persists_initial_snapshot(monkeypatch):
    _, store = _audit_context(monkeypatch)

    response = session_service.create_session("audit-create", "course1")

    assert response["session"]["user_id"] == "audit-create"
    assert len(store.snapshots[("audit-create", "course1")]) == 1
    assert ("audit-create", "course1") in store.states
    assert store.sessions[("audit-create", "course1")]["snapshot_version"] == 1


def test_cold_start_state_is_restored_from_latest_snapshot(monkeypatch):
    fake_runtime, store = _audit_context(monkeypatch)

    profile_service.submit_probe_answer("audit-cold", "course1", "visual")
    latest = _latest(store, "audit-cold", "course1")
    fake_runtime.sessions.clear()

    restored = _common.load_persisted_session("audit-cold", "course1")

    assert restored is not None
    assert restored.agent_state.internal_state["_cold_start_answers"] == ["visual"]
    assert json.loads(restored.cold_state.model_dump_json()) == latest["cold_state_json"]


def test_generated_resources_are_persisted_in_state_and_resource_bundle(monkeypatch):
    _, store = _audit_context(monkeypatch)

    result = resource_service.generate_current_node_resources("audit-resource", "course1", "N01", force=True)
    latest = _latest(store, "audit-resource", "course1")

    assert result["node_id"] == "N01"
    assert len(latest["state_json"]["generated_resources"]["N01"]) == 5
    assert len(latest["resource_bundle_json"]["N01"]) == 5
    assert store.sessions[("audit-resource", "course1")]["resource_bundle_version"] == latest["version"]


def test_tutor_response_is_persisted(monkeypatch):
    fake_runtime, store = _audit_context(monkeypatch)

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {
            "text_explanation": "Persisted tutor response",
            "mermaid_src": "",
            "query": "What is N01?",
        }
        return type("TutorOutput", (), {"agent_state": inp.agent_state})()

    monkeypatch.setattr(fake_runtime, "tutor", fake_tutor)
    tutor_service.run_tutor("audit-tutor", "course1", "What is N01?")
    latest = _latest(store, "audit-tutor", "course1")

    assert latest["state_json"]["tutor_response"]["text_explanation"] == "Persisted tutor response"
    assert latest["state_json"]["agent_feedback"][0]["agent"] == "Tutor"


def test_replan_persists_path_and_version_update(monkeypatch):
    _, store = _audit_context(monkeypatch)
    session_service.init_path("audit-replan", "course1")
    before_version = _latest(store, "audit-replan", "course1")["version"]

    response = session_service.request_replan("audit-replan", "course1", payload={"reason": "audit"})
    latest = _latest(store, "audit-replan", "course1")

    assert response["interaction_type"] == "load_node"
    assert latest["version"] > before_version
    assert latest["path_json"]["nodes"]
    assert latest["state_json"]["re_plan_triggered"] is False
    assert store.sessions[("audit-replan", "course1")]["path_version"] == latest["version"]


def test_session_reset_deletes_old_snapshots_and_persists_clean_session(monkeypatch):
    _, store = _audit_context(monkeypatch)
    resource_service.generate_current_node_resources("audit-reset", "course1", "N01", force=True)
    assert len(store.snapshots[("audit-reset", "course1")]) >= 1

    response = session_service.reset_learning_session("audit-reset", "course1")
    latest = _latest(store, "audit-reset", "course1")

    assert response["status"] == "ok"
    assert store.deleted_snapshots == [("audit-reset", "course1")]
    assert store.deleted_states == [("audit-reset", "course1")]
    assert store.deleted_sessions == [("audit-reset", "course1")]
    assert len(store.snapshots[("audit-reset", "course1")]) == 1
    assert latest["state_json"]["generated_resources"] == {}
    assert latest["state_json"]["tutor_response"] is None
