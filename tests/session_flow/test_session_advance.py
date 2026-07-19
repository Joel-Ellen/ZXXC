from src.application import session_service
from tests.helpers import disable_persistence, install_fake_runtime
from src.orchestration_core import run_official_learning_step
from src.state.agent_state import ResourceCard


def test_session_advance_load_node_happy_path(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session_service.init_path("u3", "course1")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("load_node should not invoke heavy resource generation")

    fake.mesh = fail_if_called
    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", fail_if_called)

    response = session_service.advance_session(
        "u3",
        "course1",
        behavior={"interaction_type": "load_node", "current_node_id": "N01"},
    )
    assert response["interaction_type"] == "load_node"
    assert response["current_node_id"] == "N01"
    assert any(log["agent"] == "Planner" for log in response["step_logs"])


def test_verified_completion_enqueues_missing_resources_without_sync_generation(monkeypatch):
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session = runtime.get_session("u4", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01"]
    state.generated_resources["N01"] = [
        ResourceCard(
            resource_id="N01_diagnostic_quiz_supp",
            node_id="N01",
            card_type="diagnostic_quiz",
            content="## Diagnostic quiz",
            metadata={
                "structured_payload": {
                    "questions": [
                        {
                            "id": "N01-q1",
                            "prompt": "哪项描述符合当前节点？",
                            "options": ["选项 A", "选项 B", "选项 C", "选项 D"],
                            "answer_index": 1,
                        },
                    ]
                }
            },
        )
    ]
    queued = []

    def enqueue(user_id, course_id, node_id, **kwargs):
        queued.append({
            "user_id": user_id,
            "course_id": course_id,
            "node_id": node_id,
            **kwargs,
        })
        return {
            "status": "queued",
            "job_id": "resource-job-1",
            "missing_card_types": kwargs["card_types"],
        }

    def fail_if_sync_generation(*args, **kwargs):
        raise AssertionError("learning orchestration must not synchronously generate resources")

    monkeypatch.setattr("src.application.resource_service.request_generation", enqueue)
    monkeypatch.setattr(
        "src.application.resource_service.generate_current_node_resources",
        fail_if_sync_generation,
    )

    result = run_official_learning_step(
        session,
        behavior={
            "interaction_type": "complete_learning",
            "current_node_id": "N01",
            "resource_id": "N01_diagnostic_quiz_supp",
            "answers": [{"question_id": "N01-q1", "selected_option_index": 1}],
        },
        runtime=runtime,
    )

    assert queued == [{
        "user_id": "u4",
        "course_id": "course1",
        "node_id": "N01",
        "card_types": ["concept_map"],
        "force": False,
        "priority": "concept_map",
    }]
    mesh_log = next(log for log in result.logs if log["agent"] == "ContentMesh")
    assert mesh_log["status"] == "queued"
    assert mesh_log["job_id"] == "resource-job-1"
