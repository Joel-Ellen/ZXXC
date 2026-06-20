# -*- coding: utf-8 -*-
"""
Evaluator Node — LangGraph 核心评估控制节点
=============================================

本节点是 LangGraph StateGraph 中的关键控制环节，在用户完成当前知识点
交互后执行。主要职责：

1. 行为多维非线性门控清洗 (Behavioral Non-linear Gating)
   - 捕获答题正确率、代码通过率、时长比、提问频次
   - 清洗异常行为：挂机检测、秒杀作弊检测、辅导阻碍系数调整

2. PID 平滑控制器 (PID Smoothing Controller)
   - 计算即时表现与历史掌握度的系统误差
   - 微分项对突变噪音（偶发满分/挂科）进行反向阻尼平滑
   - 输出平滑后的掌握度增量

3. 重寻路闸门控制 (Re-plan Gating)
   - 判定控制量是否连续 N 次滑出置信区间
   - 触发 re_plan_triggered 标记，遏制频繁重寻路引起的后端震荡

依赖声明：
  本模块的算法实现独立于任何特定大模型 API。
  PID 控制论基础参考 Åström & Hägglund (2006)。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from ..state.agent_state import AgentState, LatestBehavior, ErrorTypeDistribution
from ..infrastructure.pid_controller import PIDController, PIDConfig, PIDStepInput


# ============================================================================
# 枚举与常量
# ============================================================================

class AnomalyType(str, Enum):
    """行为异常类型枚举。"""
    NORMAL = "normal"                    # 正常
    AFK = "afk"                          # 挂机：时长比 > 3.0
    CHEATING_SPEED = "cheating_speed"    # 秒杀作弊：正确率极高 + 时长极短
    INCONSISTENT = "inconsistent"        # 不一致：正确率极高但提问题频次极高
    LOW_EFFORT = "low_effort"            # 低投入：多次连续异常
    RAPID_GUESSING = "rapid_guessing"    # 快速猜测：中等正确率 + 极短时长


class ReplanDecision(str, Enum):
    """重寻路决策枚举。"""
    MAINTAIN = "maintain"                # 维持原路径
    PENDING = "pending"                  # 待定（误差积累中）
    TRIGGER = "trigger"                  # 触发重寻路


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class BehaviorVector(BaseModel):
    """异构行为特征向量 — 从用户交互中实时捕获的原始特征。

    所有特征在当前知识点窗口内统计。
    """

    # 核心表现指标
    answer_correctness: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="答题正确率 (0.0-1.0)"
    )
    code_pass_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="代码/编程题通过率 (0.0-1.0)"
    )
    time_spent_ratio: float = Field(
        default=1.0, ge=0.0,
        description="实际耗时 / 预估耗时 比值"
    )
    help_request_count: int = Field(
        default=0, ge=0,
        description="主动求助/提问次数"
    )

    # 辅助特征
    total_attempts: int = Field(
        default=1, ge=1,
        description="总尝试次数"
    )
    resource_switches: int = Field(
        default=0, ge=0,
        description="在当前知识点内切换/跳过资源卡片的次数"
    )
    interaction_events: int = Field(
        default=0, ge=0,
        description="交互事件总数（点击/滚动/输入）"
    )
    node_id: str = Field(default="", description="关联的知识点 ID")

    @field_validator("time_spent_ratio")
    @classmethod
    def ratio_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"时长比不能为负: {v}")
        return v


class BehaviorAnomaly(BaseModel):
    """单次行为异常诊断结果。"""

    anomaly_type: AnomalyType = Field(default=AnomalyType.NORMAL)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="异常判定置信度")
    description: str = Field(default="", description="诊断描述")
    score_penalty: float = Field(default=0.0, ge=0.0, le=1.0, description="分数惩罚因子 (0=无惩罚, 1=完全否定)")
    friction_multiplier: float = Field(
        default=1.0, ge=1.0,
        description="辅导阻碍系数乘数 (≥1.0, 值越大后续资源难度越高)"
    )


class CleanedBehavior(BaseModel):
    """经非线性门控清洗后的有效行为数据。"""

    raw: BehaviorVector = Field(..., description="原始行为向量")
    effective_correctness: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="清洗后的有效正确率"
    )
    effective_code_pass: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="清洗后的有效代码通过率"
    )
    anomaly: BehaviorAnomaly = Field(
        default_factory=BehaviorAnomaly,
        description="异常诊断结果"
    )
    is_valid: bool = Field(default=True, description="行为数据是否有效（非挂机）")
    friction_coefficient: float = Field(
        default=1.0, ge=1.0,
        description="辅导阻碍系数 (1.0=无阻碍)"
    )


class PIDReplanGate(BaseModel):
    """PID 重寻路闸门 — 跟踪误差变化趋势以遏制重寻路震荡。

    设计原理:
      跟踪 Δe = e(t) - e(t-1) （误差的一阶差分）。
      - Δe ≤ 0 → 误差在缩小，学习在进步 → 正常 (MAINTAIN)
      - Δe > 0 → 误差在扩大，学习在退步 → 越界
      - 连续 N 次 Δe > 0 → 学生持续退步 → 触发重寻路 (TRIGGER)

    这种方法从根本上避免了"绝对值阈值难以校准"的问题:
      无论 mastery=0.1 还是 mastery=0.9，Δe 的符号决定方向。
    """

    node_id: str = Field(default="", description="关联的知识点 ID")
    window_size: int = Field(default=5, ge=2, le=20, description="滑动窗口大小")
    # 重命名以反映新语义: 跟踪误差变化
    stagnation_threshold: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="停滞阈值: |Δe| < 此值视为停滞 (也视为退步)"
    )
    consecutive_out_of_bounds: int = Field(
        default=0, ge=0, description="连续越界计数 (Δe > 0 或 |Δe| < stagnation)"
    )
    trigger_threshold: int = Field(
        default=3, ge=1, description="连续越界触发阈值 (达到此值触发重寻路)"
    )
    control_history: List[float] = Field(
        default_factory=list,
        description="误差历史值 e(t)（最近 window_size 个）"
    )
    prev_error: Optional[float] = Field(
        default=None, description="上一轮误差 e(t-1)"
    )
    decision: ReplanDecision = Field(
        default=ReplanDecision.MAINTAIN,
        description="当前重寻路决策"
    )

    def record_control_value(self, error: float) -> ReplanDecision:
        """记录一次 PID 误差并计算 Δe 趋势。

        越界判定（满足任一即为越界）:
          1. Δe > 0 → 误差在扩大（掌握度在下降）
          2. |Δe| < stagnation_threshold AND error > 0.3 → 停滞不前

        Args:
            error: PID 控制器的当前误差 e(t) = setpoint - mastery。

        Returns:
            ReplanDecision: 当前决策。
        """
        self.control_history.append(error)
        if len(self.control_history) > self.window_size:
            self.control_history = self.control_history[-self.window_size:]

        # 计算误差变化
        out_of_bounds = False
        if self.prev_error is not None:
            delta_e = error - self.prev_error  # Δe = e(t) - e(t-1)
            # 条件 1: 误差扩大（退步）
            if delta_e > 0:
                out_of_bounds = True
            # 条件 2: 误差停滞在较高水平
            elif abs(delta_e) < self.stagnation_threshold and error > 0.3:
                out_of_bounds = True

        self.prev_error = error

        if out_of_bounds:
            self.consecutive_out_of_bounds += 1
        else:
            self.consecutive_out_of_bounds = 0

        # 判定
        if self.consecutive_out_of_bounds >= self.trigger_threshold:
            self.decision = ReplanDecision.TRIGGER
        elif self.consecutive_out_of_bounds > 0:
            self.decision = ReplanDecision.PENDING
        else:
            self.decision = ReplanDecision.MAINTAIN

        return self.decision

    def reset(self) -> None:
        """重置闸门状态（触发重寻路后调用）。"""
        self.consecutive_out_of_bounds = 0
        self.control_history.clear()
        self.prev_error = None
        self.decision = ReplanDecision.MAINTAIN


class EvaluatorInput(BaseModel):
    """Evaluator Node 的输入结构 — LangGraph StateGraph Node 的入口签名。"""

    agent_state: AgentState = Field(..., description="当前全局 AgentState")
    raw_behavior: BehaviorVector = Field(..., description="当前窗口的原始行为向量")
    pid_config: Optional[PIDConfig] = Field(
        default=None,
        description="PID 控制器配置 (None 则使用默认)"
    )
    gate_config: Optional["GateConfig"] = Field(
        default=None,
        description="重寻路闸门配置 (None 则使用默认)"
    )


class GateConfig(BaseModel):
    """重寻路闸门可配置参数。"""

    window_size: int = Field(default=5, ge=2, le=20)
    stagnation_threshold: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="误差停滞阈值 (|Δe| < 此值且 error > 0.3 视为停滞)"
    )
    trigger_threshold: int = Field(default=3, ge=1, le=10)


class EvaluatorOutput(BaseModel):
    """Evaluator Node 的输出结构 — 写入 AgentState 并传递给下游节点。"""

    agent_state: AgentState = Field(..., description="更新后的全局 AgentState")
    cleaned_behavior: CleanedBehavior = Field(..., description="清洗后的行为数据")
    updated_mastery: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="更新后的知识点掌握度 (0.0-1.0)"
    )
    mastery_delta: float = Field(
        default=0.0, description="掌握度变化量 Δm (可正可负)"
    )
    pid_control_output: float = Field(
        default=0.0, description="PID 控制器输出 u(t)"
    )
    pid_error: float = Field(
        default=0.0, description="PID 跟踪误差 e(t) = r(t) - y(t)"
    )
    replan_decision: ReplanDecision = Field(
        default=ReplanDecision.MAINTAIN,
        description="重寻路决策"
    )
    anomaly_detected: bool = Field(
        default=False, description="是否检测到异常行为"
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict,
        description="诊断信息（供前端调试面板使用）"
    )


# ============================================================================
# 行为清洗器 (Non-linear Gating Cleaner)
# ============================================================================

class BehaviorCleaner:
    """行为多维非线性门控清洗器。

    清洗规则矩阵 (全部基于教育学实证):
      ┌─────────────────┬──────────────────┬──────────────────────┐
      │ 条件              │ 判定              │ 处理                     │
      ├─────────────────┼──────────────────┼──────────────────────┤
      │ time_ratio > 3.0  │ 挂机 (AFK)        │ 强置 time_ratio=1.0    │
      │                   │                  │ 标记 is_valid=False     │
      ├─────────────────┼──────────────────┼──────────────────────┤
      │ correctness > 0.9 │ 秒杀作弊           │ 得分削减 90%             │
      │ && time_ratio     │ (Cheating Speed) │ friction × 2.0         │
      │ < 0.05            │                  │                       │
      ├─────────────────┼──────────────────┼──────────────────────┤
      │ correctness > 0.9 │ 不一致             │ 得分削减 50%             │
      │ && help_requests  │ (Inconsistent)   │ friction × 1.5         │
      │ > 5               │                  │                       │
      ├─────────────────┼──────────────────┼──────────────────────┤
      │ time_ratio < 0.1  │ 快速猜测           │ 置信度降低               │
      │ && 0.4 < correct  │ (Rapid Guessing) │ friction × 1.3         │
      │ < 0.7             │                  │                       │
      └─────────────────┴──────────────────┴──────────────────────┘

    门控函数采用 Sigmoid-based 软判决：
      penalty(correctness, time_ratio) = σ(α·(correctness - β) + γ·(δ - time_ratio))
      其中 σ(x) = 1/(1+e^{-x}) 为 Logistic 函数。
    """

    # 硬阈值常量
    AFK_TIME_RATIO_THRESHOLD: float = 3.0
    CHEATING_CORRECTNESS_MIN: float = 0.90
    CHEATING_TIME_RATIO_MAX: float = 0.05
    CHEATING_SCORE_PENALTY: float = 0.90       # 削减 90%
    CHEATING_FRICTION_MULT: float = 2.0

    INCONSISTENT_CORRECTNESS_MIN: float = 0.90
    INCONSISTENT_HELP_MIN: int = 5
    INCONSISTENT_SCORE_PENALTY: float = 0.50   # 削减 50%
    INCONSISTENT_FRICTION_MULT: float = 1.5

    RAPID_GUESS_TIME_MAX: float = 0.10
    RAPID_GUESS_CORRECTNESS_LO: float = 0.40
    RAPID_GUESS_CORRECTNESS_HI: float = 0.70
    RAPID_GUESS_FRICTION_MULT: float = 1.3

    # 软门控 Sigmoid 参数
    SIGMOID_ALPHA: float = 8.0    # 正确率权重
    SIGMOID_BETA: float = 0.85    # 正确率偏移
    SIGMOID_GAMMA: float = 6.0    # 时长比权重
    SIGMOID_DELTA: float = 0.15   # 时长比偏移

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Logistic 函数，数值稳定版本。"""
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        else:
            exp_x = math.exp(x)
            return exp_x / (1.0 + exp_x)

    def clean(self, raw: BehaviorVector) -> CleanedBehavior:
        """对原始行为向量执行非线性门控清洗。

        Args:
            raw: 原始行为特征向量。

        Returns:
            CleanedBehavior: 清洗后的有效行为数据。
        """
        anomaly = BehaviorAnomaly()
        effective_correctness = raw.answer_correctness
        effective_code_pass = raw.code_pass_rate
        friction = 1.0
        is_valid = True

        time_ratio = raw.time_spent_ratio
        correctness = raw.answer_correctness
        help_count = raw.help_request_count

        # ---- Rule 1: 挂机检测 (AFK) ----
        if time_ratio > self.AFK_TIME_RATIO_THRESHOLD:
            anomaly = BehaviorAnomaly(
                anomaly_type=AnomalyType.AFK,
                confidence=self._sigmoid(
                    self.SIGMOID_GAMMA * (time_ratio - self.AFK_TIME_RATIO_THRESHOLD)
                ),
                description=(
                    f"挂机检测: 时长比={time_ratio:.2f} > {self.AFK_TIME_RATIO_THRESHOLD}, "
                    f"实际耗时远超预估，判定为无效交互"
                ),
                score_penalty=0.0,      # 挂机数据不用于评分
                friction_multiplier=1.0, # 挂机不增加阻碍
            )
            # 强置时长比为 1.0，标记无效
            effective_correctness = 0.0  # 挂机数据不计入掌握度
            effective_code_pass = 0.0
            is_valid = False
            # 使用调整后的 time_ratio 用于后续摩擦计算
            time_ratio = 1.0

        # ---- Rule 2: 秒杀作弊检测 (Cheating Speed) ----
        elif correctness >= self.CHEATING_CORRECTNESS_MIN and time_ratio < self.CHEATING_TIME_RATIO_MAX:
            soft_confidence = self._sigmoid(
                self.SIGMOID_ALPHA * (correctness - self.SIGMOID_BETA)
                + self.SIGMOID_GAMMA * (self.SIGMOID_DELTA - time_ratio)
            )
            anomaly = BehaviorAnomaly(
                anomaly_type=AnomalyType.CHEATING_SPEED,
                confidence=soft_confidence,
                description=(
                    f"秒杀作弊检测: 正确率={correctness:.3f} ≥ {self.CHEATING_CORRECTNESS_MIN}, "
                    f"时长比={time_ratio:.3f} < {self.CHEATING_TIME_RATIO_MAX}, "
                    f"判定为作弊行为，得分削减 {self.CHEATING_SCORE_PENALTY*100:.0f}%"
                ),
                score_penalty=self.CHEATING_SCORE_PENALTY,
                friction_multiplier=self.CHEATING_FRICTION_MULT,
            )
            effective_correctness = correctness * (1.0 - self.CHEATING_SCORE_PENALTY)
            effective_code_pass = raw.code_pass_rate * (1.0 - self.CHEATING_SCORE_PENALTY)
            friction = self.CHEATING_FRICTION_MULT

        # ---- Rule 3: 高正确率+高频提问（不一致） ----
        elif correctness >= self.INCONSISTENT_CORRECTNESS_MIN and help_count > self.INCONSISTENT_HELP_MIN:
            soft_confidence = self._sigmoid(
                0.5 * (correctness - self.INCONSISTENT_CORRECTNESS_MIN) * 20.0
                + 0.3 * math.log(1 + help_count - self.INCONSISTENT_HELP_MIN)
            )
            anomaly = BehaviorAnomaly(
                anomaly_type=AnomalyType.INCONSISTENT,
                confidence=soft_confidence,
                description=(
                    f"不一致行为: 正确率={correctness:.3f} 但提问 {help_count} 次, "
                    f"疑似借助外部辅助工具，得分削减 {self.INCONSISTENT_SCORE_PENALTY*100:.0f}%"
                ),
                score_penalty=self.INCONSISTENT_SCORE_PENALTY,
                friction_multiplier=self.INCONSISTENT_FRICTION_MULT,
            )
            effective_correctness = correctness * (1.0 - self.INCONSISTENT_SCORE_PENALTY)
            friction = self.INCONSISTENT_FRICTION_MULT

        # ---- Rule 4: 快速猜测 (Rapid Guessing) ----
        elif (time_ratio < self.RAPID_GUESS_TIME_MAX
              and self.RAPID_GUESS_CORRECTNESS_LO < correctness < self.RAPID_GUESS_CORRECTNESS_HI):
            anomaly = BehaviorAnomaly(
                anomaly_type=AnomalyType.RAPID_GUESSING,
                confidence=0.5 + 0.5 * (1.0 - time_ratio / self.RAPID_GUESS_TIME_MAX),
                description=(
                    f"快速猜测: 时长比={time_ratio:.3f} < {self.RAPID_GUESS_TIME_MAX}, "
                    f"正确率={correctness:.3f} 处于猜测区间, 辅导阻碍系数 ×{self.RAPID_GUESS_FRICTION_MULT}"
                ),
                score_penalty=0.0,  # 不惩罚正确率，但提高难度
                friction_multiplier=self.RAPID_GUESS_FRICTION_MULT,
            )
            friction = self.RAPID_GUESS_FRICTION_MULT

        # ---- 软门控融合: 基于 Sigmoid 的行为质量综合评分 ----
        # 用于微调最终的有效正确率（仅在无硬规则命中时生效）
        if anomaly.anomaly_type == AnomalyType.NORMAL:
            quality_score = self._sigmoid(
                self.SIGMOID_ALPHA * (correctness - self.SIGMOID_BETA)
                + self.SIGMOID_GAMMA * (time_ratio - self.SIGMOID_DELTA)
            )
            # quality_score ≈ 1.0 → 高质量学习行为
            # quality_score ≈ 0.0 → 低质量（可能是蒙的）
            # 对低质量行为微调有效正确率
            if quality_score < 0.3 and correctness > 0.7:
                # 高正确率但低质量：可能是猜测/作弊未达硬阈值
                effective_correctness = correctness * (0.5 + 0.5 * quality_score)
                friction = 1.0 + (1.0 - quality_score) * 0.5

        return CleanedBehavior(
            raw=raw,
            effective_correctness=round(min(effective_correctness, 1.0), 6),
            effective_code_pass=round(min(effective_code_pass, 1.0), 6),
            anomaly=anomaly,
            is_valid=is_valid,
            friction_coefficient=round(friction, 4),
        )


