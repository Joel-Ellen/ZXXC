# -*- coding: utf-8 -*-
"""
AgentState — LangGraph 全局上下文强类型定义
============================================

本模块定义了系统在 LangGraph StateGraph 中流转的完整全局状态。
所有字段均通过 Pydantic v2 进行严格校验，确保跨 Agent Node 传递的
数据符合预定义契约。

遵循第十五届"中国软件杯"科大讯飞出题规范：
  - 6维动态用户画像
  - PID 误差跟踪
  - 冷启动启发式计数器
  - 拓扑路径激活序列
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# 静态画像子结构
# ---------------------------------------------------------------------------

class CognitiveStyleDistribution(BaseModel):
    """认知风格 Beta 分布参数。

    使用 Beta(α, β) 共轭先验对视觉/文本/实践三种认知维度建模，
    支持在线更新（Bayesian updating）以便根据用户行为流动态调整。
    """

    visual_alpha: float = Field(default=1.0, ge=0.0, description="视觉型 α 超参数")
    visual_beta: float = Field(default=1.0, ge=0.0, description="视觉型 β 超参数")
    textual_alpha: float = Field(default=1.0, ge=0.0, description="文本型 α 超参数")
    textual_beta: float = Field(default=1.0, ge=0.0, description="文本型 β 超参数")
    practical_alpha: float = Field(default=1.0, ge=0.0, description="实践型 α 超参数")
    practical_beta: float = Field(default=1.0, ge=0.0, description="实践型 β 超参数")

    def to_dict(self) -> Dict[str, float]:
        return self.model_dump()

    def compute_means(self) -> Dict[str, float]:
        """计算各维度的后验均值 α/(α+β)，作为认知风格偏好权重。"""
        denom_v = self.visual_alpha + self.visual_beta
        denom_t = self.textual_alpha + self.textual_beta
        denom_p = self.practical_alpha + self.practical_beta
        return {
            "visual_weight": self.visual_alpha / denom_v if denom_v > 0 else 0.5,
            "textual_weight": self.textual_alpha / denom_t if denom_t > 0 else 0.5,
            "practical_weight": self.practical_alpha / denom_p if denom_p > 0 else 0.5,
        }


class StaticProfile(BaseModel):
    """用户静态画像 — 由初次登录问卷初始化，后续缓慢演化。"""

    cognitive_style_distribution: CognitiveStyleDistribution = Field(
        default_factory=CognitiveStyleDistribution,
        description="认知风格 Beta 分布参数"
    )
    motivation: str = Field(
        default="academic_exam",
        pattern=r"^(academic_exam|skill_certification|project_driven|curiosity)$",
        description="学习动机类型"
    )
    time_budget_hours_per_week: float = Field(
        default=10.0, ge=0.5, le=168.0,
        description="每周可用于学习的时间预算（小时）"
    )
    knowledge_base: List[str] = Field(
        default_factory=list,
        description="用户已掌握的知识点 ID 列表（自报 + 预测试推断）"
    )

    @field_validator("motivation")
    @classmethod
    def check_motivation(cls, v: str) -> str:
        allowed = {"academic_exam", "skill_certification", "project_driven", "curiosity"}
        if v not in allowed:
            raise ValueError(f"motivation 必须是 {allowed} 之一，实际为: {v}")
        return v


# ---------------------------------------------------------------------------
# 动态画像子结构
# ---------------------------------------------------------------------------

class KnowledgeMasteryRecord(BaseModel):
    """单个知识点的掌握度记录。"""

    node_id: str = Field(..., description="Neo4j 知识点节点 ID")
    mastery: float = Field(default=0.0, ge=0.0, le=1.0, description="掌握度 (0.0-1.0)")
    last_updated: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="最近一次更新的 ISO 时间戳"
    )
    interaction_count: int = Field(default=0, ge=0, description="与该知识点的交互总次数")


class ErrorTypeDistribution(BaseModel):
    """错误类型分布 — 用于根因分析与资源重生成策略。"""

    logic_flaw: float = Field(default=0.33, ge=0.0, le=1.0, description="逻辑缺陷比例")
    syntax_error: float = Field(default=0.33, ge=0.0, le=1.0, description="语法错误比例")
    boundary_miss: float = Field(default=0.34, ge=0.0, le=1.0, description="边界遗漏比例")

    def normalize(self) -> "ErrorTypeDistribution":
        """将三项比例归一化到总和为 1.0。"""
        total = self.logic_flaw + self.syntax_error + self.boundary_miss
        if total == 0:
            return ErrorTypeDistribution(logic_flaw=0.34, syntax_error=0.33, boundary_miss=0.33)
        return ErrorTypeDistribution(
            logic_flaw=self.logic_flaw / total,
            syntax_error=self.syntax_error / total,
            boundary_miss=self.boundary_miss / total,
        )


class PIDErrorRecord(BaseModel):
    """单个知识点的 PID 误差状态。

    用于 P 控制器的误差积分、抗饱和与历史追踪。
    """

    node_id: str = Field(..., description="知识点 ID")
    error_integral: float = Field(default=0.0, description="累计误差积分 ∫e dt")
    prev_error: float = Field(default=0.0, description="上一次误差 e(t-1)")
    kp_gain: float = Field(default=1.0, gt=0.0, description="当前比例增益 K_p")
    ki_gain: float = Field(default=0.1, gt=0.0, description="当前积分增益 K_i")
    kd_gain: float = Field(default=0.05, gt=0.0, description="当前微分增益 K_d")


class DynamicProfile(BaseModel):
    """用户动态画像 — 随每次交互实时更新。

    包含学习效果评估 (Assessment) 加分项所需的 5 维长效能力向量
    与诊断报告字段。
    """

    knowledge_mastery: Dict[str, float] = Field(
        default_factory=dict,
        description="Key=node_id, Value=mastery (0.0-1.0)"
    )
    knowledge_mastery_records: Dict[str, KnowledgeMasteryRecord] = Field(
        default_factory=dict,
        description="Key=node_id, Value=详细掌握度记录"
    )
    error_type_distribution: ErrorTypeDistribution = Field(
        default_factory=ErrorTypeDistribution,
        description="错误类型分布"
    )
    continuous_fail_counter: int = Field(
        default=0, ge=0,
        description="连续失败计数器 C_fail（触发难度降级干预）"
    )
    pid_errors: Dict[str, PIDErrorRecord] = Field(
        default_factory=dict,
        description="Key=node_id, Value=该知识点的 PID 误差状态"
    )

    # ---- 加分项扩展字段 (Assessment Node) ----
    capability_radar: List[float] = Field(
        default_factory=lambda: [0.5, 0.5, 0.5, 0.5, 0.5],
        description=(
            "5 维长期能力向量 [概念理解力, 代码工程力, 逻辑推理力, "
            "错题抗挫力, 时间管理力]，通过 EMA 平滑更新 (学习评估加分项)"
        )
    )
    diagnostic_report_md: str = Field(
        default="",
        description="最近一次生成的 Markdown 格式《多维度综合评估诊断报告》 (学习评估加分项)"
    )
    boundary_miss_ema_sequence: List[float] = Field(
        default_factory=list,
        description="边界遗漏 EMA 历史序列，用于检测连续走高趋势 (学习评估加分项)"
    )


# ---------------------------------------------------------------------------
# 行为流子结构
# ---------------------------------------------------------------------------

class LatestBehavior(BaseModel):
    """最近一次交互的行为统计数据包。

    Planner/Generator 节点读取此结构以决定路径调整与内容重生成策略。
    支持智能辅导 (Tutor Agent) 与学习评估 (Assessment) 加分项所需的
    扩展字段。
    """

    node_id: Optional[str] = Field(default=None, description="关联的知识点 ID")
    correctness: float = Field(default=1.0, ge=0.0, le=1.0, description="答题/代码正确率")
    time_spent_ratio: float = Field(default=1.0, ge=0.0, description="实际耗时/预估耗时 比值")
    error_types: List[str] = Field(default_factory=list, description="本次犯的错误类型列表")
    resource_feedback: Dict[str, float] = Field(
        default_factory=dict,
        description="用户对各类资源的多模态评分 (1-5)"
    )
    help_request_count: int = Field(default=0, ge=0, description="求助次数")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO 时间戳"
    )

    # ---- 加分项扩展字段 ----
    tutor_query: Optional[str] = Field(
        default=None,
        description="学生在 Tutor Agent 中输入的答疑提问文本 (智能辅导加分项)"
    )
    accuracy_rate: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="本轮答题正确率 (学习评估加分项)"
    )
    code_pass_rate: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="本轮代码通过率 (学习评估加分项)"
    )
    duration_ratio: float = Field(
        default=1.0, ge=0.0,
        description="本轮实际耗时与标准耗时的比率 (学习评估加分项)"
    )


# ---------------------------------------------------------------------------
# 资源卡片子结构
# ---------------------------------------------------------------------------

class ResourceCard(BaseModel):
    """多模态资源卡片 — 由 Content Mesh 生成的标准输出单元。"""

    resource_id: str = Field(..., description="资源唯一 ID")
    node_id: str = Field(..., description="关联的知识点 ID")
    card_type: str = Field(
        ...,
        pattern=r"^(concept_map|code_snippet|interactive_exercise|video_summary|diagnostic_quiz)$",
        description="资源卡片类型（5 种）"
    )
    content: str = Field(..., description="Markdown 格式内容")
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0, description="难度系数 (0.0-1.0)")
    cognitive_style: str = Field(default="textual", description="适配的认知风格")
    parent_chunk_id: Optional[str] = Field(default=None, description="Milvus 父块 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


# ---------------------------------------------------------------------------
# 全局 AgentState
# ---------------------------------------------------------------------------

class AgentFeedbackItem(BaseModel):
    """Structured agent feedback for the workspace feedback rail."""

    agent: str = Field(..., min_length=1, description="Agent name")
    stage: str = Field(default="", description="Workflow stage")
    status: str = Field(default="info", description="info|success|warning|error|skipped")
    headline: str = Field(default="", description="Short summary headline")
    summary: str = Field(default="", description="One-paragraph summary")
    details_md: str = Field(default="", description="Markdown detail body")
    structured_data: Dict[str, Any] = Field(default_factory=dict, description="Structured metrics/data")
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="Companion render artifacts")


class AgentState(BaseModel):
    """LangGraph StateGraph 的全局上下文状态。

    所有 Agent Node 通过此状态共享数据。LangGraph 的 add_node / add_edge
    机制基于此 Pydantic 模型进行序列化传递。
    """

    # ---- 用户 & 课程标识 ----
    user_id: str = Field(..., min_length=1, description="用户唯一 ID")
    course_id: str = Field(..., min_length=1, description="课程唯一 ID")

    # ---- 图谱位置 ----
    current_node_id: Optional[str] = Field(default=None, description="当前学习的知识点 ID (Neo4j)")
    target_node_id: Optional[str] = Field(default=None, description="用户的终极学习目标 ID (Neo4j)")

    # ---- 6 维动态用户画像 ----
    static_profile: StaticProfile = Field(
        default_factory=StaticProfile,
        description="静态画像（认知风格先验、动机、时间预算）"
    )
    dynamic_profile: DynamicProfile = Field(
        default_factory=DynamicProfile,
        description="动态画像（掌握度、错误分布、PID 状态）"
    )

    # ---- 路径与资源队列 ----
    active_path: List[str] = Field(
        default_factory=list,
        description="Path Planner 计算的拓扑激活序列（node_id 有序列表）"
    )
    generated_resources: Dict[str, List[ResourceCard]] = Field(
        default_factory=dict,
        description="Key=node_id, Value=该节点生成的资源卡片列表"
    )
    agent_feedback: List[AgentFeedbackItem] = Field(
        default_factory=list,
        description="Structured feedback timeline for the current workspace state"
    )

    # ---- 控制流与调度变量 ----
    latest_behavior: Optional[LatestBehavior] = Field(
        default=None,
        description="最近一次交互的行为统计数据包"
    )
    c_epoch: int = Field(
        default=0, ge=0,
        description="冷启动启发式交互计数器（前 N 轮使用特殊策略）"
    )
    re_plan_triggered: bool = Field(
        default=False,
        description="全局路径重新寻路控制闸门"
    )

    # ---- 加分项扩展字段 ----
    pedagogical_strategy: str = Field(
        default="STANDARD_PATH",
        pattern=r"^(STANDARD_PATH|SCAFFOLD_HELP|EDGE_CASE_DRILL)$",
        description=(
            "当前教学法策略控制变量。由 Assessment Node 迟滞环决策树驱动切换，"
            "直接影响 Content Mesh 的资源生成 Prompt 策略。"
        )
    )
    tutor_response: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Tutor Agent 生成的多模态答疑响应卡片。包含 text_explanation, "
            "mermaid_src, video_hydration 三个轨道的输出。"
        )
    )
    recommended_resource_style: Optional[str] = Field(
        default=None,
        description="Profiler 推荐给 Content Mesh 的主导资源风格"
    )

    # ---- 异常与审计 ----
    errors: List[str] = Field(
        default_factory=list,
        description="运行过程中收集的异常/警告信息"
    )
    internal_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="仅供编排层和基础设施使用的内部状态存储"
    )

    # ---- 会话元数据 ----
    session_start: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="会话启动 ISO 时间戳"
    )
    iteration: int = Field(default=0, ge=0, description="当前 LangGraph 迭代轮次")

    def increment_epoch(self) -> None:
        """递增冷启动计数器。"""
        self.c_epoch += 1

    def record_error(self, error_msg: str) -> None:
        """追加一条错误信息并截断至最近 50 条。"""
        self.errors.append(f"[{datetime.utcnow().isoformat()}] {error_msg}")
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]

    def is_cold_start(self, threshold: int = 5) -> bool:
        """判断当前是否处于冷启动阶段。"""
        return self.c_epoch < threshold

    def trigger_replan(self) -> None:
        """触发全局重新寻路。"""
        self.re_plan_triggered = True

    def clear_replan(self) -> None:
        """清除重新寻路标记。"""
        self.re_plan_triggered = False

    def get_next_node(self) -> Optional[str]:
        """获取路径队列中的下一个待学习节点（不弹出）。"""
        if not self.active_path:
            return None
        return self.active_path[0] if self.active_path else None
