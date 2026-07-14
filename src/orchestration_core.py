# -*- coding: utf-8 -*-
"""
LangGraph 全局网络编排 — 多智能体协同系统主控图
================================================

将全部 Agent Node 通过 StateGraph(AgentState) 进行有向图连接，
配置条件边逻辑实现智能路由。

多智能体协同网络 (含加分项 Tutor + Assessment):
    ┌──────────┐
    │  START   │
    └────┬─────┘
         │
    ┌────▼──────────┐
    │ Cold Start    │ ← handle_cold_start_interaction
    │ (pre-graph)   │
    └────┬──────────┘
         │ (cold_start_complete = True)
    ┌────▼──────────┐
    │  Evaluator    │ ← 行为清洗 + PID 评估
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Profiler     │ ← MAB 采样 + 遗忘衰减
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Planner      │ ← DAG-Dijkstra 路径规划
    └────┬──────────┘
         │
    ┌────▼──────────┐   (has tutor_query?)
    │ ┌──────────┐  │──────────────────────┐
    │ │Condition │  │                      │
    │ │  Edge    │  │───→ Tutor ──────────┘
    │ └──────────┘  │   (no query)
    │                │───→ Content Mesh
    └────────────────┘
         │
    ┌────▼──────────┐
    │ Content Mesh  │ ← WFQ 调度 + 资源生成
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Validator    │ ← 双极防幻觉校验
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Assessment   │ ← EMA 能力雷达 + 迟滞环策略决策
    └────┬──────────┘
         │
    ┌────▼──────────┐   (re_plan_triggered=True)
    │ ┌──────────┐  │──────────────────────┐
    │ │Condition │  │                      │
    │ │  Edge    │  │───→ Planner ─────────┘
    │ └──────────┘  │   (re_plan_triggered=False)
    │                │───→ Evaluator (下一轮)
    └────────────────┘

依赖声明：
  LangGraph (Apache 2.0) — 多智能体协同框架。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import ValidationError

from .api_models.learning_event import LearningEventRequest
from .api_models.tutor_request import TutorRequest
from .agents.assessment_node import AssessmentInput, AssessmentReporterNode
from .agents.content_mesh_node import ContentMeshNode, MeshInput
from .agents.evaluator_node import BehaviorVector, EvaluatorInput, EvaluatorNode
from .agents.planner_node import PlannerInput, PlannerNode
from .agents.profiler_node import ProfilerInput, ProfilerNode
from .agents.tutor_node import TutorAgentNode, TutorInput
from .agents.validator_node import ValidatorInput, ValidatorNode
from .infrastructure.cold_start import handle_cold_start_interaction
from .state.agent_state import AgentState, LatestBehavior


# ============================================================================
# LangGraph 图构建器
# ============================================================================

class EduAgentGraph:
    """EduAgent 多智能体协同网络的 LangGraph StateGraph 封装。

    使用方式:
        >>> orchestrator = EduAgentGraph()
        >>> # 注入真实 LLM
        >>> from src.llm import create_llm_client_from_env
        >>> llm = create_llm_client_from_env()
        >>> orchestrator.inject_llm(llm)
        >>> orchestrator.build()
        >>> result = orchestrator.run(initial_state)
    """

    def __init__(self) -> None:
        self._graph: Any = None
        self._evaluator = EvaluatorNode()
        self._profiler = ProfilerNode()
        self._planner = PlannerNode()
        self._tutor = TutorAgentNode()
        self._mesh = ContentMeshNode()
        self._validator = ValidatorNode()
        self._assessment = AssessmentReporterNode()

    @property
    def graph(self) -> Any:
        return self._graph

    # ------------------------------------------------------------------
    # LLM 注入
    # ------------------------------------------------------------------

    def inject_llm(self, llm_client: Any) -> "EduAgentGraph":
        """注入真实大模型客户端，替换所有 Agent Node 中的 Mock 实现。

        注入的接口方法（LLMClient 需实现）:
          - generate_content(node_id, card_type, difficulty) -> str
          - generate_academic_explanation(query, reference_chunks) -> str
          - generate_mermaid_graph(query, text_explanation) -> str
          - compute_nli_entailment(text, ground_truth) -> float

        Args:
            llm_client: LLMClient 实例。

        Returns:
            self（支持链式调用）。
        """
        # Tutor: 注入 LLM 生成器
        self._tutor = TutorAgentNode(
            milvus_client=None,
            llm_generator=llm_client,
        )

        # ContentMesh: 注入内容生成函数
        self._mesh = ContentMeshNode(
            generate_fn=llm_client.generate_content,
        )

        # Validator: 注入 NLI 评分函数
        self._validator = ValidatorNode(
            nli_fn=llm_client.compute_nli_entailment,
        )

        return self

    # ------------------------------------------------------------------
    # 图构建
    # ------------------------------------------------------------------

    def build(self) -> None:
        """构建 LangGraph StateGraph 并配置全部节点与条件边。

        含加分项节点:
          - Tutor:  智能辅导答疑（条件触发）
          - Assessment: 学习效果评估与策略自适应
        """
        try:
            from langgraph.graph import StateGraph, END
        except ImportError:
            raise ImportError(
                "langgraph 未安装。请执行: pip install langgraph"
            )

        # 创建 StateGraph
        self._graph = StateGraph(AgentState)

        # ---- 注册节点 (含加分项) ----
        self._graph.add_node("evaluator", self._evaluator_node_wrapper)
        self._graph.add_node("profiler", self._profiler_node_wrapper)
        self._graph.add_node("planner", self._planner_node_wrapper)
        self._graph.add_node("tutor", self._tutor_node_wrapper)
        self._graph.add_node("content_mesh", self._content_mesh_node_wrapper)
        self._graph.add_node("validator", self._validator_node_wrapper)
        self._graph.add_node("assessment", self._assessment_node_wrapper)

        # ---- 设置入口 ----
        self._graph.set_entry_point("evaluator")

        # ---- 普通边 ----
        self._graph.add_edge("evaluator", "profiler")
        self._graph.add_edge("profiler", "planner")

        # ---- 条件边: 智能辅导答疑（按需触发） ----
        self._graph.add_conditional_edges(
            "planner",
            self._tutor_routing,
            {
                "tutor": "tutor",            # 有答疑请求 → 先走 Tutor
                "content_mesh": "content_mesh",  # 无答疑请求 → 直接生成资源
            },
        )
        # Tutor 执行完毕后汇入 Content Mesh
        self._graph.add_edge("tutor", "content_mesh")

        # ---- 普通边 ----
        self._graph.add_edge("content_mesh", "validator")

        # ---- Assessment 在 Validator 之后，最终路由之前 ----
        self._graph.add_edge("validator", "assessment")

        # ---- 条件边: 基于 re_plan_triggered 的路由（从 Assessment 出发） ----
        self._graph.add_conditional_edges(
            "assessment",
            self._route_decision,
            {
                "replan": "planner",      # 触发重寻路 → 回到 Planner
                "continue": "evaluator",   # 无触发 → 进入下一轮评估
                "end": END,                # 终止条件
            },
        )

    # ------------------------------------------------------------------
    # 条件路由函数
    # ------------------------------------------------------------------

    def _route_decision(
        self, state: AgentState
    ) -> Literal["replan", "continue", "end"]:
        """基于 AgentState 的条件边路由决策。

        Returns:
            - "replan": re_plan_triggered=True → 回到 Planner 重寻路
            - "continue": 正常 → 进入下一轮 Evaluator
            - "end": 所有目标节点掌握度达标 → 终止
        """
        # 检查是否应终止
        if self._should_terminate(state):
            return "end"

        # 检查重寻路触发
        if state.re_plan_triggered:
            return "replan"

        return "continue"

    def _should_terminate(self, state: AgentState) -> bool:
        """判断学习流程是否应终止。

        终止条件 (满足任一):
          1. active_path 为空且无重寻路需求
          2. target_node_id 已掌握 (mastery ≥ 0.85)
          3. 迭代次数超过上限 (100 轮)
        """
        if state.iteration >= 100:
            return True

        target = state.target_node_id
        if target:
            mastery = state.dynamic_profile.knowledge_mastery.get(
                target, 0.0
            )
            if mastery >= 0.85 and not state.re_plan_triggered:
                return True

        if not state.active_path and not state.re_plan_triggered:
            return True

        return False

    # ------------------------------------------------------------------
    # Node Wrapper 函数 (LangGraph Node 签名适配)
    # ------------------------------------------------------------------

    def _evaluator_node_wrapper(self, state: AgentState) -> AgentState:
        """Evaluator Node 的 LangGraph 适配器。

        从 AgentState 中提取 latest_behavior 作为 BehaviorVector，
        若无则构建默认行为向量。
        """
        lb = state.latest_behavior
        if lb:
            raw_behavior = BehaviorVector(
                answer_correctness=lb.correctness,
                code_pass_rate=0.0,
                time_spent_ratio=lb.time_spent_ratio,
                help_request_count=lb.help_request_count,
                node_id=lb.node_id or state.current_node_id or "",
            )
        else:
            raw_behavior = BehaviorVector(
                answer_correctness=0.5,
                time_spent_ratio=1.0,
                node_id=state.current_node_id or "",
            )

        inp = EvaluatorInput(
            agent_state=state,
            raw_behavior=raw_behavior,
        )
        output = self._evaluator(inp)
        return output.agent_state

    def _profiler_node_wrapper(self, state: AgentState) -> AgentState:
        """Profiler Node 的 LangGraph 适配器。"""
        # 从 Evaluator 的输出中提取信号
        # (在真实的 LangGraph 流转中，这些信息已写入 AgentState)
        current_style = state.recommended_resource_style or "visual"

        inp = ProfilerInput(
            agent_state=state,
            evaluator_mastery_delta=0.0,
            evaluator_pid_error=1.0 - state.dynamic_profile.knowledge_mastery.get(
                state.current_node_id or "", 0.5
            ),
            resource_style_delivered=current_style,
            node_id=state.current_node_id or "",
        )
        output = self._profiler(inp)
        return output.agent_state

    def _planner_node_wrapper(self, state: AgentState) -> AgentState:
        """Planner Node 的 LangGraph 适配器。"""
        inp = PlannerInput(agent_state=state)
        output = self._planner(inp)
        planner_adj = state.internal_state.get("planner_adjacency", {})
        if planner_adj:
            self._mesh.set_adjacency(planner_adj)
        return output.agent_state

    def _content_mesh_node_wrapper(self, state: AgentState) -> AgentState:
        """Content Mesh Node 的 LangGraph 适配器。"""
        inp = MeshInput(agent_state=state)
        output = self._mesh(inp)
        return output.agent_state

    def _validator_node_wrapper(self, state: AgentState) -> AgentState:
        """Validator Node 的 LangGraph 适配器。"""
        # 收集本轮的生成卡片
        cards_to_validate: list = []
        for cards in state.generated_resources.values():
            for card in cards:
                cards_to_validate.append(card)

        inp = ValidatorInput(
            agent_state=state,
            cards_to_validate=cards_to_validate,
            ground_truth_context="",  # 实际从 Milvus Parent Lookup 获取
        )
        output = self._validator(inp)
        return output.agent_state

    def _tutor_node_wrapper(self, state: AgentState) -> AgentState:
        """Tutor Agent Node 的 LangGraph 适配器（加分项）。

        仅在 AgentState 的 latest_behavior.tutor_query 非空时被触发。
        """
        inp = TutorInput(agent_state=state)
        output = self._tutor(inp)
        return output.agent_state

    def _assessment_node_wrapper(self, state: AgentState) -> AgentState:
        """Assessment Reporter Node 的 LangGraph 适配器（加分项）。

        在 Validator 之后执行，产出能力雷达评估报告并更新教学策略。
        """
        inp = AssessmentInput(agent_state=state)
        output = self._assessment(inp)
        return output.agent_state

    # ------------------------------------------------------------------
    # 条件路由
    # ------------------------------------------------------------------

    def _tutor_routing(
        self, state: AgentState
    ) -> Literal["tutor", "content_mesh"]:
        """判断是否需要触发智能辅导答疑。

        Returns:
            - "tutor": latest_behavior.tutor_query 非空 → 先答疑
            - "content_mesh": 无需答疑 → 直接进入资源生成
        """
        lb = state.latest_behavior
        if lb and getattr(lb, "tutor_query", None):
            return "tutor"
        return "content_mesh"

    # ------------------------------------------------------------------
    # 运行入口
    # ------------------------------------------------------------------

    def run(
        self,
        initial_state: AgentState,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        """运行完整的 LangGraph 协同网络。

        Args:
            initial_state: 初始 AgentState。
            config: LangGraph 运行时配置。

        Returns:
            运行终止后的 AgentState。
        """
        if self._graph is None:
            self.build()

        # 编译图（支持 checkpointing）
        app = self._graph.compile()

        # 运行
        final_state = app.invoke(initial_state, config=config or {})
        return final_state

    def stream(
        self,
        initial_state: AgentState,
        config: Optional[Dict[str, Any]] = None,
    ):
        """流式运行 LangGraph 协同网络。

        Yields:
            每个 Node 执行后的 AgentState。
        """
        if self._graph is None:
            self.build()

        app = self._graph.compile()
        for event in app.stream(initial_state, config=config or {}):
            yield event


# ============================================================================
# 预构建的冷启动 + 主图编排器
# ============================================================================

class ColdStartOrchestrator:
    """冷启动阶段编排器 — 在进入主 LangGraph 图之前的预处理流程。

    流程:
      1. 调用 handle_cold_start_interaction 逐轮收集画像
      2. 冷启动完成后触发 Planner 初始路径规划
      3. 将就绪的 AgentState 注入主图
    """

    def __init__(self, planner_node: Optional[PlannerNode] = None) -> None:
        self._planner = planner_node or PlannerNode()
        self._cold_start_complete = False

    def is_complete(self) -> bool:
        return self._cold_start_complete

    def process_interaction(
        self, agent_state: AgentState, user_response: Optional[Any] = None
    ) -> Tuple[AgentState, Optional[Any], bool]:
        """处理一轮冷启动交互。

        Args:
            agent_state: 当前 AgentState。
            user_response: 用户回答。

        Returns:
            (agent_state, next_probe, is_complete)。
        """
        state, probe, is_complete = handle_cold_start_interaction(
            agent_state, user_response
        )
        self._cold_start_complete = is_complete
        return state, probe, is_complete

    def finalize(self, agent_state: AgentState) -> AgentState:
        """冷启动完成后的收尾工作: 触发初始路径规划。"""
        if not agent_state.active_path:
            inp = PlannerInput(agent_state=agent_state)
            output = self._planner(inp)
            agent_state = output.agent_state
        return agent_state

# ============================================================================
# Unified learning-step facade
# ============================================================================

# Threshold copied from _common to avoid importing the application layer here.
_MASTERY_ADVANCE_THRESHOLD = 0.65


def _quiz_questions_from_card(card: Any) -> list[dict[str, Any]]:
    metadata = getattr(card, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return []
    structured_payload = metadata.get("structured_payload")
    candidates = [structured_payload, metadata]
    for candidate in candidates:
        questions = candidate.get("questions") if isinstance(candidate, dict) else None
        if isinstance(questions, list):
            return [question for question in questions if isinstance(question, dict)]
    return []


def _verify_quiz_completion(
    state: AgentState,
    node_id: str,
    event: LearningEventRequest,
) -> tuple[bool, float, str, Dict[str, Any]]:
    """Derive a score from a server-owned diagnostic card, never client scores."""
    evidence = event.completion_evidence
    if evidence is None:
        return False, 0.0, "missing_completion_evidence", {}
    if evidence.evidence_type != "diagnostic_quiz":
        return False, 0.0, "unsupported_completion_evidence", {"evidence_type": evidence.evidence_type}
    if not evidence.resource_id:
        return False, 0.0, "missing_quiz_resource_id", {}

    consumed_resource_ids = state.internal_state.get("consumed_completion_resource_ids", [])
    if isinstance(consumed_resource_ids, list) and evidence.resource_id in consumed_resource_ids:
        return False, 0.0, "completion_evidence_replayed", {"resource_id": evidence.resource_id}

    card = next(
        (
            candidate
            for candidate in state.generated_resources.get(node_id, [])
            if getattr(candidate, "resource_id", "") == evidence.resource_id
            and getattr(candidate, "card_type", "") == "diagnostic_quiz"
        ),
        None,
    )
    if card is None:
        return False, 0.0, "diagnostic_quiz_not_found", {"resource_id": evidence.resource_id}

    questions = _quiz_questions_from_card(card)
    if not questions:
        return False, 0.0, "diagnostic_quiz_has_no_server_answer_key", {"resource_id": evidence.resource_id}

    answer_key: Dict[str, int] = {}
    question_by_id: Dict[str, Dict[str, Any]] = {}
    for question in questions:
        question_id = str(question.get("id") or "").strip()
        answer_index = question.get("answer_index")
        if not question_id or isinstance(answer_index, bool) or not isinstance(answer_index, int) or answer_index < 0:
            return False, 0.0, "diagnostic_quiz_has_invalid_answer_key", {"resource_id": evidence.resource_id}
        if question_id in answer_key:
            # Do not collapse malformed questions into one answerable item. That
            # would let an incomplete submission look like a verified quiz.
            return False, 0.0, "diagnostic_quiz_has_duplicate_question_id", {
                "resource_id": evidence.resource_id,
                "question_id": question_id,
            }
        answer_key[question_id] = answer_index
        question_by_id[question_id] = question

    submitted_answers: Dict[str, int] = {}
    for answer in evidence.answers:
        if not answer.question_id or answer.question_id not in answer_key:
            return False, 0.0, "quiz_answer_does_not_match_server_question", {"question_id": answer.question_id}
        if answer.question_id in submitted_answers:
            return False, 0.0, "duplicate_quiz_answer", {"question_id": answer.question_id}
        if answer.answer_index < 0:
            return False, 0.0, "invalid_quiz_answer_index", {"question_id": answer.question_id}
        submitted_answers[answer.question_id] = answer.answer_index

    if set(submitted_answers) != set(answer_key):
        return False, 0.0, "incomplete_quiz_answers", {
            "expected_question_count": len(answer_key),
            "received_question_count": len(submitted_answers),
        }

    def option_text(question: Dict[str, Any], index: int) -> str:
        options = question.get("options")
        if isinstance(options, list) and 0 <= index < len(options):
            value = options[index]
            return str(value).strip() if value is not None else ""
        return f"Option {index + 1}" if index >= 0 else ""

    question_results: list[Dict[str, Any]] = []
    for question_id, expected_index in answer_key.items():
        selected_index = submitted_answers[question_id]
        question = question_by_id[question_id]
        question_results.append({
            "question_id": question_id,
            "prompt": str(question.get("prompt") or "").strip(),
            "skill_tag": str(question.get("skill_tag") or "").strip(),
            "selected_index": selected_index,
            "selected_answer": option_text(question, selected_index),
            "correct_index": expected_index,
            "correct_answer": option_text(question, expected_index),
            "correct": selected_index == expected_index,
            "explanation": str(question.get("explanation") or "").strip(),
        })

    correct_count = sum(1 for result in question_results if result["correct"])
    correctness = correct_count / len(answer_key)
    return True, correctness, "verified_diagnostic_quiz", {
        "resource_id": evidence.resource_id,
        "question_count": len(answer_key),
        "correct_count": correct_count,
        # These answer outcomes are created from the server-owned answer key
        # after submission. They provide the immutable input for the review
        # workflow and are never accepted from browser payloads.
        "question_results": question_results,
    }


def _record_verified_completion(state: AgentState, details: Dict[str, Any]) -> None:
    records = state.internal_state.setdefault("verified_completion_events", [])
    if not isinstance(records, list):
        records = []
        state.internal_state["verified_completion_events"] = records
    records.append(dict(details))
    if len(records) > 20:
        del records[:-20]

    resource_id = str(details.get("resource_id") or "").strip()
    if resource_id:
        consumed_resource_ids = state.internal_state.setdefault("consumed_completion_resource_ids", [])
        if not isinstance(consumed_resource_ids, list):
            consumed_resource_ids = []
            state.internal_state["consumed_completion_resource_ids"] = consumed_resource_ids
        if resource_id not in consumed_resource_ids:
            consumed_resource_ids.append(resource_id)
        if len(consumed_resource_ids) > 500:
            del consumed_resource_ids[:-500]


@dataclass
class LearningStepResult:
    """Structured result returned by run_official_learning_step.

    Callers (session_service, HTTP routes) use this instead of unpacking
    scattered locals from their own pipeline wiring.
    """
    state: AgentState
    logs: List[Dict[str, Any]] = field(default_factory=list)
    # Advancement
    current_node: str = ""
    evaluated_node: str = ""
    evaluated_mastery: float = 0.0
    previous_mastery: float = 0.0
    advanced_to_next_node: bool = False
    next_node_id: Optional[str] = None
    # Pass-through
    interaction_type: str = "browse_node"
    event_type: str = "browse_node"
    correctness: float = 0.0
    evidence_accepted: bool = False
    mastery_updated: bool = False
    mastery_update_reason: str = "browse_node"


def run_official_learning_step(
    session: Any,
    behavior: Optional[Dict[str, Any]] = None,
    user_input: Optional[str] = None,
    runtime: Any = None,
) -> LearningStepResult:
    """High-level façade that owns the full agent pipeline for one learning step.

    This is the **single entry point** for running evaluator → profiler →
    planner → (tutor?) → content-mesh → resource-generation → validator →
    assessment.  Application-layer services (session_service, HTTP handlers)
    should call this function and not re-wire individual nodes themselves.

    Args:
        session:     A ``RuntimeSession`` object that carries ``agent_state``,
                     ``path_planner``, ``pipeline_log``, etc.
        behavior:    Dict of interaction parameters (interaction_type,
                     correctness, current_node_id, …).  Defaults to an empty
                     dict (``practice`` interaction with neutral scores).
        user_input:  Optional free-text that maps to a tutor query when the
                     interaction type is not ``load_node``.
        runtime:     Optional pre-resolved ``OrchestrationRuntime`` instance.
                     Pass an explicit value (e.g. from a monkeypatched
                     ``get_runtime()``) to allow tests to inject fakes without
                     touching the module-level import inside this function.

    Returns:
        :class:`LearningStepResult` with the updated state and all metadata
        needed to build the HTTP response.
    """
    # Lazy import to avoid a circular dependency: orchestration ← application.
    from src.orchestration_runtime import get_runtime as _get_runtime
    from src.agents.assessment_node import AssessmentInput
    from src.agents.evaluator_node import BehaviorVector, EvaluatorInput
    from src.agents.profiler_node import ProfilerInput
    from src.agents.tutor_node import TutorInput
    from src.application._common import RESOURCE_CARD_ORDER, normalize_state_resources
    from src.application.resource_service import generate_current_node_resources

    _runtime = runtime if runtime is not None else _get_runtime()
    state: AgentState = session.agent_state
    payload = behavior or {}
    raw_interaction_type = str(
        payload.get(
            "interaction_type",
            payload.get(
                "interactionType",
                payload.get("event_type", payload.get("eventType", "browse_node")),
            ),
        )
        or "browse_node"
    )
    event_parse_reason = ""
    try:
        event = LearningEventRequest.model_validate(payload)
    except ValidationError:
        # Preserve the requested event label for compatibility while denying evaluation.
        event = LearningEventRequest.model_validate({"interaction_type": raw_interaction_type})
        event_parse_reason = "invalid_completion_evidence"
    interaction_type = raw_interaction_type
    # Orchestration still has two execution paths.  The public event model is
    # richer, so map it explicitly instead of treating a client score as a
    # generic practice interaction.
    event_type = event.operation_type

    # ── Resolve current node ──────────────────────────────────────────────
    target_node = event.node_id or payload.get("current_node_id") or payload.get("currentNodeId")
    if target_node:
        state.current_node_id = target_node
    current_node = state.current_node_id or (
        state.active_path[0] if state.active_path else "N01"
    )
    previous_mastery = state.dynamic_profile.knowledge_mastery.get(current_node, 0.0)

    tutor_query = payload.get("tutor_query") or payload.get("question") or payload.get("query") or user_input
    tutor_request: Optional[TutorRequest] = None
    if tutor_query:
        try:
            tutor_request = TutorRequest.model_validate({**payload, "question": tutor_query})
        except ValidationError:
            tutor_request = None

    evidence_verified = False
    correctness = 0.0
    evidence_details: Dict[str, Any] = {}
    mastery_update_reason = "browse_node"
    if event_type == "complete_learning":
        evidence_verified, correctness, mastery_update_reason, evidence_details = _verify_quiz_completion(
            state,
            current_node,
            event,
        )
        if event_parse_reason:
            evidence_verified = False
            correctness = 0.0
            mastery_update_reason = event_parse_reason
            evidence_details = {}
    elif event_type == "unsupported":
        mastery_update_reason = "unsupported_learning_event"

    logs: List[Dict[str, Any]] = []

    # ── Step 1 + 2: Evaluator → Profiler (verified completion only) ─────
    if not evidence_verified:
        logs.append({
            "agent": "Evaluator",
            "status": "skipped",
            "reason": mastery_update_reason,
            "mastery_updated": False,
        })
        logs.append({
            "agent": "Profiler",
            "status": "skipped",
            "reason": mastery_update_reason,
            "mastery_updated": False,
        })
    else:
        state.latest_behavior = LatestBehavior(
            node_id=current_node,
            correctness=correctness,
            error_types=[],
            resource_feedback={},
            tutor_query=tutor_query,
            accuracy_rate=correctness,
        )
        eval_output = _runtime.evaluator(
            EvaluatorInput(
                agent_state=state,
                raw_behavior=BehaviorVector(
                    answer_correctness=correctness,
                    verified_quiz_score_only=True,
                    node_id=current_node,
                ),
            )
        )
        state = eval_output.agent_state
        logs.append({
            "agent": "Evaluator",
            "effective_correctness": eval_output.cleaned_behavior.effective_correctness,
            "anomaly_type": eval_output.cleaned_behavior.anomaly.anomaly_type.value,
            "anomaly_detected": eval_output.anomaly_detected,
            "mastery_delta": round(eval_output.mastery_delta, 4),
            "pid_error": round(eval_output.pid_error, 4),
            "replan_decision": eval_output.replan_decision.value,
            "updated_mastery": round(eval_output.updated_mastery, 4),
        })

        prof_output = _runtime.profiler(
            ProfilerInput(
                agent_state=state,
                evaluator_mastery_delta=eval_output.mastery_delta,
                evaluator_pid_error=eval_output.pid_error,
                resource_style_delivered=state.recommended_resource_style or "visual",
                node_id=current_node,
            )
        )
        state = prof_output.agent_state
        _record_verified_completion(
            state,
            {
                "event_type": event_type,
                "node_id": current_node,
                "correctness": correctness,
                **evidence_details,
            },
        )
        logs.append({
            "agent": "Profiler",
            "selected_style": prof_output.style_result.selected_style,
            "sample_values": prof_output.style_result.sample_values,
            "intervention_triggered": prof_output.intervention_active,
            "forgetting_decay": (
                round(prof_output.forgetting_result.decay_factor, 4)
                if prof_output.forgetting_result
                else None
            ),
        })

    # ── Step 3: Planner (replan if triggered or path empty) ──────────────
    if not state.active_path or state.re_plan_triggered:
        state.active_path = session.path_planner.compute_topological_order()
        state.re_plan_triggered = False
        logs.append({"agent": "Planner", "replan": True, "new_path": state.active_path})
    else:
        logs.append({"agent": "Planner", "replan": False, "active_path": state.active_path})

    if not state.active_path and current_node:
        state.active_path = [current_node]
    if current_node and current_node in state.active_path:
        state.active_path = [
            current_node,
            *[node_id for node_id in state.active_path if node_id != current_node],
        ]

    # ── Step 4: Tutor (independent from mastery evaluation) ──────────────
    if tutor_request is not None and event_type != "browse_node":
        tutor_output = _runtime.tutor(TutorInput(agent_state=state, request=tutor_request))
        state = tutor_output.agent_state
        logs.append({
            "agent": "Tutor",
            "query": tutor_request.question,
            "context_type": tutor_request.context_type,
            "has_mermaid": bool(
                state.tutor_response.get("mermaid_src", "")
                if state.tutor_response
                else False
            ),
        })
    elif tutor_query and event_type != "browse_node":
        logs.append({
            "agent": "Tutor",
            "status": "skipped",
            "reason": "invalid_tutor_request",
        })

    # ── Step 5: Content Mesh ─────────────────────────────────────────────
    existing_types = {
        getattr(card, "card_type", "")
        for card in state.generated_resources.get(current_node, [])
    }
    resources_complete = existing_types.issuperset(set(RESOURCE_CARD_ORDER))
    if event_type == "browse_node":
        logs.append({
            "agent": "ContentMesh",
            "status": "delegated_to_resource_service",
            "reason": "event_type=browse_node",
        })
        logs.append({
            "agent": "Validator",
            "status": "handled_by_resource_service",
            "reason": "resources are fetched through the session resources boundary",
        })
    elif not evidence_verified:
        logs.append({
            "agent": "ContentMesh",
            "status": "skipped",
            "reason": mastery_update_reason,
        })
        logs.append({
            "agent": "Validator",
            "status": "skipped",
            "reason": mastery_update_reason,
        })
    elif resources_complete:
        logs.append({
            "agent": "ContentMesh",
            "status": "already_exists",
            "card_types": [
                card_type
                for card_type in RESOURCE_CARD_ORDER
                if card_type in existing_types
            ],
        })
        logs.append({
            "agent": "Validator",
            "status": "already_validated",
            "reason": "resource_service validates cards before publishing",
        })
    else:
        session.agent_state = state
        resource_result = generate_current_node_resources(
            session.agent_state.user_id
            if hasattr(session.agent_state, "user_id")
            else "",
            session.agent_state.course_id
            if hasattr(session.agent_state, "course_id")
            else "data_structures",
            current_node,
            force=False,
        )
        state = session.agent_state
        generated_cards = state.generated_resources.get(current_node, [])
        logs.append({
            "agent": "ContentMesh",
            "status": resource_result.get("status", "generated"),
            "generated_cards": len(generated_cards),
            "card_types": [getattr(card, "card_type", "") for card in generated_cards],
        })
        logs.append({
            "agent": "Validator",
            "status": "handled_by_resource_service",
            "reason": "resource_service validates cards before publishing",
        })

    # ── Step 8: Assessment (verified completion only) ────────────────────
    if not evidence_verified:
        logs.append({
            "agent": "Assessment",
            "status": "skipped",
            "reason": mastery_update_reason,
            "mastery_updated": False,
        })
    else:
        assess_output = _runtime.assessment(AssessmentInput(agent_state=state))
        state = assess_output.agent_state
        logs.append({
            "agent": "Assessment",
            "capability_radar": state.dynamic_profile.capability_radar,
            "pedagogical_strategy": state.pedagogical_strategy,
            "a_mix": round(sum(state.dynamic_profile.capability_radar) / 5, 4),
        })

    # ── Node advancement ─────────────────────────────────────────────────
    evaluated_mastery = state.dynamic_profile.knowledge_mastery.get(
        current_node,
        previous_mastery,
    )
    advanced_to_next_node = False
    next_node_id: Optional[str] = None

    def _find_next(
        path: list,
        mastery_map: Dict[str, float],
        cur: str,
    ) -> Optional[str]:
        start = path.index(cur) + 1 if cur in path else 0
        for nid in path[start:]:
            if mastery_map.get(nid, 0.0) < _MASTERY_ADVANCE_THRESHOLD:
                return nid
        return None

    if (
        event_type == "complete_learning"
        and evidence_verified
        and evaluated_mastery >= _MASTERY_ADVANCE_THRESHOLD
    ):
        next_node_id = _find_next(
            state.active_path,
            state.dynamic_profile.knowledge_mastery,
            current_node,
        )
        if next_node_id:
            state.current_node_id = next_node_id
            advanced_to_next_node = True
        else:
            state.current_node_id = current_node
    else:
        state.current_node_id = current_node

    normalize_state_resources(state)
    session.agent_state = state
    session.pipeline_log.extend(logs)

    return LearningStepResult(
        state=state,
        logs=logs,
        current_node=state.current_node_id,
        evaluated_node=current_node,
        evaluated_mastery=evaluated_mastery,
        previous_mastery=previous_mastery,
        advanced_to_next_node=advanced_to_next_node,
        next_node_id=next_node_id,
        interaction_type=interaction_type,
        event_type=event_type,
        correctness=correctness,
        evidence_accepted=evidence_verified,
        mastery_updated=abs(evaluated_mastery - previous_mastery) > 1e-9,
        mastery_update_reason=mastery_update_reason,
    )
