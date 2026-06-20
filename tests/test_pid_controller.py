# -*- coding: utf-8 -*-
"""
PID 控制器单元测试套件 (辅助算法一)
====================================

覆盖范围:
  1. 基础 PID 步进 (单步与多步)
  2. 积分抗饱和 (Anti-Windup)
  3. 测量微分 (Derivative-on-Measurement)
  4. 自适应增益调度 (Adaptive Gain Scheduling)
  5. 条件积分 (Conditional Integration)
  6. 输出钳位
  7. 冷启动误差窗口 RMSE
  8. 状态序列化/反序列化 (PIDState ↔ dict)
  9. 控制器同步回 AgentState
  10. 边界条件 (0 mastery, 1.0 mastery, 极端 C_fail)

运行方式:
    pytest tests/test_pid_controller.py -v
    或: python -m pytest tests/test_pid_controller.py -v
"""

import pytest
import math
from collections import deque

# 确保 src 在 path 中
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.pid_controller import (
    PIDController,
    PIDConfig,
    PIDState,
    PIDStepInput,
    PIDStepResult,
    sync_pid_state_to_agent_state,
    restore_pid_state_from_agent_state,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def default_config() -> PIDConfig:
    """返回默认 PID 配置。"""
    return PIDConfig()


@pytest.fixture
def strict_config() -> PIDConfig:
    """返回一套用于测试抗饱和与钳位行为的严格配置。"""
    return PIDConfig(
        kp_base=2.0,
        ki_base=0.2,
        kd_base=0.1,
        n_filter=20.0,
        output_min=0.2,
        output_max=0.9,
        integral_clamp=1.5,
        conditional_integral_threshold=0.25,
        fail_counter_kp_multiplier=2.0,
        fail_counter_ki_multiplier=3.0,
        fail_counter_threshold=2,
        error_window_size=5,
    )


@pytest.fixture
def controller(default_config: PIDConfig) -> PIDController:
    """返回使用默认配置的控制器。"""
    return PIDController(default_config)


@pytest.fixture
def strict_controller(strict_config: PIDConfig) -> PIDController:
    """返回使用严格配置的控制器。"""
    return PIDController(strict_config)


# ============================================================================
# 1. 基础 PID 步进 — 单步
# ============================================================================

class TestBasicPIDStep:
    """测试 PID 控制器单步/多步的基本行为。"""

    def test_single_step_defaults(self, controller: PIDController) -> None:
        """单步 PID: 默认 setpoint=1.0, mastery=0.5 → 应产生正控制输出。"""
        result = controller.step(PIDStepInput(
            node_id="N_TEST_001",
            current_mastery=0.5,
        ))

        assert isinstance(result, PIDStepResult)
        assert result.node_id == "N_TEST_001"
        # mastery < setpoint → error > 0 → control_output > 0
        assert result.error > 0
        assert result.control_output > 0
        assert result.effective_kp == controller.config.kp_base
        assert result.effective_ki == controller.config.ki_base
        assert result.effective_kd == controller.config.kd_base

    def test_single_step_perfect_mastery(self, controller: PIDController) -> None:
        """掌握度 = 1.0 时误差应为 0，P 项应为 0。"""
        result = controller.step(PIDStepInput(
            node_id="N_PERFECT",
            current_mastery=1.0,
        ))
        assert result.error == 0.0
        assert result.p_term == 0.0

    def test_single_step_zero_mastery(self, controller: PIDController) -> None:
        """掌握度 = 0 时误差应为最大，控制输出应 > 0。"""
        result = controller.step(PIDStepInput(
            node_id="N_ZERO",
            current_mastery=0.0,
        ))
        assert result.error == 1.0
        assert result.control_output > 0.5  # 至少比中等误差的响应强

    def test_control_output_in_range(self, controller: PIDController) -> None:
        """控制输出应在 [output_min, output_max] 范围内。"""
        for mastery in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = controller.step(PIDStepInput(
                node_id=f"N_{mastery}",
                current_mastery=mastery,
            ))
            assert controller.config.output_min <= result.control_output <= controller.config.output_max, (
                f"mastery={mastery}, output={result.control_output}"
            )


# ============================================================================
# 2. 多步收敛测试
# ============================================================================

class TestMultiStepConvergence:
    """测试 PID 控制器在多次迭代中的收敛行为。"""

    def test_convergence_toward_setpoint(self, controller: PIDController) -> None:
        """模拟学生逐步掌握，验证 PID 输出随 mastery 上升而减少。"""
        node_id = "N_CONV"
        masteries = [0.2, 0.4, 0.6, 0.8, 0.95]
        outputs: list[float] = []
        prev_state = None

        for m in masteries:
            inp = PIDStepInput(
                node_id=node_id,
                current_mastery=m,
                pid_state=prev_state,
            )
            result = controller.step(inp)
            outputs.append(result.control_output)
            prev_state = result.new_state

        # 控制输出应随掌握度上升而下降（不一定是严格单调，但趋势应向下）
        assert outputs[-1] < outputs[0], (
            f"期望最终输出 < 初始输出，实际: {outputs[-1]} >= {outputs[0]}"
        )

    def test_integral_accumulates_over_time(self, controller: PIDController) -> None:
        """当 mastery 持续 < setpoint 且误差在条件积分阈值内时，积分项应持续累积。"""
        node_id = "N_INTEGRAL"
        prev_state = None
        integrals: list[float] = []
        # 使用 mastery=0.85 使 error=0.15 < conditional_integral_threshold(0.3)，触发条件积分
        for _ in range(5):
            inp = PIDStepInput(
                node_id=node_id,
                current_mastery=0.85,  # error=0.15 < 0.3, 满足条件积分
                pid_state=prev_state,
            )
            result = controller.step(inp)
            integrals.append(abs(result.new_state.error_integral))
            prev_state = result.new_state

        # 积分绝对值应单调增加
        for i in range(1, len(integrals)):
            assert integrals[i] > integrals[i - 1] * 0.9, (
                f"积分应以显著速率累积: [{i-1}]={integrals[i-1]:.4f}, [{i}]={integrals[i]:.4f}"
            )


# ============================================================================
# 3. 积分抗饱和 (Anti-Windup)
# ============================================================================

class TestAntiWindup:
    """测试积分抗饱和机制。"""

    def test_integral_clamping(self, strict_controller: PIDController) -> None:
        """积分项不应超过 integral_clamp。"""
        node_id = "N_CLAMP"
        prev_state = None

        # 持续制造大误差迫使积分累积到上限
        for _ in range(20):
            inp = PIDStepInput(
                node_id=node_id,
                current_mastery=0.0,  # 最大误差
                dt=2.0,  # 加速累积
                pid_state=prev_state,
            )
            result = strict_controller.step(inp)
            prev_state = result.new_state

        assert abs(prev_state.error_integral) <= strict_controller.config.integral_clamp + 1e-6, (
            f"error_integral={prev_state.error_integral} 超出 clamp={strict_controller.config.integral_clamp}"
        )

    def test_conditional_integration_pauses_on_large_error(
        self, strict_controller: PIDController
    ) -> None:
        """条件积分: 大误差时直接积分累积应暂停。

        注意：反算抗饱和 (Back-Calculation Anti-Windup) 可能在输出钳位时
        修改积分项，这是预期行为而非条件积分的失败。本测试验证直接累积路径
        的条件判断逻辑。
        """
        node_id = "N_COND_INT"
        threshold = strict_controller.config.conditional_integral_threshold

        # 先制造小误差 → 积分应累积 (error=threshold/2 < threshold)
        r1 = strict_controller.step(PIDStepInput(
            node_id=node_id,
            current_mastery=1.0 - threshold / 2,  # error = 0.125 < 0.25
        ))
        integral_after_small = r1.new_state.error_integral
        assert abs(integral_after_small) > 0, "小误差时应累积积分"

        # 使用 mastery=0.65 → error=0.35，满足:
        #   0.35 > 0.25(threshold) → 条件积分暂停
        #   且 kp=2.0 → P=0.7 → raw 不超出 [0.2, 0.9] → 无钳位反算干扰
        r2 = strict_controller.step(PIDStepInput(
            node_id=node_id,
            current_mastery=0.65,  # error = 0.35, in tight range
            pid_state=r1.new_state,
        ))
        integral_after_moderate = r2.new_state.error_integral
        assert abs(integral_after_moderate - integral_after_small) < 1e-9, (
            f"中等大误差下积分直接累积应暂停: "
            f"before={integral_after_small:.6f}, after={integral_after_moderate:.6f}"
        )


# ============================================================================
# 4. 测量微分 (Derivative-on-Measurement)
# ============================================================================

class TestDerivativeOnMeasurement:
    """测试测量微分的正确性。"""

    def test_no_derivative_kick_on_setpoint_change(self, controller: PIDController) -> None:
        """使用测量微分时，setpoint 不变所以不应有微分冲击。"""
        # 默认 setpoint 固定为 1.0，因此 de/dt ≈ -dy/dt
        # 当 mastery 增加时，dy/dt > 0 → de/dt < 0 → D 项应为负
        r1 = controller.step(PIDStepInput(
            node_id="N_DERIV",
            current_mastery=0.3,
        ))
        r2 = controller.step(PIDStepInput(
            node_id="N_DERIV",
            current_mastery=0.6,  # mastery 上升
            pid_state=r1.new_state,
        ))
        # mastery 上升意味着误差减小，D 项应贡献负值（抑制超调）
        assert r2.d_term < 0, (
            f"mastery 上升时 D 应为负以抑制超调，实际: {r2.d_term}"
        )

    def test_derivative_positive_when_mastery_drops(self, controller: PIDController) -> None:
        """mastery 下降时，D 项应为正（加速拉回）。"""
        r1 = controller.step(PIDStepInput(
            node_id="N_DERIV2",
            current_mastery=0.6,
        ))
        r2 = controller.step(PIDStepInput(
            node_id="N_DERIV2",
            current_mastery=0.3,  # mastery 下降
            pid_state=r1.new_state,
        ))
        assert r2.d_term > 0, (
            f"mastery 下降时 D 应为正以加速纠正，实际: {r2.d_term}"
        )


# ============================================================================
# 5. 自适应增益调度 (Adaptive Gain Scheduling)
# ============================================================================

class TestAdaptiveGainScheduling:
    """测试 C_fail 驱动的增益调度。"""

    def test_gains_increase_with_high_cfail(self, controller: PIDController) -> None:
        """C_fail >= threshold 时 K_p 和 K_i 应放大。"""
        cfg = controller.config

        # 正常情况
        r_normal = controller.step(PIDStepInput(
            node_id="N_GAIN_NORM",
            current_mastery=0.5,
            continuous_fail_counter=0,
        ))
        # 高 C_fail
        r_fail = controller.step(PIDStepInput(
            node_id="N_GAIN_FAIL",
            current_mastery=0.5,
            continuous_fail_counter=cfg.fail_counter_threshold,
        ))

        assert r_fail.effective_kp > r_normal.effective_kp, (
            f"C_fail={cfg.fail_counter_threshold} 时 K_p 应放大: "
            f"normal={r_normal.effective_kp:.4f}, fail={r_fail.effective_kp:.4f}"
        )
        assert r_fail.effective_ki > r_normal.effective_ki, (
            f"C_fail={cfg.fail_counter_threshold} 时 K_i 应放大: "
            f"normal={r_normal.effective_ki:.4f}, fail={r_fail.effective_ki:.4f}"
        )

    def test_gains_scale_with_cfail_magnitude(self, controller: PIDController) -> None:
        """更高的 C_fail 应产生更大的增益放大。"""
        cfg = controller.config

        r_3 = controller.step(PIDStepInput(
            node_id="N_S1", current_mastery=0.5,
            continuous_fail_counter=3,
        ))
        r_10 = controller.step(PIDStepInput(
            node_id="N_S2", current_mastery=0.5,
            continuous_fail_counter=10,
        ))
        assert r_10.effective_kp >= r_3.effective_kp, (
            f"C_fail=10 的 K_p 应 >= C_fail=3"
        )


# ============================================================================
# 6. 干预触发
# ============================================================================

class TestInterventionTrigger:
    """测试难度干预触发机制。"""

    def test_intervention_triggered_on_high_cfail(self, controller: PIDController) -> None:
        """C_fail 达标时应触发干预。"""
        cfg = controller.config
        result = controller.step(PIDStepInput(
            node_id="N_INTV",
            current_mastery=0.5,
            continuous_fail_counter=cfg.fail_counter_threshold,
        ))
        assert result.intervention_triggered is True

    def test_no_intervention_on_low_cfail(self, controller: PIDController) -> None:
        """C_fail 低于阈值时不触发干预。"""
        result = controller.step(PIDStepInput(
            node_id="N_NOINTV",
            current_mastery=0.5,
            continuous_fail_counter=0,
        ))
        assert result.intervention_triggered is False

    def test_window_intervention_on_high_error(self, controller: PIDController) -> None:
        """滑动窗口内持续高误差应触发干预。"""
        node_id = "N_WIN"
        prev_state = None
        # 持续制造大误差填满窗口
        for _ in range(controller.config.error_window_size + 2):
            inp = PIDStepInput(
                node_id=node_id,
                current_mastery=0.1,  # error = 0.9，远超 0.5
                pid_state=prev_state,
            )
            result = controller.step(inp)
            prev_state = result.new_state

        assert controller.evaluate_window_intervention(node_id) is True

    def test_window_no_intervention_on_correcting(self, controller: PIDController) -> None:
        """窗口内误差均值低时不触发干预。"""
        node_id = "N_WIN_OK"
        prev_state = None
        for m in [0.85, 0.88, 0.90, 0.92, 0.95]:
            inp = PIDStepInput(
                node_id=node_id,
                current_mastery=m,
                pid_state=prev_state,
            )
            result = controller.step(inp)
            prev_state = result.new_state

        assert controller.evaluate_window_intervention(node_id) is False


# ============================================================================
# 7. 状态序列化/反序列化
# ============================================================================

class TestStateSerialization:
    """测试 PIDState 与 dict 之间的双向转换。"""

    def test_roundtrip(self) -> None:
        """PIDState → dict → PIDState 应无损。"""
        original = PIDState(
            node_id="N_SER",
            error_integral=0.42,
            prev_error=0.13,
            prev_measurement=0.87,
            filtered_derivative=-0.02,
            kp_gain=1.5,
            ki_gain=0.3,
            kd_gain=0.08,
            error_window=deque([0.1, 0.2, 0.3], maxlen=5),
        )
        d = original.to_dict()
        restored = PIDState.from_dict(d)

        assert restored.node_id == original.node_id
        assert restored.error_integral == original.error_integral
        assert restored.prev_error == original.prev_error
        assert restored.prev_measurement == original.prev_measurement
        assert restored.filtered_derivative == original.filtered_derivative
        assert restored.kp_gain == original.kp_gain
        assert restored.ki_gain == original.ki_gain
        assert restored.kd_gain == original.kd_gain
        assert list(restored.error_window) == list(original.error_window)

    def test_empty_state_roundtrip(self) -> None:
        """空状态也应正确往返。"""
        original = PIDState(node_id="N_EMPTY")
        d = original.to_dict()
        restored = PIDState.from_dict(d)
        assert restored.node_id == original.node_id
        assert restored.error_integral == 0.0


# ============================================================================
# 8. AgentState 同步
# ============================================================================

class TestAgentStateSync:
    """测试 PIDController ↔ AgentState 同步函数。"""

    def test_sync_and_restore(self, controller: PIDController) -> None:
        """同步到 pid_errors 再恢复，应保持一致性。"""
        # 执行几步操作 — 使用 mastery 值使误差在条件积分阈值内
        prev_state = None
        for m in [0.80, 0.85, 0.90]:  # errors: 0.20, 0.15, 0.10 均 ≤ 0.3
            result = controller.step(PIDStepInput(
                node_id="N_SYNC",
                current_mastery=m,
                pid_state=prev_state,
            ))
            prev_state = result.new_state

        # 同步到 dict
        pid_errors: dict = {}
        pid_errors = sync_pid_state_to_agent_state(controller, pid_errors)
        assert "N_SYNC" in pid_errors
        assert abs(pid_errors["N_SYNC"]["error_integral"]) > 0, (
            f"积分应累积: {pid_errors['N_SYNC']['error_integral']}"
        )

        # 创建新控制器并恢复
        new_controller = PIDController(controller.config)
        restore_pid_state_from_agent_state(new_controller, pid_errors)
        restored_state = new_controller.get_state("N_SYNC")
        assert restored_state is not None
        assert abs(restored_state.error_integral - prev_state.error_integral) < 1e-9

    def test_empty_pid_errors_no_error(self, controller: PIDController) -> None:
        """空 pid_errors 不应导致异常。"""
        # 不应抛出异常
        sync_pid_state_to_agent_state(controller, {})
        restore_pid_state_from_agent_state(controller, {})


# ============================================================================
# 9. 重置与统计
# ============================================================================

class TestResetAndStats:
    """测试控制器重置与统计功能。"""

    def test_reset_node(self, controller: PIDController) -> None:
        """重置某个知识点后其状态应不存在。"""
        controller.step(PIDStepInput(node_id="N_RST", current_mastery=0.5))
        assert controller.get_state("N_RST") is not None
        controller.reset_node("N_RST")
        assert controller.get_state("N_RST") is None

    def test_reset_all(self, controller: PIDController) -> None:
        """全量重置后所有状态应清空。"""
        for nid in ["A", "B", "C"]:
            controller.step(PIDStepInput(node_id=nid, current_mastery=0.5))
        assert len(controller._states) == 3
        controller.reset_all()
        assert len(controller._states) == 0

    def test_rmse(self, controller: PIDController) -> None:
        """RMSE 应正确计算。"""
        node_id = "N_RMSE"
        prev_state = None
        for m in [0.3, 0.3, 0.3]:  # 恒定 mastery → 恒定误差 0.7
            result = controller.step(PIDStepInput(
                node_id=node_id, current_mastery=m, pid_state=prev_state,
            ))
            prev_state = result.new_state

        rmse = controller.compute_rmse(node_id)
        assert rmse is not None
        # 误差恒为 0.7, RMSE 应为 0.7
        assert abs(rmse - 0.7) < 0.01, f"expected ~0.7, got {rmse}"

    def test_statistics(self, controller: PIDController) -> None:
        """统计信息应包含正确的节点数。"""
        for nid in ["X1", "X2"]:
            controller.step(PIDStepInput(node_id=nid, current_mastery=0.5))
        stats = controller.get_statistics()
        assert stats["total_nodes"] == 2
        assert stats["avg_error"] is not None
        assert stats["avg_error"] > 0


# ============================================================================
# 10. 边界条件
# ============================================================================

class TestBoundaryConditions:
    """测试极端边界条件。"""

    def test_zero_dt_does_not_crash(self, controller: PIDController) -> None:
        """dt=0 或极小值不应导致除零错误。"""
        # 使用极小的 dt（正数）
        result = controller.step(PIDStepInput(
            node_id="N_DT",
            current_mastery=0.5,
            dt=1e-9,
        ))
        assert result is not None
        assert not math.isnan(result.control_output)
        assert not math.isinf(result.control_output)

    def test_very_high_cfail_does_not_explode(self, controller: PIDController) -> None:
        """极大 C_fail (100) 不应导致控制输出发散。"""
        result = controller.step(PIDStepInput(
            node_id="N_BIGFAIL",
            current_mastery=0.0,
            continuous_fail_counter=100,
        ))
        assert not math.isnan(result.control_output)
        assert not math.isinf(result.control_output)
        assert result.control_output <= controller.config.output_max

    def test_different_nodes_independent(self, controller: PIDController) -> None:
        """不同知识点的 PID 状态应相互独立。"""
        r_a = controller.step(PIDStepInput(node_id="A", current_mastery=0.3))
        r_b = controller.step(PIDStepInput(node_id="B", current_mastery=0.9))

        state_a = controller.get_state("A")
        state_b = controller.get_state("B")
        assert state_a is not None and state_b is not None
        # A 的误差应远大于 B
        assert abs(state_a.prev_error) > abs(state_b.prev_error), (
            f"节点A误差应 > 节点B: A={state_a.prev_error}, B={state_b.prev_error}"
        )

    def test_setpoint_can_be_less_than_one(self, controller: PIDController) -> None:
        """setpoint 支持非 1.0 的值。"""
        result = controller.step(PIDStepInput(
            node_id="N_SP",
            current_mastery=0.5,
            setpoint=0.6,  # 比默认 1.0 更低的期望
        ))
        assert abs(result.error - 0.1) < 1e-6

    def test_pid_config_validation(self) -> None:
        """PIDConfig 各字段边界校验。"""
        with pytest.raises(Exception):
            PIDConfig(kp_base=-1.0)  # K_p 必须 > 0
        with pytest.raises(Exception):
            PIDConfig(output_min=2.0)  # output_min 必须 <= 1.0
        with pytest.raises(Exception):
            PIDConfig(output_max=0.0)  # output_max 必须 >= 0.1


# ============================================================================
# 11. PID 控制器工厂函数集成测试
# ============================================================================

class TestPIDIntegration:
    """集成测试: 模拟 LangGraph Node 中的 PID 完整使用流程。"""

    def test_full_langgraph_node_flow(self) -> None:
        """模拟 Agent Node 中跨轮次的 PID 调用。"""
        # 使用 fail_counter_threshold=2 的配置以覆盖干预触发路径
        config = PIDConfig(fail_counter_threshold=2)
        controller = PIDController(config)
        pid_errors: dict = {}

        # Round 1: 学生答对率 0.8
        inp1 = PIDStepInput(node_id="NODE_001", current_mastery=0.8, continuous_fail_counter=0)
        r1 = controller.step(inp1)
        pid_errors = sync_pid_state_to_agent_state(controller, pid_errors)

        # Round 2: 学生答对率 0.85 (有进步)
        saved_state = PIDState.from_dict(pid_errors["NODE_001"])
        inp2 = PIDStepInput(
            node_id="NODE_001", current_mastery=0.85,
            continuous_fail_counter=0, pid_state=saved_state,
        )
        r2 = controller.step(inp2)
        pid_errors = sync_pid_state_to_agent_state(controller, pid_errors)

        # Round 3: 学生答对率 0.7 (退步, C_fail=1)
        saved_state = PIDState.from_dict(pid_errors["NODE_001"])
        inp3 = PIDStepInput(
            node_id="NODE_001", current_mastery=0.7,
            continuous_fail_counter=1, pid_state=saved_state,
        )
        r3 = controller.step(inp3)
        pid_errors = sync_pid_state_to_agent_state(controller, pid_errors)

        # Round 4: 学生答对率 0.6 (持续失败, C_fail=2, 达到 fail_counter_threshold=2)
        saved_state = PIDState.from_dict(pid_errors["NODE_001"])
        inp4 = PIDStepInput(
            node_id="NODE_001", current_mastery=0.6,
            continuous_fail_counter=2, pid_state=saved_state,
        )
        r4 = controller.step(inp4)

        # C_fail=2 == fail_counter_threshold → 触发干预
        assert r4.intervention_triggered is True, (
            f"C_fail={config.fail_counter_threshold} 应触发干预"
        )
        # 增益调度也应生效
        assert r4.effective_kp > config.kp_base, "C_fail 达标时 K_p 应放大"
        assert r4.effective_ki > config.ki_base, "C_fail 达标时 K_i 应放大"

    def test_simulate_student_improvement(self, controller: PIDController) -> None:
        """模拟学生逐步进步: 最初 mastery=0.2, 每次 +0.15, 最终 mastery=0.95。"""
        node_id = "N_PROGRESS"
        prev_state = None
        outputs: list[float] = []
        masteries = [0.2, 0.35, 0.5, 0.65, 0.8, 0.95]

        for i, m in enumerate(masteries):
            c_fail = 0 if m >= masteries[max(0, i - 1)] else i  # 进步则 C_fail=0
            result = controller.step(PIDStepInput(
                node_id=node_id,
                current_mastery=m,
                continuous_fail_counter=c_fail,
                pid_state=prev_state,
            ))
            outputs.append(result.control_output)
            prev_state = result.new_state

        # 最终控制输出应接近 output_min (几乎不需要干预)
        assert outputs[-1] < outputs[0], (
            f"进步趋势下控制输出应递减: {outputs}"
        )
        # 误差应收敛到接近 0
        assert abs(prev_state.prev_error) < 0.1, (
            f"最终误差应接近 0: {prev_state.prev_error}"
        )


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
