# -*- coding: utf-8 -*-
"""
Profiler Node — LangGraph 画像演进大脑
=======================================

本节点是 LangGraph StateGraph 中的用户画像演进控制节点，在 Evaluator
之后执行，负责根据评估反馈持续更新用户的两类画像维度：

1. 慢变维度 (Slow-varying) — 学习风格偏好
   - 使用 Multi-Armed Bandit (MAB) 汤普森采样 (Thompson Sampling)
   - 三个臂 (Arms): visual / textual / practical
   - 每个臂维护独立 Beta(α, β) 分布
   - 每次推送资源时从各 Beta 中随机采样，取最大值决定推送风格
   - 根据 Evaluator 反馈信号增量更新 α / β

2. 快变维度 (Fast-varying) — 知识掌握度
   - 结合艾宾浩斯遗忘曲线对知识点进行时变衰减更新
   - 遗忘曲线: m(t) = m_0 · exp(-λ · Δt)
   - 连续失败 ≥ 3 次时触发硬切换干预

3. 干预门控 (Intervention Gate)
   - C_fail ≥ 3 → 强制风格切换（排除当前风格，选择次优伯仲）
   - 最低掌握度保底: max(m_decayed, 0.15)

依赖声明：
  NumPy 用于 Beta 分布采样与随机数生成。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import math
import time as _time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..state.agent_state import (
    AgentState,
    StaticProfile,
    DynamicProfile,
    CognitiveStyleDistribution,
    ErrorTypeDistribution,
    KnowledgeMasteryRecord,
)


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class ProfilerInput(BaseModel):
    """Profiler Node 的输入 — 对接 LangGraph StateGraph。"""

    agent_state: AgentState = Field(..., description="当前全局 AgentState")
    # Evaluator 反馈信号
    evaluator_mastery_delta: float = Field(
        default=0.0, description="Evaluator 计算的掌握度增量 Δm"
    )
    evaluator_pid_error: float = Field(
        default=0.0, description="Evaluator 的 PID 误差 e(t)"
    )
    resource_style_delivered: Optional[str] = Field(
        default=None, pattern=r"^(visual|textual|practical)$",
        description="上一轮推送时使用的资源风格"
    )
    # 时间戳
    current_timestamp: float = Field(
        default_factory=lambda: _time.time(),
        description="当前 Unix 时间戳（用于遗忘衰减）"
    )
    node_id: str = Field(default="", description="当前知识点 ID")


class StyleProfileResult(BaseModel):
    """风格画像的汤普森采样结果。"""

    selected_style: str = Field(..., description="本轮被选中的推送风格")
    sample_values: Dict[str, float] = Field(
        default_factory=dict,
        description="各风格本轮 Beta 采样值"
    )
    distribution_params: Dict[str, Tuple[float, float]] = Field(
        default_factory=dict,
        description="各风格当前的 (α, β) 参数"
    )
    intervention_triggered: bool = Field(
        default=False, description="是否触发了硬切换干预"
    )


class ForgettingCurveResult(BaseModel):
    """遗忘曲线衰减结果。"""

    mastery_before: float = Field(..., description="衰减前的掌握度")
    mastery_after: float = Field(..., description="衰减后的掌握度")
    elapsed_hours: float = Field(default=0.0, description="距上次更新的时间（小时）")
    decay_factor: float = Field(default=1.0, ge=0.0, le=1.0, description="衰减因子")
    memory_strength: float = Field(default=1.0, description="当前记忆强度系数 S")


class ProfilerOutput(BaseModel):
    """Profiler Node 的输出 — 将更新写回 AgentState。"""

    agent_state: AgentState = Field(..., description="更新后的全局 AgentState")
    style_result: StyleProfileResult = Field(..., description="风格采样结果")
    forgetting_result: Optional[ForgettingCurveResult] = Field(
        default=None, description="遗忘衰减结果 (当前节点有时提供)"
    )
    recommended_resource_style: str = Field(
        default="textual", description="推荐给 Generator 的资源推送风格"
    )
    intervention_active: bool = Field(
        default=False, description="硬切换干预是否激活"
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict, description="诊断信息"
    )


# ============================================================================
# 多臂老虎机 汤普森采样器 (MAB Thompson Sampling)
# ============================================================================

class ThompsonSampler:
    """Multi-Armed Bandit 汤普森采样器。

    三个臂对应三种认知风格:
      - Arm 0: visual   (视觉型)
      - Arm 1: textual  (文本型)
      - Arm 2: practical (实践型)

    每个臂维护 Beta(α, β) 分布。
    α = 成功次数 + 1 (先验 pseudo-count)
    β = 失败次数 + 1

    采样策略:
      1. 从每个臂的 Beta(α, β) 中随机采样一个值
      2. 选择采样值最大的臂
      3. 获得用户反馈 (reward ∈ [0, 1]) 后更新该臂的 α 或 β

    奖励函数:
      reward = effective_correctness (来自 Evaluator 清洗后的有效正确率)
      若 reward ≥ 0.6 → 成功 → α += reward
      若 reward < 0.6 → 失败 → β += (1 - reward)
    """

    ARM_NAMES: List[str] = ["visual", "textual", "practical"]
    SUCCESS_THRESHOLD: float = 0.6

    def __init__(self, rng: Optional[np.random.Generator] = None) -> None:
        """初始化汤普森采样器。

        Args:
            rng: NumPy 随机数生成器 (可注入以支持可复现测试)。
        """
        self._rng = rng or np.random.default_rng()
        # Beta 参数: {style_name: (alpha, beta)}
        self._params: Dict[str, Tuple[float, float]] = {
            "visual": (1.0, 1.0),
            "textual": (1.0, 1.0),
            "practical": (1.0, 1.0),
        }

    # ------------------------------------------------------------------
    # 参数管理
    # ------------------------------------------------------------------

    def set_params(self, style: str, alpha: float, beta: float) -> None:
        """设置指定风格的 Beta 参数。"""
        if style not in self._params:
            raise ValueError(f"未知风格: {style}")
        self._params[style] = (max(0.01, alpha), max(0.01, beta))

    def get_params(self, style: str) -> Tuple[float, float]:
        """获取指定风格的 (α, β)。"""
        return self._params.get(style, (1.0, 1.0))

    def load_from_cognitive_distribution(self, csd: CognitiveStyleDistribution) -> None:
        """从 AgentState 的 CognitiveStyleDistribution 加载先验参数。"""
        self._params["visual"] = (csd.visual_alpha, csd.visual_beta)
        self._params["textual"] = (csd.textual_alpha, csd.textual_beta)
        self._params["practical"] = (csd.practical_alpha, csd.practical_beta)

    def save_to_cognitive_distribution(self) -> CognitiveStyleDistribution:
        """将当前参数写回 CognitiveStyleDistribution。"""
        return CognitiveStyleDistribution(
            visual_alpha=self._params["visual"][0],
            visual_beta=self._params["visual"][1],
            textual_alpha=self._params["textual"][0],
            textual_beta=self._params["textual"][1],
            practical_alpha=self._params["practical"][0],
            practical_beta=self._params["practical"][1],
        )

    # ------------------------------------------------------------------
    # 核心采样
    # ------------------------------------------------------------------

    def sample(self) -> Tuple[str, Dict[str, float]]:
        """执行一轮汤普森采样。

        Returns:
            (selected_style, sample_values):
              - selected_style: 被选中的风格名称
              - sample_values: 各风格的采样值字典
        """
        samples: Dict[str, float] = {}
        for name in self.ARM_NAMES:
            alpha, beta = self._params[name]
            # NumPy Beta 采样
            samples[name] = float(self._rng.beta(alpha, beta))

        # 选择最大值
        best_style = max(samples, key=samples.get)
        return best_style, samples

    def sample_excluding(
        self, excluded_styles: List[str]
    ) -> Tuple[str, Dict[str, float]]:
        """汤普森采样，排除指定风格（用于硬切换干预）。

        Args:
            excluded_styles: 要排除的风格名称列表。

        Returns:
            (selected_style, sample_values)。
        """
        samples: Dict[str, float] = {}
        excluded_set = set(excluded_styles)

        for name in self.ARM_NAMES:
            if name in excluded_set:
                samples[name] = -1.0  # 强制排除
            else:
                alpha, beta = self._params[name]
                samples[name] = float(self._rng.beta(alpha, beta))

        # 从非排除臂中选择最大值
        eligible = {k: v for k, v in samples.items() if k not in excluded_set}
        if not eligible:
            # 所有风格都被排除 → 回退到全量采样
            return self.sample()

        best_style = max(eligible, key=eligible.get)
        return best_style, samples

    # ------------------------------------------------------------------
    # 奖励更新
    # ------------------------------------------------------------------

    def update(
        self, style: str, reward: float
    ) -> Tuple[float, float]:
        """根据反馈奖励更新指定风格的 Beta 参数。

        更新规则:
          - reward ≥ SUCCESS_THRESHOLD → α += reward (成功计数增加)
          - reward < SUCCESS_THRESHOLD → β += (1 - reward) (失败计数增加)

        增量幅度与 reward 值成比例（而非二元的 ±1），
        使高置信度的反馈产生更大的参数更新。

        Args:
            style: 被更新的风格。
            reward: 奖励信号 [0.0, 1.0] (来自 Evaluator 的有效正确率)。

        Returns:
            更新后的 (α, β)。
        """
        if style not in self._params:
            raise ValueError(f"未知风格: {style}")

        alpha, beta = self._params[style]

        if reward >= self.SUCCESS_THRESHOLD:
            alpha += reward
        else:
            beta += (1.0 - reward)

        # 防止参数退化到零
        alpha = max(0.01, alpha)
        beta = max(0.01, beta)

        self._params[style] = (alpha, beta)
        return (alpha, beta)

    def get_expected_rewards(self) -> Dict[str, float]:
        """计算各臂的期望奖励 E[Beta(α, β)] = α / (α + β)。"""
        means: Dict[str, float] = {}
        for name in self.ARM_NAMES:
            a, b = self._params[name]
            means[name] = a / (a + b) if (a + b) > 0 else 0.5
        return means


# ============================================================================
# 艾宾浩斯遗忘曲线引擎
# ============================================================================

class EbbinghausForgettingEngine:
    """艾宾浩斯遗忘曲线驱动的知识掌握度时变衰减引擎。

    遗忘曲线公式:
      m(t) = m_0 · exp(-λ · Δt)

    其中:
      - m_0:   最近一次记录的掌握度
      - λ:     遗忘速率 (由记忆强度 S 决定: λ = 1 / S)
      - Δt:    距上次更新的时间间隔（小时）
      - S:     记忆强度系数（随复习次数递增）

    记忆强度更新:
      - 每次成功交互: S *= 1.5 (记忆力增强)
      - 每次失败交互: S *= 0.8 (记忆力减弱)
      - S 钳位到 [0.5, 20.0]

    参考:
      Ebbinghaus, H. (1885). Über das Gedächtnis.
      Murre, J. M. J., & Dros, J. (2015). Replication and Analysis of
        Ebbinghaus' Forgetting Curve. PLOS ONE.
    """

    # 遗忘速率范围
    MIN_STRENGTH: float = 0.5
    MAX_STRENGTH: float = 20.0
    # 基础遗忘半衰期对应 S ≈ 24 (约 24 小时半衰)
    DEFAULT_STRENGTH: float = 10.0
    # 复习增益
    SUCCESS_STRENGTH_MULT: float = 1.5
    FAILURE_STRENGTH_MULT: float = 0.8
    # 最低掌握度保底
    MASTERY_FLOOR: float = 0.15

    def __init__(self) -> None:
        # 每个知识点的记忆强度
        self._strengths: Dict[str, float] = {}

    def get_strength(self, node_id: str) -> float:
        """获取指定知识点的记忆强度。"""
        return self._strengths.get(node_id, self.DEFAULT_STRENGTH)

    def set_strength(self, node_id: str, strength: float) -> None:
        """设置记忆强度（钳位到合法范围）。"""
        self._strengths[node_id] = max(
            self.MIN_STRENGTH,
            min(self.MAX_STRENGTH, strength),
        )

    def apply_decay(
        self,
        node_id: str,
        mastery: float,
        last_updated_ts: float,
        current_ts: float,
    ) -> ForgettingCurveResult:
        """对指定知识点的掌握度应用艾宾浩斯遗忘衰减。

        Args:
            node_id: 知识点 ID。
            mastery: 当前掌握度 m_0。
            last_updated_ts: 上次更新的 Unix 时间戳。
            current_ts: 当前时间戳。

        Returns:
            ForgettingCurveResult。
        """
        elapsed_seconds = max(0.0, current_ts - last_updated_ts)
        elapsed_hours = elapsed_seconds / 3600.0

        strength = self.get_strength(node_id)
        # λ = 1 / S (记忆越强，遗忘越慢)
        lambd = 1.0 / strength if strength > 0 else 1.0

        # m(t) = m_0 · exp(-λ · Δt)
        decay_factor = math.exp(-lambd * elapsed_hours)
        decayed_mastery = mastery * decay_factor

        # 最低保底
        decayed_mastery = max(self.MASTERY_FLOOR, decayed_mastery)

        return ForgettingCurveResult(
            mastery_before=round(mastery, 6),
            mastery_after=round(decayed_mastery, 6),
            elapsed_hours=round(elapsed_hours, 2),
            decay_factor=round(decay_factor, 6),
            memory_strength=round(strength, 4),
        )

    def update_strength(
        self, node_id: str, reward: float
    ) -> float:
        """根据交互反馈更新记忆强度。

        Args:
            node_id: 知识点 ID。
            reward: 奖励信号 [0.0, 1.0]。

        Returns:
            更新后的记忆强度。
        """
        current = self.get_strength(node_id)
        if reward >= ThompsonSampler.SUCCESS_THRESHOLD:
            new_strength = current * self.SUCCESS_STRENGTH_MULT
        else:
            new_strength = current * self.FAILURE_STRENGTH_MULT

        new_strength = max(self.MIN_STRENGTH, min(self.MAX_STRENGTH, new_strength))
        self._strengths[node_id] = new_strength
        return new_strength


# ============================================================================
# Profiler Node — LangGraph Node 主类
# ============================================================================

class ProfilerNode:
    """LangGraph Profiler Node — 画像演进大脑。

    在 LangGraph 中的注册方式:
        >>> graph.add_node("profiler", profiler_node)

    执行流程:
      1. 加载 AgentState 中的认知风格先验 → 初始化 MAB 采样器
      2. 执行汤普森采样 → 选择推送风格
      3. 根据 Evaluator 反馈更新 Beta 参数
      4. 检查 C_fail ≥ 3 → 硬切换干预
      5. 对当前知识点应用艾宾浩斯遗忘衰减
      6. 写回 AgentState
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """初始化 Profiler Node。

        Args:
            seed: 随机种子（用于可复现测试）。
        """
        self._rng = np.random.default_rng(seed)
        self._mab = ThompsonSampler(self._rng)
        self._forgetting = EbbinghausForgettingEngine()

        # 阶段跟踪: 记录每个风格被连续推送的轮次
        self._style_streak: Dict[str, int] = {"visual": 0, "textual": 0, "practical": 0}

    @property
    def mab(self) -> ThompsonSampler:
        return self._mab

    @property
    def forgetting(self) -> EbbinghausForgettingEngine:
        return self._forgetting

    # ------------------------------------------------------------------
    # LangGraph Node 调用签名
    # ------------------------------------------------------------------

    def __call__(self, inp: ProfilerInput) -> ProfilerOutput:
        return self.profile(inp)

    # ------------------------------------------------------------------
    # 核心画像演进逻辑
    # ------------------------------------------------------------------

    def profile(self, inp: ProfilerInput) -> ProfilerOutput:
        """执行完整的画像演进管线。

        Args:
            inp: ProfilerInput 结构体。

        Returns:
            ProfilerOutput: 更新后的 AgentState + 画像诊断。
        """
        state = inp.agent_state
        node_id = inp.node_id or state.current_node_id or "unknown"
        diagnostics: Dict[str, Any] = {}
        intervention_active = False

        sp = state.static_profile
        dp = state.dynamic_profile

        # ---- Step 1: 从 AgentState 加载 Beta 先验 ----
        self._mab.load_from_cognitive_distribution(
            sp.cognitive_style_distribution
        )

        # ---- Step 2: 检查硬切换干预条件 ----
        c_fail = dp.continuous_fail_counter

        if c_fail >= 3 and inp.resource_style_delivered:
            # 触发硬切换: 排除当前风格，强制选择次优风格
            current_style = inp.resource_style_delivered
            intervention_active = True
            selected_style, sample_values = self._mab.sample_excluding(
                excluded_styles=[current_style]
            )
            diagnostics["intervention"] = (
                f"C_fail={c_fail} ≥ 3, 强制从 {current_style} 切换到 {selected_style}"
            )
            # 重置当前风格的连续推送计数
            self._style_streak[current_style] = 0
        else:
            # 正常汤普森采样
            selected_style, sample_values = self._mab.sample()

        # ---- Step 3: 根据 Evaluator 反馈更新 Beta 参数 ----
        if inp.resource_style_delivered and inp.evaluator_mastery_delta != 0.0:
            # 奖励信号: 基于 PID 误差的归一化
            # 误差越小 → 表现越好 → reward 越高
            reward = max(0.0, min(1.0, 1.0 - abs(inp.evaluator_pid_error)))
            self._mab.update(inp.resource_style_delivered, reward)
            diagnostics["mab_reward"] = round(reward, 4)
            diagnostics["mab_style_updated"] = inp.resource_style_delivered

            # 更新风格连续推送计数
            self._style_streak[inp.resource_style_delivered] += 1

        # ---- Step 4: 更新遗忘引擎的记忆强度 ----
        if inp.resource_style_delivered and inp.evaluator_mastery_delta != 0.0:
            reward = max(0.0, min(1.0, 1.0 - abs(inp.evaluator_pid_error)))
            new_strength = self._forgetting.update_strength(node_id, reward)
            diagnostics["memory_strength"] = round(new_strength, 4)

        # ---- Step 5: 对当前知识点应用遗忘衰减 ----
        forgetting_result: Optional[ForgettingCurveResult] = None

        if node_id and node_id in dp.knowledge_mastery:
            current_mastery = dp.knowledge_mastery[node_id]
            # 获取上次更新时间戳
            mastery_record = dp.knowledge_mastery_records.get(node_id)
            if mastery_record:
                import datetime
                try:
                    last_ts = datetime.datetime.fromisoformat(
                        mastery_record.last_updated
                    ).timestamp()
                except (ValueError, OSError):
                    last_ts = inp.current_timestamp - 3600  # 默认 1 小时前
            else:
                last_ts = inp.current_timestamp

            forgetting_result = self._forgetting.apply_decay(
                node_id=node_id,
                mastery=current_mastery,
                last_updated_ts=last_ts,
                current_ts=inp.current_timestamp,
            )

            # 写回衰减后的掌握度 + 保底检查
            decayed = forgetting_result.mastery_after

            # 若 C_fail ≥ 3 → 强制保底（不低于 MASTERY_FLOOR 且不低于当前值）
            if c_fail >= 3 and decayed < EbbinghausForgettingEngine.MASTERY_FLOOR * 2:
                decayed = max(decayed, EbbinghausForgettingEngine.MASTERY_FLOOR * 2)
                diagnostics["mastery_floor_enforced"] = True

            dp.knowledge_mastery[node_id] = decayed

            # 更新掌握度记录
            import datetime
            dp.knowledge_mastery_records[node_id] = KnowledgeMasteryRecord(
                node_id=node_id,
                mastery=decayed,
                last_updated=datetime.datetime.utcnow().isoformat(),
                interaction_count=(
                    mastery_record.interaction_count + 1
                    if mastery_record else 1
                ),
            )

        # ---- Step 6: 将 MAB 参数写回 AgentState ----
        sp.cognitive_style_distribution = (
            self._mab.save_to_cognitive_distribution()
        )

        # ---- Step 7: 构建 StyleProfileResult ----
        style_result = StyleProfileResult(
            selected_style=selected_style,
            sample_values=sample_values,
            distribution_params={
                name: self._mab.get_params(name)
                for name in ThompsonSampler.ARM_NAMES
            },
            intervention_triggered=intervention_active,
        )

        # ---- Step 8: 组装输出 ----
        state.recommended_resource_style = selected_style
        return ProfilerOutput(
            agent_state=state,
            style_result=style_result,
            forgetting_result=forgetting_result,
            recommended_resource_style=selected_style,
            intervention_active=intervention_active,
            diagnostics=diagnostics,
        )


# ============================================================================
# 工厂函数
# ============================================================================

def create_profiler_node(seed: Optional[int] = None) -> ProfilerNode:
    """创建 Profiler Node 实例。"""
    return ProfilerNode(seed=seed)
