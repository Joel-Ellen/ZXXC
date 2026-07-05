from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.infrastructure.cold_start import ColdStartEngine
from src.orchestration_runtime import RuntimeSession
from src.state.agent_state import AgentState, ResourceCard


class FakePathPlanner:
    def __init__(self, nodes=None):
        self.nodes = nodes or ["N01", "N02", "N03"]

    def compute_topological_order(self):
        return list(self.nodes)


class FakeRuntime:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, RuntimeSession]] = {}
        self.path_planner = FakePathPlanner()
        self.kg = type("FakeKg", (), {"get_node_title": lambda _, node_id: node_id})()
        self.evaluator = lambda inp: type("EvalOutput", (), {"agent_state": inp.agent_state, "cleaned_behavior": type("Cleaned", (), {"effective_correctness": 0.75, "anomaly": type("Anomaly", (), {"anomaly_type": type("A", (), {"value": "none"})()})()})(), "anomaly_detected": False, "mastery_delta": 0.0, "pid_error": 0.0, "replan_decision": type("R", (), {"value": "none"})(), "updated_mastery": 0.0})()
        self.profiler = lambda inp: type("ProfOutput", (), {"agent_state": inp.agent_state, "style_result": type("Style", (), {"selected_style": "textual", "sample_values": {}})(), "intervention_active": False, "forgetting_result": None})()
        self.mesh = lambda inp: type("MeshOutput", (), {"agent_state": inp.agent_state, "generated_cards": []})()
        self.validator = lambda inp: type("ValOutput", (), {"agent_state": inp.agent_state, "valid_cards": [], "rejected_cards": [], "refined_cards": [], "overall_pass_rate": 1.0})()
        self.assessment = lambda inp: type("AssessOutput", (), {"agent_state": inp.agent_state})()
        self.tutor = lambda inp: type("TutorOutput", (), {"agent_state": inp.agent_state})()

    def get_session(self, user_id: str, course_id: str = "data_structures") -> RuntimeSession:
        self.sessions.setdefault(user_id, {})
        if course_id not in self.sessions[user_id]:
            cold_engine = ColdStartEngine()
            self.sessions[user_id][course_id] = RuntimeSession(
                agent_state=AgentState(user_id=user_id, course_id=course_id, target_node_id="N03"),
                cold_engine=cold_engine,
                cold_state=cold_engine.initialize(user_id),
                path_planner=self.path_planner,
            )
        return self.sessions[user_id][course_id]

    def peek_session(self, user_id: str, course_id: str = "data_structures"):
        return self.sessions.get(user_id, {}).get(course_id)

    def replace_session_state(self, user_id, course_id, agent_state, cold_state=None):
        session = self.get_session(user_id, course_id)
        session.agent_state = agent_state
        if cold_state is not None:
            session.cold_state = cold_state
        return session

    def reset_session(self, user_id, course_id="data_structures"):
        self.sessions.get(user_id, {}).pop(course_id, None)
        return self.get_session(user_id, course_id)

    def _generate_resource_content(self, node_id, card_type, difficulty):
        return f"## {node_id} {card_type}\n\ncontent"


class FakeValidationPipeline:
    def __init__(self, pass_resource=True, pass_tutor=True):
        self.pass_resource = pass_resource
        self.pass_tutor = pass_tutor

    def validate_resource_card(self, card, ground_truth_context=""):
        from src.validation.result import ValidationResult
        result = ValidationResult()
        if not self.pass_resource:
            result.add_issue("forced_reject", "forced reject")
            return None, result
        return card, result

    def validate_input(self, text="", payload=None, field="input"):
        from src.validation.result import ValidationResult
        result = ValidationResult()
        result.sanitized_text = text
        return result

    def validate_tutor_response(self, response):
        from src.validation.result import ValidationResult
        result = ValidationResult()
        if not self.pass_tutor:
            result.add_issue("forced_tutor_reject", "forced tutor reject")
            response = {"text_explanation": "blocked", "blocked": True, "validation": result.to_contract_validation()}
            return response, result
        response = dict(response or {})
        response["validation"] = result.to_contract_validation()
        return response, result


def install_fake_runtime(monkeypatch):
    fake = FakeRuntime()
    monkeypatch.setattr("src.application._common.get_runtime", lambda: fake)
    monkeypatch.setattr("src.orchestration_runtime.get_runtime", lambda: fake)
    monkeypatch.setattr("src.application.session_service.get_runtime", lambda: fake)
    monkeypatch.setattr("src.application.resource_service.get_runtime", lambda: fake, raising=False)
    monkeypatch.setattr("src.application.tutor_service.get_runtime", lambda: fake, raising=False)
    return fake


def disable_persistence(monkeypatch):
    monkeypatch.setattr("src.application._common.persist_session", lambda session: None)
    monkeypatch.setattr("src.application.session_service.persist_session", lambda session: None)
    monkeypatch.setattr("src.application.resource_service.persist_session", lambda session: None)
    monkeypatch.setattr("src.application.tutor_service.persist_session", lambda session: None)
    monkeypatch.setattr("src.application._common.load_persisted_session", lambda user_id, course_id="data_structures": None)
