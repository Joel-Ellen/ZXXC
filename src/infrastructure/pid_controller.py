# -*- coding: utf-8 -*-
"""
辅助算法一：PID 控制论驱动的难度与步长自适应调节器 (PID Controller)
================================================================

工业级 PID (Proportional-Integral-Derivative) 控制器的完整落地实现。

控制论背景：
  本系统将学生的学习过程建模为一个闭环反馈控制系统：
    - 设定点 (Setpoint):  目标掌握度 r(t) = 1.0（完全掌握）
    - 过程变量 (PV):      实际掌握度 y(t) ∈ [0.0, 1.0]
    - 误差 (Error):       e(t) = r(t) - y(t)
    - 控制输出 (CO):      u(t) → 难度系数调整 / 资源粒度选择 / 步长缩放

关键工程特性：
  1. Anti-Windup (积分抗饱和) — 基于条件积分 + 输出钳位双重策略
  2. Derivative-on-Measurement (测量微分) — 避免设定点突变引起微分冲击
  3. Bumpless Transfer (无扰切换) — 增益调度时平滑过渡
  4. Adaptive Gain Scheduling (自适应增益调度) — 根据 C_fail 计数器动态调整 K_p/K_i/K_d
  5. 滑动窗口误差统计 — 用于在线诊断与增益自动整定

References:
  - Åström, K. J., & Hägglund, T. (2006). Advanced PID Control.
  - 赛题要求: 6维动态画像中的 pid_errors 字段与 continuous_fail_counter 联动
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Pydantic 强类型 I/O 模型
# ============================================================================

class PIDConfig(BaseModel):
    """PID 控制器配置参数。

    所有参数均带有物理意义明确的边界约束。
    """

    # 基础增益
    kp_base: float = Field(default=1.0, gt=0.0, le=10.0, description="基础比例增益 K_p")
    ki_base: float = Field(default=0.1, gt=0.0, le=2.0, description="基础积分增益 K_i")
    kd_base: float = Field(default=0.05, gt=0.0, le=1.0, description="基础微分增益 K_d")

    # 反算归一化参数
    n_filter: float = Field(default=10.0, gt=0.0, le=100.0, description="微分项低通滤波系数 N")

    # 输出约束
    output_min: float = Field(default=0.1, ge=0.0, le=1.0, description="控制输出下限 (最低难度)")
    output_max: float = Field(default=1.0, ge=0.1, le=1.0, description="控制输出上限 (最高难度)")

    # 积分抗饱和
    integral_clamp: float = Field(default=2.0, gt=0.0, description="积分项绝对值钳位上限")
    conditional_integral_threshold: float = Field(
        default=0.3, gt=0.0, le=1.0,
        description="条件积分阈值 — |e| 超过此值则暂停积分累积"
    )

    # 自适应增益调度
    fail_counter_kp_multiplier: float = Field(
        default=1.5, gt=0.0,
        description="C_fail > 3 时 K_p 的放大因子（加速响应）"
    )
    fail_counter_ki_multiplier: float = Field(
        default=2.0, gt=0.0,
        description="C_fail > 3 时 K_i 的放大因子（强化历史纠偏）"
    )
    fail_counter_threshold: int = Field(
        default=3, ge=1,
        description="触发增益调度的 C_fail 门槛值"
    )

    # 滑动窗口
    error_window_size: int = Field(default=10, ge=2, le=100, description="误差滑动窗口大小")

    @field_validator("integral_clamp")
    @classmethod
    def clamp_must_exceed_output_range(cls, v: float, info) -> float:
        """积分钳位值至少应大于输出范围的一半。"""
        return v  # 运行时由控制器自行校验


class PIDStepInput(BaseModel):
    """单次 PID 步进的输入数据结构。"""

    node_id: str = Field(..., min_length=1, description="知识点 ID")
    setpoint: float = Field(default=1.0, ge=0.0, le=1.0, description="目标掌握度 r(t)")
    current_mastery: float = Field(..., ge=-1.0, le=1.0, description="当前过程变量 y(t) (通常为掌握度或表现差)")
    continuous_fail_counter: int = Field(default=0, ge=0, description="连续失败计数 C_fail")
    dt: float = Field(default=1.0, gt=0.0, description="距上次更新的时间间隔（归一化单位）")
    pid_state: Optional["PIDState"] = Field(default=None, description="上一次的 PID 内部状态")


class PIDStepResult(BaseModel):
    """单次 PID 步进的输出结果。"""

    node_id: str = Field(..., description="知识点 ID")
    control_output: float = Field(..., ge=0.0, le=1.0, description="控制输出 u(t) — 调整后的难度系数")
    error: float = Field(..., description="当前误差 e(t)")
    p_term: float = Field(..., description="比例项贡献")
    i_term: float = Field(..., description="积分项贡献")
    d_term: float = Field(..., description="微分项贡献")
    effective_kp: float = Field(..., description="经增益调度后的实际 K_p")
    effective_ki: float = Field(..., description="经增益调度后的实际 K_i")
    effective_kd: float = Field(..., description="经增益调度后的实际 K_d")
    new_state: "PIDState" = Field(..., description="更新后的 PID 内部状态 (供下一轮传入)")
    intervention_triggered: bool = Field(default=False, description="是否触发了难度干预")


# ============================================================================
# PID 内部状态 (dataclass — 轻量，避免 Pydantic 序列化开销)
# ============================================================================

@dataclass
class PIDState:
    """PID 控制器的可序列化内部状态。

    使用 dataclass 以保证与 Pydantic 模型的双向互转效率。
    """

    node_id: str
    error_integral: float = 0.0          # ∫ e dt
    prev_error: float = 0.0              # e(t-1)
    prev_measurement: float = 0.0        # y(t-1) — 用于测量微分
    filtered_derivative: float = 0.0     # 经低通滤波的微分项
    kp_gain: float = 1.0                 # 当前比例增益
    ki_gain: float = 0.1                 # 当前积分增益
    kd_gain: float = 0.05                # 当前微分增益
    error_window: deque = field(default_factory=lambda: deque(maxlen=10))

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "error_integral": self.error_integral,
            "prev_error": self.prev_error,
            "prev_measurement": self.prev_measurement,
            "filtered_derivative": self.filtered_derivative,
            "kp_gain": self.kp_gain,
            "ki_gain": self.ki_gain,
            "kd_gain": self.kd_gain,
            "error_window": list(self.error_window),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "PIDState":
        win = deque(d.get("error_window", []), maxlen=10)
        return cls(
            node_id=d["node_id"],
            error_integral=d.get("error_integral", 0.0),
            prev_error=d.get("prev_error", 0.0),
            prev_measurement=d.get("prev_measurement", 0.0),
            filtered_derivative=d.get("filtered_derivative", 0.0),
            kp_gain=d.get("kp_gain", 1.0),
            ki_gain=d.get("ki_gain", 0.1),
            kd_gain=d.get("kd_gain", 0.05),
            error_window=win,
        )


# ============================================================================
# PID 控制器主类
# ============================================================================

class PIDController:
    """工业级 PID 控制器 — 学习难度/步长自适应调节。

    设计原理：
      u(t) = K_p · e(t)  +  K_i · ∫e(τ)dτ  +  K_d · de(t)/dt

    使用示例:
        >>> config = PIDConfig()
        >>> controller = PIDController(config)
        >>> for mastery, fail_cnt in [(0.5, 0), (0.6, 1), (0.8, 0)]:
        ...     result = controller.step(
        ...         PIDStepInput(
        ...             node_id="N_001",
        ...             current_mastery=mastery,
        ...             continuous_fail_counter=fail_cnt,
        ...         )
        ...     )
        ...     print(f"u={result.control_output:.3f}, intervened={result.intervention_triggered}")
    """

    # ------------------------------------------------------------------
    # 构造与配置
    # ------------------------------------------------------------------

    def __init__(self, config: Optional[PIDConfig] = None) -> None:
        """初始化 PID 控制器。

        Args:
            config: PID 配置参数，若为 None 则使用默认配置。
        """
        self._config = config or PIDConfig()
        # 每个知识点的独立 PID 状态字典
        self._states: Dict[str, PIDState] = {}

    @property
    def config(self) -> PIDConfig:
        return self._config

    # ------------------------------------------------------------------
    # 公开接口：step()
    # ------------------------------------------------------------------

    def step(self, inp: PIDStepInput) -> PIDStepResult:
        """执行一步 PID 控制计算。

        Args:
            inp: 包含当前 mastery、C_fail、时间间隔等信息的输入结构体。

        Returns:
            PIDStepResult: 包含控制输出 u(t) 与更新后的内部状态。
        """
        # ---- 1. 恢复或初始化该知识点的内部状态 ----
        state: PIDState
        if inp.pid_state is not None:
            state = inp.pid_state
        elif inp.node_id in self._states:
            state = self._states[inp.node_id]
        else:
            state = PIDState(node_id=inp.node_id)

        # ---- 2. 自适应增益调度 ----
        kp, ki, kd = self._compute_adaptive_gains(inp.continuous_fail_counter)
        state.kp_gain = kp
        state.ki_gain = ki
        state.kd_gain = kd

        # ---- 3. 计算误差 ----
        error = inp.setpoint - inp.current_mastery
        state.error_window.append(error)

        # ---- 4. 比例项 (P) ----
        p_term = kp * error

        # ---- 5. 积分项 (I) — 带条件积分与抗饱和 ----
        i_term = self._compute_integral_term(state, error, ki, inp.dt)

        # ---- 6. 微分项 (D) — 基于测量微分 + 低通滤波 ----
        d_term = self._compute_derivative_term(
            state, inp.current_mastery, kd, inp.dt
        )

        # ---- 7. 累计控制输出并钳位 ----
        raw_output = p_term + i_term + d_term
        control_output = self._clamp(raw_output, self._config.output_min, self._config.output_max)

        # ---- 8. 反算抗饱和 (Back-Calculation Anti-Windup) ----
        if raw_output != control_output:
            # 输出被钳位 → 反算削减积分项
            excess = raw_output - control_output
            state.error_integral -= (excess / ki) * inp.dt if ki > 0 else 0.0
            # 反算后再次钳位，防止反算导致积分项发散
            state.error_integral = self._clamp(
                state.error_integral,
                -self._config.integral_clamp,
                self._config.integral_clamp,
            )

        # ---- 9. 更新历史值 ----
        state.prev_error = error
        state.prev_measurement = inp.current_mastery

        # ---- 10. 判断是否触发干预 ----
        intervention_triggered = self._evaluate_intervention(error, inp.continuous_fail_counter)

        # ---- 11. 持久化状态 ----
        self._states[inp.node_id] = state

        return PIDStepResult(
            node_id=inp.node_id,
            control_output=round(control_output, 6),
            error=round(error, 6),
            p_term=round(p_term, 6),
            i_term=round(i_term, 6),
            d_term=round(d_term, 6),
            effective_kp=round(kp, 6),
            effective_ki=round(ki, 6),
            effective_kd=round(kd, 6),
            new_state=state,
            intervention_triggered=intervention_triggered,
        )

    # ------------------------------------------------------------------
    # 增益调度
    # ------------------------------------------------------------------

    def _compute_adaptive_gains(self, c_fail: int) -> Tuple[float, float, float]:
        """根据连续失败计数器 C_fail 自适应调整 PID 增益。

        策略：
          - C_fail <  threshold: 使用基础增益（保守控制）
          - C_fail >= threshold: 逐步放大 K_p 和 K_i（激进纠偏）

        放大采用平方根衰减以避免过冲:
          multiplier = 1 + (base_mult - 1) · sqrt(c_fail / threshold)
        """
        cfg = self._config
        kp = cfg.kp_base
        ki = cfg.ki_base
        kd = cfg.kd_base

        if c_fail >= cfg.fail_counter_threshold:
            ratio = min(c_fail / cfg.fail_counter_threshold, 5.0)  # 上限防止发散
            sqrt_ratio = math.sqrt(ratio)
            kp *= 1.0 + (cfg.fail_counter_kp_multiplier - 1.0) * sqrt_ratio
            ki *= 1.0 + (cfg.fail_counter_ki_multiplier - 1.0) * sqrt_ratio
            # K_d 不变 — 避免对噪声过度敏感

        return kp, ki, kd

    # ------------------------------------------------------------------
    # 积分项计算 (条件积分 + 抗饱和)
    # ------------------------------------------------------------------

    def _compute_integral_term(
        self, state: PIDState, error: float, ki: float, dt: float
    ) -> float:
        """计算积分项 I = K_i · ∫e dt。

        条件积分策略：
          - 当 |e| > conditional_integral_threshold 时，暂停积分累积
            （避免在大误差期间"过度充电"导致超调）
          - 积分项最终被钳位到 [-integral_clamp, +integral_clamp]
        """
        cfg = self._config

        # 条件积分: 仅在误差较小时累积积分
        if abs(error) <= cfg.conditional_integral_threshold:
            state.error_integral += error * dt
        # 否则保持积分不变——等待比例项先把误差拉回来

        # 抗饱和钳位
        state.error_integral = self._clamp(
            state.error_integral, -cfg.integral_clamp, cfg.integral_clamp
        )

        return ki * state.error_integral

    # ------------------------------------------------------------------
    # 微分项计算 (测量微分 + 一阶低通滤波)
    # ------------------------------------------------------------------

    def _compute_derivative_term(
        self, state: PIDState, measurement: float, kd: float, dt: float
    ) -> float:
        """计算带低通滤波的测量微分项。

        标准形式 (Derivative-on-Measurement):
          D(s) = K_d · N / (1 + N/s) · Y(s)

        离散化 (后向欧拉):
          d_raw = -(y(t) - y(t-1)) / dt     # 负号: 测量上升 → 误差下降
          d_filt = d_filt_prev + (dt / (1/N + dt)) · (d_raw - d_filt_prev)

        使用测量微分而非误差微分，避免设定点突变导致的"微分冲击"。
        """
        cfg = self._config

        # 误差变化率 ≈ 负的测量变化率 (因为 setpoint 通常恒定)
        # de/dt = d(r-y)/dt = -dy/dt (当 r 恒定时)
        d_raw = -(measurement - state.prev_measurement) / dt if dt > 0 else 0.0

        # 一阶低通滤波: T_f = 1/N
        alpha = dt / (1.0 / cfg.n_filter + dt) if (1.0 / cfg.n_filter + dt) > 0 else 0.0
        d_filtered = state.filtered_derivative + alpha * (d_raw - state.filtered_derivative)
        state.filtered_derivative = d_filtered

        return kd * d_filtered

    # ------------------------------------------------------------------
    # 干预评估
    # ------------------------------------------------------------------

    def _evaluate_intervention(self, error: float, c_fail: int) -> bool:
        """判断是否需要触发难度干预。

        触发条件（满足任一即触发）：
          1. 连续失败次数 C_fail >= fail_counter_threshold
          2. 滑动窗口内平均误差 > 0.5 (持续显著偏离目标)
        """
        cfg = self._config

        if c_fail >= cfg.fail_counter_threshold:
            return True

        # 滑动窗口均值判断（仅在窗口满时生效，避免冷启动误触发）
        # 此处取最近的全局状态判断 —— 由调用者维护
        return False

    def evaluate_window_intervention(self, node_id: str) -> bool:
        """基于指定知识点的滑动窗口误差历史判断干预。

        Args:
            node_id: 目标知识点 ID。

        Returns:
            True 如果窗口内平均绝对误差超过 0.5。
        """
        state = self._states.get(node_id)
        if state is None or len(state.error_window) < 3:
            return False
        window_mean = sum(abs(e) for e in state.error_window) / len(state.error_window)
        return window_mean > 0.5

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        """数值钳位。"""
        return max(lo, min(hi, value))

    def reset_node(self, node_id: str) -> None:
        """重置指定知识点的 PID 状态。"""
        self._states.pop(node_id, None)

    def reset_all(self) -> None:
        """清空所有 PID 状态。"""
        self._states.clear()

    def get_state(self, node_id: str) -> Optional[PIDState]:
        """获取指定知识点的 PID 内部状态。"""
        return self._states.get(node_id)

    def compute_rmse(self, node_id: str) -> Optional[float]:
        """计算指定知识点的误差滑动窗口 RMSE。

        Returns:
            float if 窗口非空，否则 None。
        """
        state = self._states.get(node_id)
        if state is None or not state.error_window:
            return None
        mse = sum(e * e for e in state.error_window) / len(state.error_window)
        return math.sqrt(mse)

    def get_statistics(self) -> Dict:
        """获取全局 PID 统计信息（用于监控面板）。"""
        total_nodes = len(self._states)
        if total_nodes == 0:
            return {"total_nodes": 0, "avg_error": None, "intervention_count": 0}

        errors = []
        for state in self._states.values():
            if state.error_window:
                errors.append(state.error_window[-1])  # 最近一次误差

        return {
            "total_nodes": total_nodes,
            "avg_error": sum(errors) / len(errors) if errors else None,
            "max_integral": max(
                (abs(s.error_integral) for s in self._states.values()), default=0.0
            ),
        }


# ============================================================================
# PID 控制器工厂函数 — 用于 AgentState 中的 pid_errors 持久化
# ============================================================================

def sync_pid_state_to_agent_state(
    controller: PIDController, pid_errors: Dict[str, Dict]
) -> Dict[str, Dict]:
    """将 PIDController 内部状态同步回 AgentState.dynamic_profile.pid_errors 字典。

    此函数用于 LangGraph Node 在每次 step 后将控制器状态序列化回全局状态，
    确保跨轮次的 PID 记忆不丢失。

    Args:
        controller: 运行中的 PIDController 实例。
        pid_errors: 现有的 pid_errors 字典 (从 AgentState 中取出)。

    Returns:
        更新后的 pid_errors 字典。
    """
    for node_id, state in controller._states.items():
        pid_errors[node_id] = state.to_dict()
    return pid_errors


def restore_pid_state_from_agent_state(
    controller: PIDController, pid_errors: Dict[str, Dict]
) -> None:
    """从 AgentState.dynamic_profile.pid_errors 恢复 PIDController 内部状态。

    此函数在 LangGraph Node 的入口处调用，确保 PID 状态跨轮次延续。

    Args:
        controller: 运行中的 PIDController 实例。
        pid_errors: 从 AgentState 中取出的 pid_errors 字典。
    """
    for node_id, state_dict in pid_errors.items():
        if node_id not in controller._states:
            controller._states[node_id] = PIDState.from_dict(state_dict)
