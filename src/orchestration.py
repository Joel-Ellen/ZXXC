# -*- coding: utf-8 -*-
"""
LangGraph 全局网络编排 — 多智能体协同系统主控图
================================================

将全部 Agent Node 通过 StateGraph(AgentState) 进行有向图连接，
配置条件边逻辑实现智能路由。

多智能体协同网络:
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
    ┌────▼──────────┐
    │ Content Mesh  │ ← WFQ 调度 + 资源生成
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Validator    │ ← 双极防幻觉校验
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

from typing import Dict, Any, Optional, Literal

from .state.agent_state import AgentState
from .agents.evaluator_node import (
    EvaluatorNode, EvaluatorInput, BehaviorVector,
)
from .agents.profiler_node import (
    ProfilerNode, ProfilerInput,
)
from .agents.planner_node import (
    PlannerNode, PlannerInput,
)
from .agents.content_mesh_node import (
    ContentMeshNode, MeshInput,
)
from .agents.validator_node import (
    ValidatorNode, ValidatorInput,
)
from .infrastructure.cold_start import (
    handle_cold_start_interaction,
)


# ============================================================================
# LangGraph 图构建器
# ============================================================================

class EduAgentGraph:
    """EduAgent 多智能体协同网络的 LangGraph StateGraph 封装。

    使用方式:
        >>> orchestrator = EduAgentGraph()
        >>> orchestrator.build()
        >>> result = orchestrator.run(initial_state)
    """

    def __init__(self) -> None:
        self._graph: Any = None
        self._evaluator = EvaluatorNode()
        self._profiler = ProfilerNode()
        self._planner = PlannerNode()
        self._mesh = ContentMeshNode()
        self._validator = ValidatorNode()

    @property
    def graph(self) -> Any:
        return self._graph

    # ------------------------------------------------------------------
    # 图构建
    # ------------------------------------------------------------------

    def build(self) -> None:
        """构建 LangGraph StateGraph 并配置全部节点与条件边。"""
        try:
            from langgraph.graph import StateGraph, END
        except ImportError:
            raise ImportError(
                "langgraph 未安装。请执行: pip install langgraph"
            )

        # 创建 StateGraph
        self._graph = StateGraph(AgentState)

        # ---- 注册节点 ----
        self._graph.add_node("evaluator", self._evaluator_node_wrapper)
        self._graph.add_node("profiler", self._profiler_node_wrapper)
        self._graph.add_node("planner", self._planner_node_wrapper)
        self._graph.add_node("content_mesh", self._content_mesh_node_wrapper)
        self._graph.add_node("validator", self._validator_node_wrapper)

        # ---- 设置入口 ----
        self._graph.set_entry_point("evaluator")

        # ---- 普通边 ----
        self._graph.add_edge("evaluator", "profiler")
        self._graph.add_edge("profiler", "planner")
        self._graph.add_edge("planner", "content_mesh")
        self._graph.add_edge("content_mesh", "validator")

        # ---- 条件边: 基于 re_plan_triggered 的路由 ----
        self._graph.add_conditional_edges(
            "validator",
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
        c_fail = state.dynamic_profile.continuous_fail_counter
        current_style = "visual"  # 默认，实际从 AgentState 推断

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
        for node_id, cards in state.generated_resources.items():
            for card in cards:
                cards_to_validate.append(card)

        inp = ValidatorInput(
            agent_state=state,
            cards_to_validate=cards_to_validate,
            ground_truth_context="",  # 实际从 Milvus Parent Lookup 获取
        )
        output = self._validator(inp)
        return output.agent_state

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
        self._cold_start_state: Any = None

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
