# -*- coding: utf-8 -*-
"""Stable orchestration runtime for the official learning flow.

This module owns long-lived graph/node lifecycle concerns so HTTP routes and
application services do not rebuild agents, LLM clients, or path planners.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.agents.assessment_node import AssessmentReporterNode
from src.agents.content_mesh_node import ContentMeshNode
from src.agents.evaluator_node import EvaluatorNode
from src.agents.planner_node import PlannerNode
from src.agents.profiler_node import ProfilerNode
from src.agents.tutor_node import TutorAgentNode
from src.agents.validator_node import ValidatorNode
from src.graph import get_kg_manager
from src.infrastructure.cold_start import ColdStartEngine, ColdStartState
from src.orchestration import EduAgentGraph
from src.state.agent_state import AgentState


@dataclass
class RuntimeSession:
    agent_state: AgentState
    cold_engine: ColdStartEngine
    cold_state: ColdStartState
    path_planner: Any
    pipeline_log: List[Dict[str, Any]] = field(default_factory=list)


class OrchestrationRuntime:
    """Singleton-style lifecycle holder for the official orchestration path."""

    def __init__(self) -> None:
        self._llm_client: Any = None
        self._graph: Optional[EduAgentGraph] = None
        self._sessions: Dict[str, Dict[str, RuntimeSession]] = {}
        self.kg = get_kg_manager()

        llm = self.get_llm()
        self.evaluator = EvaluatorNode()
        self.profiler = ProfilerNode(seed=42)
        self.planner = PlannerNode()
        self.tutor = TutorAgentNode(llm_generator=llm)
        self.mesh = ContentMeshNode(generate_fn=self._generate_resource_content)
        self.validator = ValidatorNode(nli_fn=llm.compute_nli_entailment if llm else None)
        self.assessment = AssessmentReporterNode(alpha=0.2)

    def get_llm(self) -> Any:
        if self._llm_client is None:
            api_key = os.environ.get("DASHSCOPE_API_KEY", "")
            if api_key and not api_key.startswith("sk-your-") and len(api_key) > 20:
                try:
                    from src.llm import LLMClientV2
                    self._llm_client = LLMClientV2(provider="qwen")
                except Exception:
                    self._llm_client = None
        return self._llm_client

    def get_graph(self) -> EduAgentGraph:
        if self._graph is None:
            self._graph = EduAgentGraph()
            llm = self.get_llm()
            if llm is not None:
                self._graph.inject_llm(llm)
            self._graph.build()
        return self._graph

    def peek_session(self, user_id: str, course_id: str = "data_structures") -> Optional[RuntimeSession]:
        return self._sessions.get(user_id, {}).get(course_id)
    def get_session(self, user_id: str, course_id: str = "data_structures") -> RuntimeSession:
        user_sessions = self._sessions.setdefault(user_id, {})
        if course_id not in user_sessions:
            self.kg.seed_course(course_id)
            target_node = "N20" if course_id == "data_structures" else "N01"
            agent_state = AgentState(
                user_id=user_id,
                course_id=course_id,
                current_node_id=None,
                target_node_id=target_node,
            )
            cold_engine = ColdStartEngine()
            user_sessions[course_id] = RuntimeSession(
                agent_state=agent_state,
                cold_engine=cold_engine,
                cold_state=cold_engine.initialize(user_id),
                path_planner=self.kg.create_path_planner(course_id),
            )
        return user_sessions[course_id]

    def replace_session_state(
        self,
        user_id: str,
        course_id: str,
        agent_state: AgentState,
        cold_state: Optional[ColdStartState] = None,
    ) -> RuntimeSession:
        session = self.get_session(user_id, course_id)
        session.agent_state = agent_state
        if cold_state is not None:
            session.cold_state = cold_state
        return session

    def reset_session(self, user_id: str, course_id: str = "data_structures") -> RuntimeSession:
        if user_id in self._sessions:
            self._sessions[user_id].pop(course_id, None)
        return self.get_session(user_id, course_id)

    def _generate_resource_content(self, node_id: str, card_type: str, difficulty: float) -> str:
        llm = self.get_llm()
        if llm is not None:
            try:
                content = llm.generate_content(node_id, card_type, difficulty)
                if content:
                    return content
            except Exception:
                pass

        title = self.kg.get_node_title(node_id) or node_id
        templates = {
            "concept_map": f"## {title}\n\nCore concept map placeholder for {node_id}.",
            "code_snippet": f"## {title}\n\n```python\n# Practice scaffold for {node_id}\npass\n```",
            "interactive_exercise": f"## {title}\n\nTry one small exercise that applies this concept.",
            "video_summary": f"## {title}\n\nShort explanation script for reviewing the idea.",
            "diagnostic_quiz": f"## {title}\n\n1. What is the key invariant of this concept?",
        }
        return templates.get(card_type, templates["concept_map"])


_runtime: Optional[OrchestrationRuntime] = None


def get_runtime() -> OrchestrationRuntime:
    global _runtime
    if _runtime is None:
        _runtime = OrchestrationRuntime()
    return _runtime
