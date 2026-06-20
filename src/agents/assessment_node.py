# -*- coding: utf-8 -*-
"""
Assessment Reporter Node — 学习效果评估与策略自适应节点 (LangGraph 加分项)
=============================================================================

本节点是 EduAgent 多智能体系统中的学习评估与策略自适应控制节点，
对应赛题「学习效果评估」可选加分项。通过对历史行为堆栈执行指数移动平均（EMA）
消除偶发性数据噪音，产出长效能力雷达图，并触发带有控制论迟滞环（Hysteresis Loop）
的教学法干预决策树，直接修改全局控制变量 pedagogical_strategy。

核心能力:
  1. 5 维能力雷达图 EMA 平滑演进
     - 概念理解力 (Concept Understanding)
     - 代码工程力 (Code Engineering)
     - 逻辑推理力 (Logical Reasoning)
     - 错题抗挫力 (Error Resilience)
     - 时间管理力 (Time Management)

  2. 控制论迟滞环自适应调控决策树
     - 双阈值控制带 (Double-Threshold Control Band)
     - 策略冷却时间门 (避免 Policy Thrashing 策略震荡)
     - 三种教学法策略: STANDARD_PATH, SCAFFOLD_HELP, EDGE_CASE_DRILL

  3. Markdown 格式《多维度综合评估诊断报告》自动生成

算法依据:
  a_k^(t) = α · Current_Score(x_k) + (1-α) · a_k^(t-1)
  A_mix = Mean(A_vector)
  Hysteresis Band: T_low = 0.40, T_high = 0.75

依赖声明:
  本模块算法独立于任何特定大模型 API，为纯控制论 + 统计学计算。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 枚举与常量
# ============================================================================

# 5 维能力维度索引
RADAR_DIM_CONCEPT = 0       # 概念理解力
RADAR_DIM_CODE = 1           # 代码工程力
RADAR_DIM_LOGIC = 2          # 逻辑推理力
RADAR_DIM_RESILIENCE = 3     # 错题抗挫力
RADAR_DIM_TIME = 4           # 时间管理力

RADAR_DIM_NAMES = [
    "概念理解力",
    "代码工程力",
    "逻辑推理力",
    "错题抗挫力",
    "时间管理力",
]

# 教学法策略枚举
STRATEGY_STANDARD = "STANDARD_PATH"
STRATEGY_SCAFFOLD = "SCAFFOLD_HELP"
STRATEGY_EDGE_CASE = "EDGE_CASE_DRILL"


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class AssessmentInput(BaseModel):
    """Assessment Node 的标准化输入。"""

    agent_state: Any = Field(..., description="当前 AgentState 全量快照")


class AssessmentOutput(BaseModel):
    """Assessment Node 的标准化输出。"""

    agent_state: Any = Field(..., description="更新后的 AgentState（含 capability_radar, diagnostic_report_md, pedagogical_strategy）")


class CapabilityRadar(BaseModel):
    """5 维长效能力雷达图的强类型表示。"""

    concept_understanding: float = Field(
        default=0.5, ge=0.0, le=1.0, description="概念理解力"
    )
    code_engineering: float = Field(
        default=0.5, ge=0.0, le=1.0, description="代码工程力"
    )
    logical_reasoning: float = Field(
        default=0.5, ge=0.0, le=1.0, description="逻辑推理力"
    )
    error_resilience: float = Field(
        default=0.5, ge=0.0, le=1.0, description="错题抗挫力"
    )
    time_management: float = Field(
        default=0.5, ge=0.0, le=1.0, description="时间管理力"
    )

    def to_list(self) -> List[float]:
        return [
            self.concept_understanding,
            self.code_engineering,
            self.logical_reasoning,
            self.error_resilience,
            self.time_management,
        ]

    @classmethod
    def from_list(cls, values: List[float]) -> "CapabilityRadar":
        if len(values) != 5:
            raise ValueError(f"capability_radar 必须包含 5 个值，实际: {len(values)}")
        return cls(
            concept_understanding=values[0],
            code_engineering=values[1],
            logical_reasoning=values[2],
            error_resilience=values[3],
            time_management=values[4],
        )

    def compute_mean(self) -> float:
        """计算 5 维能力综合指标 A_mix。"""
        return float(np.mean(self.to_list()))

    def describe(self) -> str:
        """生成人类可读的能力维度描述。"""
        labels = []
        for name, val in zip(RADAR_DIM_NAMES, self.to_list()):
            if val >= 0.80:
                label = "[A] 优秀"
            elif val >= 0.60:
                label = "[B] 良好"
            elif val >= 0.40:
                label = "[C] 待提升"
            else:
                label = "[D] 亟需加强"
            labels.append(f"{name}={val:.2f}({label})")
        return ", ".join(labels)


# ============================================================================
# 迟滞环决策树
# ============================================================================

class HysteresisStrategyController:
    """控制论迟滞环自适应决策树 — 防止策略频繁跳变震荡 (Policy Thrashing)。

    设计原理:
      - 双阈值控制带: T_low=0.40（降级下界）, T_high=0.75（升级上界）
      - 只有 A_mix 跌破 T_low 且 C_fail >= 2 时触发降级干预
      - 只有 A_mix 冲破 T_high 时才准予解除干预
      - 常态过渡区保持现状，避免在及格线边缘频繁切换
      - 特异性分支: boundary_miss EMA 连续 3 次走高 → EDGE_CASE_DRILL

    状态转换图:
      STANDARD_PATH ──(A_mix < 0.40 & fail >= 2)──► SCAFFOLD_HELP
      SCAFFOLD_HELP  ──(A_mix > 0.75)──────────────► STANDARD_PATH
      STANDARD_PATH  ──(boundary_miss↑ ×3)──────────► EDGE_CASE_DRILL
      EDGE_CASE_DRILL──(A_mix > 0.75)───────────────► STANDARD_PATH
    """

    T_LOW: float = 0.40    # 策略降级跌破下限阈值
    T_HIGH: float = 0.75   # 策略升级冲破上限阈值
    FAIL_GATE: int = 2     # 降级干预所需的最小连续失败次数
    BOUNDARY_EMA_WINDOW: int = 3      # 边界遗漏 EMA 连续走高检测窗口
    BOUNDARY_EMA_THRESHOLD: float = 0.5  # 边界遗漏触发阈值

    def decide(
        self,
        a_mix: float,
        current_strategy: str,
        fail_counter: int,
        boundary_miss_ema_sequence: List[float],
    ) -> str:
        """执行迟滞环决策树，返回应切换到的教学法策略。

        Args:
            a_mix: 5 维能力综合指标均值。
            current_strategy: 当前策略 (STANDARD_PATH / SCAFFOLD_HELP / EDGE_CASE_DRILL)。
            fail_counter: 连续失败计数器 C_fail。
            boundary_miss_ema_sequence: 边界遗漏 EMA 历史序列（最近 N 轮）。

        Returns:
            新策略标识。
        """
        new_strategy = current_strategy

        # ---- 降级门控: SCAFFOLD_HELP ----
        # 只有当前非降级、A_mix 跌破下界、且连续失败达标时触发
        if (
            current_strategy != STRATEGY_SCAFFOLD
            and a_mix < self.T_LOW
            and fail_counter >= self.FAIL_GATE
        ):
            new_strategy = STRATEGY_SCAFFOLD

        # ---- 升级解除门控 ----
        elif (
            current_strategy in (STRATEGY_SCAFFOLD, STRATEGY_EDGE_CASE)
            and a_mix > self.T_HIGH
        ):
            new_strategy = STRATEGY_STANDARD

        # ---- 特异性分支: EDGE_CASE_DRILL ----
        # 在常态路径下，若边界遗漏 EMA 连续 N 次超过阈值
        elif current_strategy == STRATEGY_STANDARD and len(boundary_miss_ema_sequence) >= self.BOUNDARY_EMA_WINDOW:
            recent = boundary_miss_ema_sequence[-self.BOUNDARY_EMA_WINDOW:]
            if all(v > self.BOUNDARY_EMA_THRESHOLD for v in recent):
                new_strategy = STRATEGY_EDGE_CASE

        return new_strategy


# ============================================================================
# Assessment Reporter 主节点
# ============================================================================

class AssessmentReporterNode:
    """长期能力评估与迟滞环自适应策略控制节点。

    在每个 LangGraph 迭代轮次结束时（通常位于 Validator 之后），
    执行以下流程:
      1. 提炼本轮多源清洗后特征数据
      2. 通过 EMA 增量更新 5 维长效能力向量
      3. 执行迟滞环决策树 → 更新 pedagogical_strategy
      4. 生成 Markdown 格式《多维度综合评估诊断报告》
      5. 写回 AgentState

    使用示例:
        >>> assessor = AssessmentReporterNode(alpha=0.2)
        >>> inp = AssessmentInput(agent_state=state)
        >>> out = assessor(inp)
        >>> print(out.agent_state.diagnostic_report_md)
    """

    DEFAULT_ALPHA: float = 0.2  # EMA 平滑权重系数

    def __init__(
        self,
        alpha: float = 0.2,
        t_low: float = 0.40,
        t_high: float = 0.75,
    ) -> None:
        """初始化 AssessmentReporterNode。

        Args:
            alpha: EMA 平滑系数 (0 < alpha ≤ 1)。越小越平滑，越大越敏感。
            t_low: 策略降级下限阈值。
            t_high: 策略升级上限阈值。
        """
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha 必须在 (0, 1] 区间内，实际: {alpha}")
        if not 0.0 <= t_low < t_high <= 1.0:
            raise ValueError(f"阈值必须满足 0 ≤ t_low < t_high ≤ 1")

        self.alpha = alpha
        self._controller = HysteresisStrategyController()
        # 允许覆盖默认阈值
        self._controller.T_LOW = t_low
        self._controller.T_HIGH = t_high

    @property
    def t_low(self) -> float:
        return self._controller.T_LOW

    @property
    def t_high(self) -> float:
        return self._controller.T_HIGH

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def __call__(self, inp: AssessmentInput) -> AssessmentOutput:
        """执行一轮完整的学习效果评估与策略自适应。

        Args:
            inp: AssessmentInput（含 agent_state）。

        Returns:
            AssessmentOutput（含更新后的 agent_state）。
        """
        return self.execute_evaluation(inp.agent_state)

    def execute_evaluation(self, state: Any) -> AssessmentOutput:
        """执行评估核心流程（兼容直接传入 AgentState 的调用方式）。

        Args:
            state: 当前 AgentState。

        Returns:
            AssessmentOutput。
        """
        dynamic_profile = state.dynamic_profile
        latest_behavior = state.latest_behavior

        # ---- 1. 提炼本轮多源清洗后特征数据 ----
        x1 = getattr(latest_behavior, "accuracy_rate", 0.5) if latest_behavior else 0.5
        x2 = getattr(latest_behavior, "code_pass_rate", 0.5) if latest_behavior else 0.5
        x3 = getattr(latest_behavior, "duration_ratio", 1.0) if latest_behavior else 1.0

        # ---- 2. 增量更新 5 维长效能力向量 (EMA 模型) ----
        # 获取当前能力雷达（默认为中性值）
        current_radar = list(getattr(
            dynamic_profile, "capability_radar", [0.5, 0.5, 0.5, 0.5, 0.5]
        ))
        if len(current_radar) != 5:
            current_radar = [0.5, 0.5, 0.5, 0.5, 0.5]

        # 映射计算当前交互维度的得分变动
        # score[0]: 概念理解力 ← 正确率
        # score[1]: 代码工程力  ← 代码通过率
        # score[2]: 逻辑推理力  ← 基于耗时比的反向映射（太快的可能是蒙的，太慢的逻辑卡顿）
        # score[3]: 错题抗挫力  ← 正确率与代码通过率的混合
        # score[4]: 时间管理力  ← 默认中性（后续可由行为模式细化）
        scores = self._compute_dimension_scores(x1, x2, x3)

        updated_radar: List[float] = []
        for i in range(5):
            new_val = self.alpha * scores[i] + (1.0 - self.alpha) * current_radar[i]
            updated_radar.append(float(np.clip(new_val, 0.0, 1.0)))

        # ---- 3. 更新边界遗漏 EMA 历史 ----
        boundary_miss_seq = list(getattr(
            dynamic_profile, "boundary_miss_ema_sequence", []
        ) or [])
        boundary_current = 0.0
        if latest_behavior and hasattr(latest_behavior, "error_types"):
            error_types = latest_behavior.error_types or []
            boundary_current = 1.0 if "boundary_miss" in error_types else 0.0
        boundary_ema = self._update_boundary_ema(boundary_miss_seq, boundary_current)
        # 保留最近 10 轮
        if len(boundary_ema) > 10:
            boundary_ema = boundary_ema[-10:]

        # ---- 4. 迟滞环决策树 ----
        a_mix = float(np.mean(updated_radar))
        current_strategy = getattr(state, "pedagogical_strategy", STRATEGY_STANDARD) or STRATEGY_STANDARD
        fail_counter = getattr(dynamic_profile, "continuous_fail_counter", 0) or 0

        new_strategy = self._controller.decide(
            a_mix=a_mix,
            current_strategy=current_strategy,
            fail_counter=fail_counter,
            boundary_miss_ema_sequence=boundary_ema,
        )

        # ---- 5. 生成诊断报告 ----
        diagnostic_report = self._generate_diagnostic_report(
            updated_radar, a_mix, new_strategy, current_strategy
        )

        # ---- 6. 写回 AgentState ----
        dynamic_profile.capability_radar = updated_radar
        dynamic_profile.diagnostic_report_md = diagnostic_report
        dynamic_profile.boundary_miss_ema_sequence = boundary_ema
        state.pedagogical_strategy = new_strategy

        return AssessmentOutput(agent_state=state)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _compute_dimension_scores(
        self,
        accuracy: float,
        code_pass: float,
        duration_ratio: float,
    ) -> List[float]:
        """从原始行为特征计算 5 维能力维度的本轮得分。

        Args:
            accuracy: 答题正确率 (0-1)。
            code_pass: 代码通过率 (0-1)。
            duration_ratio: 实际耗时/标准耗时比值。

        Returns:
            [概念理解力, 代码工程力, 逻辑推理力, 错题抗挫力, 时间管理力]。
        """
        # 逻辑推理力：耗时比在 0.8-1.5 之间最优（不太快也不太慢）
        logic_score = 1.0 - abs(1.0 - min(duration_ratio, 2.0))
        logic_score = max(0.0, min(1.0, logic_score))

        # 错题抗挫力：正确率 + 代码通过率的混合
        resilience_score = accuracy * 0.6 + code_pass * 0.4

        # 时间管理力：耗时比接近 1.0 最优
        time_score = 1.0 - abs(1.0 - min(duration_ratio, 2.0)) * 0.5
        time_score = max(0.0, min(1.0, time_score))

        return [
            accuracy,          # 概念理解力 ← 直接由正确率反映
            code_pass,         # 代码工程力 ← 代码通过率
            logic_score,       # 逻辑推理力 ← 耗时合理性
            resilience_score,  # 错题抗挫力 ← 综合衡量
            time_score,        # 时间管理力 ← 时间利用效率
        ]

    def _update_boundary_ema(
        self,
        history: List[float],
        current: float,
    ) -> List[float]:
        """更新边界遗漏 EMA 序列。

        Args:
            history: 历史 EMA 序列。
            current: 本轮是否出现边界遗漏 (0 或 1)。

        Returns:
            更新后的序列。
        """
        if not history:
            history = [current]
        else:
            # EMA 平滑: 新值 = α * current + (1-α) * prev
            smoothed = self.alpha * current + (1.0 - self.alpha) * history[-1]
            history = history + [smoothed]
        return history

    def _generate_diagnostic_report(
        self,
        radar: List[float],
        a_mix: float,
        new_strategy: str,
        old_strategy: str,
    ) -> str:
        """生成 Markdown 格式的《多维度综合评估诊断报告》。

        Args:
            radar: 5 维能力向量。
            a_mix: 综合效能指数。
            new_strategy: 新策略。
            old_strategy: 旧策略。

        Returns:
            Markdown 报告字符串。
        """
        # 策略描述映射
        strategy_desc = {
            STRATEGY_STANDARD: "[Normal] 标准进阶路径 -- 按计划推进正常学习节奏",
            STRATEGY_SCAFFOLD: "[Help] 脚手架降级干预 -- 降低难度、增加提示与引导",
            STRATEGY_EDGE_CASE: "[Drill] 边缘用例强化 -- 针对边界条件遗漏进行集中训练",
        }
        strategy_change = ""
        if new_strategy != old_strategy:
            strategy_change = (
                f"\n* **策略切换**: `{old_strategy}` -> `{new_strategy}`"
            )

        # 能力维度诊断语段
        dim_lines = []
        for i, (name, val) in enumerate(zip(RADAR_DIM_NAMES, radar)):
            if val >= 0.80:
                diagnosis = "已达优秀水平，可适当增加挑战难度以维持学习兴趣。"
            elif val >= 0.60:
                diagnosis = "处于良好区间，建议继续保持当前学习节奏。"
            elif val >= 0.40:
                diagnosis = "存在提升空间，建议针对性增加该维度练习量。"
            else:
                diagnosis = "亟需加强，系统已自动调整资源难度与推送策略。"
            dim_lines.append(f"* **{name}**: {val:.2f} — {diagnosis}")

        dim_section = "\n".join(dim_lines)

        # 能力评级
        if a_mix >= 0.75:
            grade = "[A] 优秀"
        elif a_mix >= 0.60:
            grade = "[B] 良好"
        elif a_mix >= 0.40:
            grade = "[C] 待提升"
        else:
            grade = "[D] 亟需加强"

        report = f"""### 学术能力综合评估报告

#### 能力雷达图谱分布
{dim_section}

#### 系统综合效能指数
* **A_mix**: {a_mix:.2f}（{grade}）

#### 当前下发调控策略
* **策略**: `{new_strategy}` -- {strategy_desc.get(new_strategy, '未知策略')}{strategy_change}
"""
        return report.strip()


# ============================================================================
# 工厂函数
# ============================================================================

def create_assessment_node(
    alpha: float = 0.2,
    t_low: float = 0.40,
    t_high: float = 0.75,
) -> AssessmentReporterNode:
    """创建 AssessmentReporterNode 实例的工厂函数。

    Args:
        alpha: EMA 平滑系数，默认 0.2。
        t_low: 降级阈值，默认 0.40。
        t_high: 升级阈值，默认 0.75。

    Returns:
        配置好的 AssessmentReporterNode。
    """
    return AssessmentReporterNode(alpha=alpha, t_low=t_low, t_high=t_high)
