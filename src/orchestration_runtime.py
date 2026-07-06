# -*- coding: utf-8 -*-
"""Stable orchestration runtime for the official learning flow."""

from __future__ import annotations

import concurrent.futures
import os
import time
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
from src.observability import incr_metric, log_event
from src.orchestration_core import EduAgentGraph
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
        self._llm_clients: Dict[str, Any] = {}
        self._graph: Optional[EduAgentGraph] = None
        self._sessions: Dict[str, Dict[str, RuntimeSession]] = {}
        self._resource_llm_timeout_sec = self._read_float_env("EDUAGENT_RESOURCE_LLM_TIMEOUT_SEC", 4.0)
        self._resource_llm_retries = self._read_int_env("EDUAGENT_RESOURCE_LLM_RETRIES", 2)
        self._resource_llm_retry_backoff_sec = self._read_float_env(
            "EDUAGENT_RESOURCE_LLM_RETRY_BACKOFF_SEC",
            0.25,
        )
        self._resource_generation_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._read_int_env("EDUAGENT_RESOURCE_LLM_WORKERS", 2),
            thread_name_prefix="eduagent-resource-llm",
        )
        self._llm_provider_order = self._build_provider_order()
        self.kg = get_kg_manager()

        llm = self.get_llm()
        self.evaluator = EvaluatorNode()
        self.profiler = ProfilerNode(seed=42)
        self.planner = PlannerNode()
        self.tutor = TutorAgentNode(llm_generator=llm)
        self.mesh = ContentMeshNode(generate_fn=self._generate_resource_content)
        self.validator = ValidatorNode(nli_fn=llm.compute_nli_entailment if llm else None)
        self.assessment = AssessmentReporterNode(alpha=0.2)

    def _build_provider_order(self) -> List[str]:
        primary = (os.environ.get("LLM_PROVIDER") or "qwen").strip().lower()
        fallbacks = [
            provider.strip().lower()
            for provider in os.environ.get("EDUAGENT_LLM_FALLBACKS", "deepseek,openai").split(",")
            if provider.strip()
        ]
        ordered: List[str] = []
        for provider in [primary, *fallbacks]:
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    @staticmethod
    def _provider_has_credentials(provider: str) -> bool:
        if provider in {"qwen", "dashscope"}:
            key = os.environ.get("DASHSCOPE_API_KEY", "")
            return bool(key and not key.startswith("sk-your-") and len(key) > 20)
        if provider == "deepseek":
            return bool(os.environ.get("DEEPSEEK_API_KEY", ""))
        if provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY", ""))
        if provider == "spark":
            return all(
                os.environ.get(name, "")
                for name in ("SPARK_API_KEY", "SPARK_APP_ID", "SPARK_API_SECRET")
            )
        return False

    def _get_or_create_llm_for_provider(self, provider: str) -> Any:
        if provider in self._llm_clients:
            return self._llm_clients[provider]
        if not self._provider_has_credentials(provider):
            return None
        try:
            from src.llm import LLMClientV2

            client = LLMClientV2(provider=provider)
            self._llm_clients[provider] = client
            log_event("llm.client.ready", provider=provider)
            return client
        except Exception as exc:
            incr_metric("llm.init_failure_total", provider=provider)
            log_event("llm.client.init_failed", level="warning", provider=provider, error=str(exc))
            return None

    def get_llm(self) -> Any:
        if self._llm_client is not None:
            return self._llm_client
        for provider in self._llm_provider_order:
            client = self._get_or_create_llm_for_provider(provider)
            if client is not None:
                self._llm_client = client
                if provider != self._llm_provider_order[0]:
                    incr_metric(
                        "llm.fallback_total",
                        operation="runtime_init",
                        fallback=provider,
                    )
                return client
        return None

    @staticmethod
    def _read_float_env(name: str, default: float) -> float:
        try:
            return max(0.1, float(os.environ.get(name, str(default))))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, str(default))))
        except (TypeError, ValueError):
            return default

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

    def _candidate_llms(self) -> List[tuple[str, Any]]:
        candidates: List[tuple[str, Any]] = []
        current = self.get_llm()
        if current is not None:
            candidates.append((getattr(current, "provider", "primary"), current))
        for provider in self._llm_provider_order:
            client = self._get_or_create_llm_for_provider(provider)
            if client is None:
                continue
            if any(existing is client for _, existing in candidates):
                continue
            candidates.append((provider, client))
        return candidates

    def _generate_resource_content(self, node_id: str, card_type: str, difficulty: float) -> str:
        candidates = self._candidate_llms()
        for provider_name, llm in candidates:
            for attempt in range(1, self._resource_llm_retries + 1):
                future = self._resource_generation_pool.submit(
                    llm.generate_content,
                    node_id,
                    card_type,
                    difficulty,
                )
                try:
                    content = future.result(timeout=self._resource_llm_timeout_sec)
                    if content:
                        if provider_name != candidates[0][0]:
                            incr_metric(
                                "llm.fallback_total",
                                operation="resource_generation",
                                fallback=provider_name,
                            )
                        return content
                    raise RuntimeError("empty_llm_content")
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    incr_metric("llm.timeout_total", operation="resource_generation", provider=provider_name)
                    log_event(
                        "llm.resource.timeout",
                        level="warning",
                        provider=provider_name,
                        card_type=card_type,
                        attempt=attempt,
                        timeout_sec=self._resource_llm_timeout_sec,
                    )
                except Exception as exc:
                    incr_metric("llm.error_total", operation="resource_generation", provider=provider_name)
                    log_event(
                        "llm.resource.error",
                        level="warning",
                        provider=provider_name,
                        card_type=card_type,
                        attempt=attempt,
                        error=str(exc),
                    )
                if attempt < self._resource_llm_retries:
                    time.sleep(self._resource_llm_retry_backoff_sec * attempt)

        incr_metric("llm.fallback_total", operation="resource_generation", fallback="template")
        return self._template_resource_content(node_id, card_type)

    def _template_resource_content(self, node_id: str, card_type: str) -> str:
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
