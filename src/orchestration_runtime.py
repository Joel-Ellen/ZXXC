# -*- coding: utf-8 -*-
"""Stable orchestration runtime for the official learning flow."""

from __future__ import annotations

import concurrent.futures
import inspect
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
from src.resource_generation import TEMPLATE_NOTICE
from src.resource_generation.services import CircuitBreaker
from src.orchestration_core import EduAgentGraph
from src.state.agent_state import AgentState


@dataclass
class RuntimeSession:
    agent_state: AgentState
    cold_engine: ColdStartEngine
    cold_state: ColdStartState
    path_planner: Any
    pipeline_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ResourceGenerationResult:
    """The content and provenance of one resource-generation attempt."""

    content: str
    source: str
    provider: Optional[str] = None
    model: Optional[str] = None
    attempt_count: int = 0
    fallback_reason: Optional[str] = None
    elapsed_ms: float = 0.0
    structured_payload: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0

    def to_metadata(self) -> Dict[str, Any]:
        """Return learner-safe provenance suitable for the resource contract."""
        metadata: Dict[str, Any] = {
            "source": self.source,
            "attempt_count": self.attempt_count,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.provider:
            metadata["provider"] = self.provider
        if self.model:
            metadata["model"] = self.model
        if self.fallback_reason:
            metadata["fallback_reason"] = self.fallback_reason
        return metadata


class OrchestrationRuntime:
    """Singleton-style lifecycle holder for the official orchestration path."""

    def __init__(self) -> None:
        self._llm_client: Any = None
        self._llm_clients: Dict[str, Any] = {}
        self._graph: Optional[EduAgentGraph] = None
        self._sessions: Dict[str, Dict[str, RuntimeSession]] = {}
        # Resource work runs out of band.  Keep each provider attempt short so
        # a slow model cannot pin a worker or delay concept-map first paint.
        self._resource_llm_timeout_sec = self._read_float_env("EDUAGENT_RESOURCE_LLM_TIMEOUT_SEC", 18.0)
        self._resource_llm_total_timeout_sec = max(
            self._resource_llm_timeout_sec,
            self._read_float_env("EDUAGENT_RESOURCE_LLM_TOTAL_TIMEOUT_SEC", 20.0),
        )
        # One bounded attempt is the default.  Deployments with a reliable
        # secondary provider may explicitly opt into another attempt.
        configured_retries = self._read_int_env("EDUAGENT_RESOURCE_LLM_RETRIES", 1)
        environment = str(
            os.environ.get("APP_ENV")
            or os.environ.get("ENVIRONMENT")
            or ""
        ).strip().lower()
        self._resource_llm_retries = (
            1 if environment in {"prod", "production"} else configured_retries
        )
        self._resource_llm_retry_backoff_sec = self._read_float_env(
            "EDUAGENT_RESOURCE_LLM_RETRY_BACKOFF_SEC",
            0.25,
        )
        self._resource_generation_parallelism = min(
            5,
            self._read_int_env("EDUAGENT_RESOURCE_LLM_PARALLELISM", 3),
        )
        self._resource_generation_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(
                self._resource_generation_parallelism,
                min(8, self._read_int_env("EDUAGENT_RESOURCE_LLM_WORKERS", 3)),
            ),
            thread_name_prefix="eduagent-resource-llm",
        )
        self._llm_provider_order = self._build_provider_order()
        self._provider_breakers = {
            provider: CircuitBreaker(failure_threshold=3, open_seconds=30.0)
            for provider in self._llm_provider_order
        }
        self.kg = get_kg_manager()

        llm = self.get_llm()
        self.evaluator = EvaluatorNode()
        self.profiler = ProfilerNode(seed=42)
        self.planner = PlannerNode()
        self.tutor = TutorAgentNode(llm_generator=llm)
        self.mesh = ContentMeshNode(generate_fn=self.generate_resource_content)
        self.validator = ValidatorNode(nli_fn=llm.compute_nli_entailment if llm else None)
        self.assessment = AssessmentReporterNode(alpha=0.2)

    @staticmethod
    def _canonical_provider(provider: str) -> str:
        aliases = {
            "qwen": "dashscope",
            "iflytek": "spark",
        }
        normalized = str(provider or "").strip().lower()
        return aliases.get(normalized, normalized)

    def _build_provider_order(self) -> List[str]:
        primary = self._canonical_provider(os.environ.get("LLM_PROVIDER") or "dashscope")
        fallbacks = [
            self._canonical_provider(provider)
            for provider in os.environ.get("EDUAGENT_LLM_FALLBACKS", "deepseek,openai").split(",")
            if provider.strip()
        ]
        ordered: List[str] = []
        for provider in [primary, *fallbacks]:
            environment = str(
                os.environ.get("APP_ENV")
                or os.environ.get("ENVIRONMENT")
                or ""
            ).strip().lower()
            if environment in {"prod", "production"}:
                allowed = {
                    self._canonical_provider(value)
                    for value in os.environ.get(
                        "EDUAGENT_RESOURCE_DOMESTIC_PROVIDERS",
                        "dashscope,deepseek,spark",
                    ).split(",")
                    if value.strip()
                }
                if provider not in allowed:
                    continue
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    @staticmethod
    def _usable_secret(value: str, *, minimum_length: int = 8) -> bool:
        normalized = str(value or "").strip()
        if len(normalized) < minimum_length:
            return False
        placeholder_markers = (
            "placeholder",
            "your-",
            "sk-your-",
            "change-me",
            "example",
            "replace-me",
        )
        return not normalized.lower().startswith(placeholder_markers)

    @classmethod
    def _provider_has_credentials(cls, provider: str) -> bool:
        provider = cls._canonical_provider(provider)
        if provider == "dashscope":
            return cls._usable_secret(os.environ.get("DASHSCOPE_API_KEY", ""), minimum_length=20)
        if provider == "deepseek":
            return cls._usable_secret(os.environ.get("DEEPSEEK_API_KEY", ""))
        if provider == "openai":
            return cls._usable_secret(os.environ.get("OPENAI_API_KEY", ""))
        if provider == "spark":
            return all(
                cls._usable_secret(os.environ.get(name, ""))
                for name in ("SPARK_API_KEY", "SPARK_APP_ID", "SPARK_API_SECRET")
            )
        return False

    def _get_or_create_llm_for_provider(self, provider: str) -> Any:
        provider = self._canonical_provider(provider)
        if provider in self._llm_clients:
            return self._llm_clients[provider]
        if not self._provider_has_credentials(provider):
            return None
        try:
            # Resolve the concrete client here so optional provider-import
            # failures are handled by this runtime's fallback path directly.
            from src.llm.client_v2 import LLMClientV2

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
                path_planner=self.kg.create_path_planner(course_id, local_only=True),
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

    def drop_session(self, user_id: str, course_id: str = "data_structures") -> None:
        """Evict a runtime session without creating a replacement."""
        user_sessions = self._sessions.get(user_id)
        if user_sessions is None:
            return
        user_sessions.pop(course_id, None)
        if not user_sessions:
            self._sessions.pop(user_id, None)

    def drop_user_sessions(self, user_id: str) -> None:
        """Evict every in-process learning session for an account."""
        self._sessions.pop(user_id, None)

    def _candidate_llms(self) -> List[tuple[str, Any]]:
        candidates: List[tuple[str, Any]] = []
        current = self.get_llm()
        if current is not None:
            candidates.append((self._canonical_provider(getattr(current, "provider", "primary")), current))
        for provider in self._llm_provider_order:
            provider = self._canonical_provider(provider)
            breaker = self._provider_breakers.get(provider)
            if breaker is not None and not breaker.allow():
                continue
            client = self._get_or_create_llm_for_provider(provider)
            if client is None:
                continue
            if any(existing is client for _, existing in candidates):
                continue
            candidates.append((provider, client))
        return candidates

    def _provider_success(self, provider: str) -> None:
        breaker = self._provider_breakers.get(self._canonical_provider(provider))
        if breaker is not None:
            breaker.success()

    def _provider_failure(self, provider: str) -> None:
        breaker = self._provider_breakers.get(self._canonical_provider(provider))
        if breaker is not None:
            breaker.failure()

    @staticmethod
    def _llm_model_name(llm: Any) -> Optional[str]:
        config = getattr(llm, "config", None)
        if isinstance(config, dict):
            model = str(config.get("model") or "").strip()
            return model or None
        return None

    @staticmethod
    def _llm_supports_resource_parameter(generate_content: Any, name: str) -> bool:
        try:
            parameters = inspect.signature(generate_content).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            parameter.name == name
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _call_resource_generator(
        self,
        llm: Any,
        node_id: str,
        card_type: str,
        difficulty: float,
        timeout_sec: float,
        course_id: str,
        node_title: str,
    ) -> str:
        generate_content = llm.generate_content
        kwargs: Dict[str, Any] = {}
        if self._llm_supports_resource_parameter(generate_content, "timeout_sec"):
            kwargs["timeout_sec"] = timeout_sec
        if self._llm_supports_resource_parameter(generate_content, "course_id"):
            kwargs["course_id"] = course_id
        if self._llm_supports_resource_parameter(generate_content, "node_title"):
            kwargs["node_title"] = node_title
        return generate_content(node_id, card_type, difficulty, **kwargs)

    def generate_resource_content_result(
        self,
        node_id: str,
        card_type: str,
        difficulty: float,
        *,
        course_id: str = "data_structures",
        node_title: str = "",
        _deadline_monotonic: Optional[float] = None,
    ) -> ResourceGenerationResult:
        """Generate one card within a bounded deadline and retain provenance.

        The string-only ``generate_resource_content`` method remains below for
        graph compatibility. Resource service callers should use this method
        so a local template can never be confused with an LLM response.
        """
        started = time.monotonic()
        deadline = started + self._resource_llm_total_timeout_sec
        if _deadline_monotonic is not None:
            deadline = min(deadline, _deadline_monotonic)
        candidates = self._candidate_llms()
        last_failure = "no_eligible_provider"
        attempt_count = 0

        for provider_name, llm in candidates:
            for attempt in range(1, self._resource_llm_retries + 1):
                remaining_sec = deadline - time.monotonic()
                if remaining_sec <= 0:
                    last_failure = "deadline_exceeded"
                    break

                attempt_timeout_sec = min(self._resource_llm_timeout_sec, remaining_sec)
                # Let the provider client cancel its HTTP coroutine slightly
                # before this outer guard expires. This avoids permanently
                # occupying a worker after a timed-out request.
                provider_timeout_sec = max(0.1, attempt_timeout_sec - 0.2)
                future = self._resource_generation_pool.submit(
                    self._call_resource_generator,
                    llm,
                    node_id,
                    card_type,
                    difficulty,
                    provider_timeout_sec,
                    course_id,
                    node_title,
                )
                attempt_count += 1
                try:
                    content = future.result(timeout=attempt_timeout_sec)
                    if str(content or "").strip():
                        self._provider_success(provider_name)
                        if provider_name != candidates[0][0]:
                            incr_metric(
                                "llm.fallback_total",
                                operation="resource_generation",
                                fallback=provider_name,
                            )
                        return ResourceGenerationResult(
                            content=str(content),
                            source="llm",
                            provider=provider_name,
                            model=self._llm_model_name(llm),
                            attempt_count=attempt_count,
                            elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                        )
                    last_failure = "empty_response"
                    raise RuntimeError(last_failure)
                except concurrent.futures.TimeoutError:
                    self._provider_failure(provider_name)
                    future.cancel()
                    last_failure = "timeout"
                    incr_metric("llm.timeout_total", operation="resource_generation", provider=provider_name)
                    log_event(
                        "llm.resource.timeout",
                        level="warning",
                        provider=provider_name,
                        card_type=card_type,
                        attempt=attempt,
                        timeout_sec=round(attempt_timeout_sec, 3),
                    )
                except Exception as exc:
                    self._provider_failure(provider_name)
                    last_failure = "provider_error" if last_failure != "empty_response" else last_failure
                    incr_metric("llm.error_total", operation="resource_generation", provider=provider_name)
                    log_event(
                        "llm.resource.error",
                        level="warning",
                        provider=provider_name,
                        card_type=card_type,
                        attempt=attempt,
                        error_type=type(exc).__name__,
                    )
                if time.monotonic() >= deadline:
                    last_failure = "deadline_exceeded"
                    break
                if attempt < self._resource_llm_retries:
                    backoff_sec = min(
                        self._resource_llm_retry_backoff_sec * attempt,
                        max(0.0, deadline - time.monotonic()),
                    )
                    if backoff_sec:
                        time.sleep(backoff_sec)
            if time.monotonic() >= deadline:
                break

        incr_metric("llm.fallback_total", operation="resource_generation", fallback="template")
        return ResourceGenerationResult(
            content=self._template_resource_content(
                node_id,
                card_type,
                course_id=course_id,
                node_title=node_title,
            ),
            source="template",
            attempt_count=attempt_count,
            fallback_reason=last_failure,
            elapsed_ms=round((time.monotonic() - started) * 1000, 3),
        )

    def generate_resource_contents(
        self,
        node_id: str,
        card_types: List[str],
        difficulty: float,
        *,
        course_id: str = "data_structures",
        node_title: str = "",
        resource_context: Any = None,
    ) -> Dict[str, ResourceGenerationResult]:
        """Generate distinct requested card types concurrently and boundedly."""
        requested_types = list(dict.fromkeys(card_types))
        if not requested_types:
            return {}
        if resource_context is not None:
            return self.generate_resource_contents_for_context(resource_context, requested_types)
        if len(requested_types) == 1:
            card_type = requested_types[0]
            return {
                card_type: self.generate_resource_content_result(
                    node_id,
                    card_type,
                    difficulty,
                    course_id=course_id,
                    node_title=node_title,
                ),
            }

        # Every worker shares one absolute deadline. Without this, a batch
        # larger than ``max_workers`` can consume a full timeout per wave.
        batch_deadline = time.monotonic() + self._resource_llm_total_timeout_sec
        max_workers = min(len(requested_types), self._resource_generation_parallelism)
        results: Dict[str, ResourceGenerationResult] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="eduagent-resource-batch",
        ) as pool:
            futures = {
                card_type: pool.submit(
                    self.generate_resource_content_result,
                    node_id,
                    card_type,
                    difficulty,
                    course_id=course_id,
                    node_title=node_title,
                    _deadline_monotonic=batch_deadline,
                )
                for card_type in requested_types
            }
            for card_type in requested_types:
                try:
                    results[card_type] = futures[card_type].result()
                except Exception as exc:
                    # This is defensive: normal failures are represented by a
                    # template result above, but an unexpected runtime failure
                    # must still publish truthful provenance.
                    incr_metric("llm.error_total", operation="resource_generation", provider="runtime")
                    log_event(
                        "llm.resource.batch_error",
                        level="warning",
                        card_type=card_type,
                        error_type=type(exc).__name__,
                    )
                    results[card_type] = ResourceGenerationResult(
                        content=self._template_resource_content(
                            node_id,
                            card_type,
                            course_id=course_id,
                            node_title=node_title,
                        ),
                        source="template",
                        fallback_reason="runtime_error",
                    )
        return results

    @staticmethod
    def _structured_result_from_generated(generated: Any) -> ResourceGenerationResult:
        metadata = generated.generation_metadata()
        return ResourceGenerationResult(
            content=generated.body_markdown,
            source=str(metadata.get("source") or "unknown"),
            provider=metadata.get("provider"),
            model=metadata.get("model"),
            attempt_count=int(metadata.get("attempt_count") or 0),
            fallback_reason=metadata.get("fallback_reason"),
            elapsed_ms=float(metadata.get("elapsed_ms") or 0.0),
            structured_payload=dict(generated.structured_payload),
            input_tokens=max(0, int(getattr(generated, "input_tokens", 0) or 0)),
            output_tokens=max(0, int(getattr(generated, "output_tokens", 0) or 0)),
        )

    def _structured_single_attempt(
        self,
        llm: Any,
        context: Any,
        card_type: str,
        timeout_sec: float,
    ) -> ResourceGenerationResult:
        from src.resource_generation.generator import ResourceGenerator

        generated = ResourceGenerator().generate(
            llm,
            context,
            card_type,
            timeout_sec=max(0.1, timeout_sec - 0.2),
        )
        return self._structured_result_from_generated(generated)

    def generate_structured_resource_result(
        self,
        context: Any,
        card_type: str,
        *,
        _deadline_monotonic: Optional[float] = None,
    ) -> ResourceGenerationResult:
        """Generate one Pydantic resource card with a short bounded timeout."""
        started = time.monotonic()
        deadline = started + self._resource_llm_total_timeout_sec
        if _deadline_monotonic is not None:
            deadline = min(deadline, _deadline_monotonic)
        last_failure = "no_eligible_provider"
        attempts = 0
        for provider_name, llm in self._candidate_llms():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_failure = "deadline_exceeded"
                break
            timeout_sec = min(self._resource_llm_timeout_sec, remaining)
            future = self._resource_generation_pool.submit(
                self._structured_single_attempt,
                llm,
                context,
                card_type,
                timeout_sec,
            )
            attempts += 1
            try:
                result = future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                self._provider_failure(provider_name)
                future.cancel()
                last_failure = "timeout"
                incr_metric("llm.timeout_total", operation="resource_generation", provider=provider_name)
                continue
            except Exception as exc:
                self._provider_failure(provider_name)
                last_failure = f"provider_error:{type(exc).__name__}"
                incr_metric("llm.error_total", operation="resource_generation", provider=provider_name)
                continue
            if result.source == "llm":
                self._provider_success(provider_name)
                return result
            last_failure = result.fallback_reason or "invalid_output"
        from src.resource_generation.generator import ResourceGenerator

        fallback = ResourceGenerator().template(context, card_type, last_failure)
        result = self._structured_result_from_generated(fallback)
        return ResourceGenerationResult(
            **{**result.__dict__, "attempt_count": attempts, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
        )

    def generate_supporting_bundle_results(
        self,
        context: Any,
        card_types: List[str],
        *,
        _deadline_monotonic: Optional[float] = None,
    ) -> Dict[str, ResourceGenerationResult]:
        """Generate non-concept cards in one structured supporting-bundle call."""
        requested = [card_type for card_type in dict.fromkeys(card_types) if card_type != "concept_map"]
        if not requested:
            return {}
        from src.resource_generation.generator import ResourceGenerator

        started = time.monotonic()
        deadline = started + self._resource_llm_total_timeout_sec
        if _deadline_monotonic is not None:
            deadline = min(deadline, _deadline_monotonic)
        last_failure = "no_eligible_provider"
        for provider_name, llm in self._candidate_llms():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_failure = "deadline_exceeded"
                break
            timeout_sec = min(self._resource_llm_total_timeout_sec, remaining)
            future = self._resource_generation_pool.submit(
                ResourceGenerator().generate_bundle,
                llm,
                context,
                requested,
                timeout_sec=max(0.1, timeout_sec - 0.2),
            )
            try:
                generated = future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                self._provider_failure(provider_name)
                future.cancel()
                last_failure = "timeout"
                incr_metric("llm.timeout_total", operation="resource_supporting_bundle", provider=provider_name)
                continue
            except Exception as exc:
                self._provider_failure(provider_name)
                last_failure = f"provider_error:{type(exc).__name__}"
                incr_metric("llm.error_total", operation="resource_supporting_bundle", provider=provider_name)
                continue
            results = {
                card_type: self._structured_result_from_generated(value)
                for card_type, value in generated.items()
            }
            if any(result.source == "llm" for result in results.values()):
                self._provider_success(provider_name)
                return results
            last_failure = next(
                (result.fallback_reason for result in results.values() if result.fallback_reason),
                "invalid_output",
            )
        generator = ResourceGenerator()
        return {
            card_type: self._structured_result_from_generated(
                generator.template(context, card_type, last_failure)
            )
            for card_type in requested
        }

    def generate_resource_contents_for_context(
        self,
        context: Any,
        card_types: List[str],
    ) -> Dict[str, ResourceGenerationResult]:
        """Two-phase API: concept map first, supporting cards as one bundle."""
        requested = list(dict.fromkeys(card_types))
        results: Dict[str, ResourceGenerationResult] = {}
        if "concept_map" in requested:
            results["concept_map"] = self.generate_structured_resource_result(context, "concept_map")
        supporting = [card_type for card_type in requested if card_type != "concept_map"]
        results.update(self.generate_supporting_bundle_results(context, supporting))
        return results

    def generate_resource_content(self, node_id: str, card_type: str, difficulty: float) -> str:
        """Compatibility wrapper for graph integrations that consume strings."""
        return self.generate_resource_content_result(node_id, card_type, difficulty).content

    def _template_resource_content(
        self,
        node_id: str,
        card_type: str,
        *,
        course_id: str = "data_structures",
        node_title: str = "",
    ) -> str:
        title = str(node_title or "").strip()
        if not title:
            get_node_by_id = getattr(self.kg, "get_node_by_id", None)
            if callable(get_node_by_id):
                try:
                    node = get_node_by_id(node_id, course_id)
                    title = str(getattr(node, "title", "") or "").strip()
                except Exception:
                    title = ""
        title = title or self.kg.get_node_title(node_id) or node_id
        templates = {
            "concept_map": f"## {title}\n\n{node_id} 的核心概念图占位内容。",
            "code_snippet": f"## {title}\n\n```python\n# {node_id} 的练习脚手架\npass\n```",
            "interactive_exercise": f"## {title}\n\n尝试一个应用该概念的小练习。",
            "video_summary": f"## {title}\n\n用于复习该概念的简短讲解提纲。",
            "diagnostic_quiz": f"## {title}\n\n1. 这个概念的关键不变量是什么？",
        }
        return TEMPLATE_NOTICE + templates.get(card_type, templates["concept_map"])


_runtime: Optional[OrchestrationRuntime] = None


def get_runtime() -> OrchestrationRuntime:
    global _runtime
    if _runtime is None:
        _runtime = OrchestrationRuntime()
    return _runtime