# ============================================================================
# PID 平滑评估控制器 (PID Smoothing Evaluation Controller)
# ============================================================================

class PIDReplanController:
    """PID 平滑控制器 + 重寻路闸门。

    双层控制架构:
      Layer 1 — PID 平滑:
        计算即时表现与历史掌握度的误差 e(t) = r(t) - y(t)。
        使用 PID 控制器产生平滑的掌握度增量 u(t)。
        微分项对突变噪音（偶发满分/挂科）产生反向阻尼，防止单一
        异常数据点导致掌握度剧烈波动。

      Layer 2 — 重寻路闸门:
        跟踪控制误差 e(t) 是否连续 N 次滑出置信区间。
        只有连续 N 次越界才触发 re_plan_triggered = True。
        单次越界 → PENDING，回到区间内 → 计数清零 → MAINTAIN。
        彻底遏制因噪声引起的频繁重寻路（后端震荡）。
    """

    def __init__(
        self,
        pid_config: Optional[PIDConfig] = None,
        gate_config: Optional[GateConfig] = None,
    ) -> None:
        """初始化 PID 平滑评估控制器。

        Args:
            pid_config: PID 控制器配置。
            gate_config: 重寻路闸门配置。
        """
        self._pid = PIDController(pid_config or PIDConfig())
        self._gate_config = gate_config or GateConfig()
        # 每个知识点的独立闸门
        self._gates: Dict[str, PIDReplanGate] = {}

    # ------------------------------------------------------------------
    # 核心评估方法
    # ------------------------------------------------------------------

    def evaluate(
        self,
        node_id: str,
        cleaned: CleanedBehavior,
        current_mastery: float,
        continuous_fail_counter: int,
        dt: float = 1.0,
    ) -> Tuple[float, float, float, float, ReplanDecision, PIDReplanGate]:
        """执行完整的 PID 平滑评估 + 重寻路闸门判定。

        Args:
            node_id: 知识点 ID。
            cleaned: 清洗后的行为数据。
            current_mastery: 当前掌握度 (0.0-1.0)。
            continuous_fail_counter: 连续失败计数器 C_fail。
            dt: 距上次评估的时间间隔（归一化单位）。

        Returns:
            (updated_mastery, mastery_delta, pid_output, pid_error, decision, gate):
              - updated_mastery: 更新后的掌握度。
              - mastery_delta: 掌握度变化量。
              - pid_output: PID 控制输出 u(t)。
              - pid_error: PID 跟踪误差 e(t)。
              - decision: 重寻路决策。
              - gate: 更新后的闸门状态。
        """
        # ---- 计算加权有效表现 ----
        # 综合答题正确率和代码通过率
        if cleaned.raw.code_pass_rate > 0 or cleaned.raw.total_attempts > 1:
            # 有编程题时取加权平均
            weighted_performance = (
                0.6 * cleaned.effective_correctness
                + 0.4 * cleaned.effective_code_pass
            )
        else:
            weighted_performance = cleaned.effective_correctness

        # 若无效数据（挂机），不更新掌握度
        if not cleaned.is_valid:
            return (
                current_mastery, 0.0, 0.0, 0.0,
                ReplanDecision.MAINTAIN,
                self._gates.get(node_id, PIDReplanGate(node_id=node_id)),
            )

        # ---- Layer 1: PID 平滑的掌握度更新 ----
        # 核心逻辑：
        #   performance_gap = weighted_performance - current_mastery
        #   若 gap > 0 → 学生表现超出预期 → mastery 应上升
        #   若 gap < 0 → 学生表现低于预期 → mastery 应下降
        #   PID 对 gap 进行平滑，抑制单次突变噪音
        #
        #   PID 配置: setpoint=0 (期望 gap=0, 即表现匹配掌握度)
        #            y(t) = performance_gap
        #            e(t) = 0 - gap = -gap
        #            u(t) = PID(e) → 平滑后的修正量
        performance_gap = weighted_performance - current_mastery

        prev_pid_state = self._pid.get_state(node_id)

        pid_input = PIDStepInput(
            node_id=node_id,
            setpoint=0.0,  # 期望 gap=0
            current_mastery=performance_gap,  # y(t) = 实际 gap
            continuous_fail_counter=continuous_fail_counter,
            dt=dt,
            pid_state=prev_pid_state,
        )

        pid_result = self._pid.step(pid_input)

        # PID 误差: e = setpoint - y = 0 - gap = -gap
        # PID 输出: u(t) = 平滑后的修正方向与幅度
        pid_error = pid_result.error  # = -gap
        control_output = pid_result.control_output

        # 计算掌握度增量
        # 基础方向: gap > 0 → 应该增加 mastery
        # PID 输出 u(t) 提供平滑后的修正比例
        # raw_delta = sign(gap) * |u(t)| * alpha
        # 其中 alpha 是基础学习率
        alpha_base = 0.15  # 基础学习率
        if performance_gap >= 0:
            raw_delta = abs(performance_gap) * alpha_base * abs(control_output)
        else:
            raw_delta = performance_gap * alpha_base * abs(control_output)

        # 应用辅导阻碍系数
        friction = cleaned.friction_coefficient
        if friction > 1.0:
            raw_delta /= friction

        # 钳位增量
        mastery_delta = max(-0.25, min(0.25, raw_delta))

        # 计算新的掌握度
        updated_mastery = current_mastery + mastery_delta
        updated_mastery = max(0.0, min(1.0, updated_mastery))

        # ---- Layer 2: 重寻路闸门 (基于 mastery 的变化趋势) ----
        gate = self._ensure_gate(node_id)
        # 闸门跟踪当前 mastery 与目标的差距: target_error = 1.0 - updated_mastery
        # 若 mastery 下降 → target_error 上升 → Δe > 0 → 连续则触发
        target_error = 1.0 - updated_mastery
        decision = gate.record_control_value(target_error)

        # 若连续越界触发，设置决策并记录日志
        if decision == ReplanDecision.TRIGGER:
            # 不在这里重置闸门 — 由 Planner Node 消费后调用 reset()
            pass

        return (
            round(updated_mastery, 6),
            round(mastery_delta, 6),
            round(control_output, 6),
            round(target_error, 6),
            decision,
            gate,
        )

    def reset_gate(self, node_id: str) -> None:
        """重置指定节点的重寻路闸门（Planner Node 完成重寻路后调用）。"""
        if node_id in self._gates:
            self._gates[node_id].reset()

    def _ensure_gate(self, node_id: str) -> PIDReplanGate:
        """获取或创建指定节点的闸门。"""
        if node_id not in self._gates:
            self._gates[node_id] = PIDReplanGate(
                node_id=node_id,
                window_size=self._gate_config.window_size,
                stagnation_threshold=self._gate_config.stagnation_threshold,
                trigger_threshold=self._gate_config.trigger_threshold,
            )
        return self._gates[node_id]

    def get_gate(self, node_id: str) -> Optional[PIDReplanGate]:
        """查询指定节点的闸门状态（调试用）。"""
        return self._gates.get(node_id)

    def get_pid(self) -> PIDController:
        """获取底层 PID 控制器。"""
        return self._pid


# ============================================================================
# Evaluator Node — LangGraph Node 主函数
# ============================================================================

class EvaluatorNode:
    """LangGraph Evaluator Node — 评估控制节点。

    此节点在 LangGraph StateGraph 中被注册为一个 Node 函数。
    输入: EvaluatorInput (含 AgentState + BehaviorVector)
    输出: EvaluatorOutput (更新后的 AgentState + 评估结果)

    在 LangGraph 中注册方式:
        >>> graph.add_node("evaluator", evaluator_node)

    内部执行流程:
      1. 行为清洗 — BehaviorCleaner.clean(raw_behavior)
      2. PID 平滑 — PIDReplanController.evaluate(...)
      3. AgentState 更新 — 写回动态画像 & re_plan_triggered
      4. 返回 EvaluatorOutput
    """

    def __init__(
        self,
        pid_config: Optional[PIDConfig] = None,
        gate_config: Optional[GateConfig] = None,
    ) -> None:
        """初始化 Evaluator Node。

        Args:
            pid_config: PID 控制器配置。
            gate_config: 重寻路闸门配置。
        """
        self._cleaner = BehaviorCleaner()
        self._controller = PIDReplanController(pid_config, gate_config)

    @property
    def controller(self) -> PIDReplanController:
        return self._controller

    @property
    def cleaner(self) -> BehaviorCleaner:
        return self._cleaner

    # ------------------------------------------------------------------
    # LangGraph Node 调用签名
    # ------------------------------------------------------------------

    def __call__(self, inp: EvaluatorInput) -> EvaluatorOutput:
        """LangGraph Node 调用入口。

        标准调用方式:
            output = evaluator_node(EvaluatorInput(
                agent_state=state,
                raw_behavior=BehaviorVector(
                    answer_correctness=0.85, ...
                ),
            ))

        Args:
            inp: EvaluatorInput 结构体。

        Returns:
            EvaluatorOutput: 包含更新后 AgentState + 完整评估诊断。
        """
        return self.evaluate(inp)

    # ------------------------------------------------------------------
    # 核心评估逻辑
    # ------------------------------------------------------------------

    def evaluate(self, inp: EvaluatorInput) -> EvaluatorOutput:
        """执行完整的评估管线。

        Args:
            inp: 评估输入。

        Returns:
            EvaluatorOutput。
        """
        state = inp.agent_state
        raw = inp.raw_behavior
        node_id = raw.node_id or state.current_node_id or "unknown"
        diagnostics: Dict[str, Any] = {}

        # ---- Step 1: 行为清洗 ----
        cleaned = self._cleaner.clean(raw)
        diagnostics["anomaly_type"] = cleaned.anomaly.anomaly_type.value
        diagnostics["anomaly_confidence"] = cleaned.anomaly.confidence
        diagnostics["friction_coefficient"] = cleaned.friction_coefficient

        # ---- Step 2: 获取当前掌握度 ----
        dp = state.dynamic_profile
        current_mastery = dp.knowledge_mastery.get(node_id, 0.5)
        c_fail = dp.continuous_fail_counter

        # ---- Step 3: PID 平滑评估 ----
        updated_mastery, delta, pid_out, pid_err, decision, gate = (
            self._controller.evaluate(
                node_id=node_id,
                cleaned=cleaned,
                current_mastery=current_mastery,
                continuous_fail_counter=c_fail,
                dt=1.0,
            )
        )

        diagnostics["pid_output"] = pid_out
        diagnostics["pid_error"] = pid_err
        diagnostics["consecutive_out_of_bounds"] = gate.consecutive_out_of_bounds
        diagnostics["replan_decision"] = decision.value

        # ---- Step 4: 更新 AgentState ----

        # 4a. 更新掌握度
        dp.knowledge_mastery[node_id] = updated_mastery

        # 4b. 更新 latest_behavior（保留加分项字段）
        # 从旧 latest_behavior 中保留 tutor_query（不入 Evaluator 处理范围）
        prev_lb = state.latest_behavior
        state.latest_behavior = LatestBehavior(
            node_id=node_id,
            correctness=cleaned.effective_correctness,
            time_spent_ratio=raw.time_spent_ratio,
            error_types=self._classify_errors(cleaned, raw),
            resource_feedback={},
            help_request_count=raw.help_request_count,
            # 保留加分项字段 (Tutor Agent / Assessment)
            tutor_query=getattr(prev_lb, "tutor_query", None) if prev_lb else None,
            accuracy_rate=getattr(prev_lb, "accuracy_rate", cleaned.effective_correctness) if prev_lb else cleaned.effective_correctness,
            code_pass_rate=getattr(prev_lb, "code_pass_rate", raw.code_pass_rate) if prev_lb else raw.code_pass_rate,
            duration_ratio=getattr(prev_lb, "duration_ratio", raw.time_spent_ratio) if prev_lb else raw.time_spent_ratio,
        )

        # 4c. 更新连续失败计数器 C_fail
        if cleaned.effective_correctness < 0.5 and cleaned.is_valid:
            dp.continuous_fail_counter += 1
        else:
            if cleaned.is_valid:
                dp.continuous_fail_counter = max(0, dp.continuous_fail_counter - 1)

        diagnostics["c_fail_updated"] = dp.continuous_fail_counter

        # 4d. 更新错误类型分布（指数移动平均）
        self._update_error_distribution(dp, cleaned, raw)

        # 4e. 重寻路闸门
        if decision == ReplanDecision.TRIGGER:
            state.trigger_replan()
            diagnostics["replan_triggered"] = True
            # 重置闸门，等待 Planner 消费
            self._controller.reset_gate(node_id)
        else:
            # 确保维持时不清除已有的 re_plan_triggered
            # （如果是 PENDING 状态，保留 False 等待下次判定）
            if decision == ReplanDecision.MAINTAIN:
                state.clear_replan()

        # 4f. 递增迭代轮次
        state.iteration += 1

        # ---- Step 5: 组装输出 ----
        return EvaluatorOutput(
            agent_state=state,
            cleaned_behavior=cleaned,
            updated_mastery=updated_mastery,
            mastery_delta=delta,
            pid_control_output=pid_out,
            pid_error=pid_err,
            replan_decision=decision,
            anomaly_detected=cleaned.anomaly.anomaly_type != AnomalyType.NORMAL,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_errors(
        cleaned: CleanedBehavior, raw: BehaviorVector
    ) -> List[str]:
        """根据行为特征推断错误类型分类。"""
        errors: List[str] = []
        correctness = cleaned.effective_correctness
        help_count = raw.help_request_count
        time_ratio = raw.time_spent_ratio

        if correctness < 0.4:
            errors.append("logic_flaw")
        if raw.code_pass_rate < 0.3 and raw.code_pass_rate > 0.0:
            errors.append("syntax_error")
        if correctness < 0.6 and time_ratio > 2.0:
            errors.append("boundary_miss")
        if help_count > 3:
            errors.append("logic_flaw")  # 高频求助 → 逻辑理解不足
        if not errors:
            errors.append("boundary_miss")  # 默认为边界疏忽

        return errors

    @staticmethod
    def _update_error_distribution(
        dp: Any, cleaned: CleanedBehavior, raw: BehaviorVector
    ) -> None:
        """使用指数移动平均 (EMA) 更新错误类型分布。

        EMA 公式: new_value = α * observed + (1-α) * old_value, α = 0.3
        """
        alpha = 0.3
        errors = EvaluatorNode._classify_errors(cleaned, raw)
        etd = dp.error_type_distribution

        observed = {"logic_flaw": 0.0, "syntax_error": 0.0, "boundary_miss": 0.0}
        for e in errors:
            if e in observed:
                observed[e] = 1.0 / len(errors) if errors else 0.33

        etd.logic_flaw = alpha * observed["logic_flaw"] + (1 - alpha) * etd.logic_flaw
        etd.syntax_error = alpha * observed["syntax_error"] + (1 - alpha) * etd.syntax_error
        etd.boundary_miss = alpha * observed["boundary_miss"] + (1 - alpha) * etd.boundary_miss

        # 归一化
        etd_norm = etd.normalize()
        etd.logic_flaw = etd_norm.logic_flaw
        etd.syntax_error = etd_norm.syntax_error
        etd.boundary_miss = etd_norm.boundary_miss


# ============================================================================
# 工厂函数: 创建 Evaluator Node 实例
# ============================================================================

def create_evaluator_node(
    pid_config: Optional[PIDConfig] = None,
    gate_config: Optional[GateConfig] = None,
) -> EvaluatorNode:
    """工厂函数 — 创建 Evaluator Node 实例。

    便捷创建方式，等价于 EvaluatorNode(pid_config, gate_config)。

    Args:
        pid_config: PID 控制器配置。
        gate_config: 重寻路闸门配置。

    Returns:
        EvaluatorNode 实例。

    使用示例:
        >>> node = create_evaluator_node()
        >>> output = node(EvaluatorInput(
        ...     agent_state=state,
        ...     raw_behavior=BehaviorVector(answer_correctness=0.85),
        ... ))
        >>> # 在 LangGraph 中注册:
        >>> # graph.add_node("evaluator", node)
    """
    return EvaluatorNode(pid_config, gate_config)
