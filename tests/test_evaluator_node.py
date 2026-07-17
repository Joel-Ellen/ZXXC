# -*- coding: utf-8 -*-
"""
Evaluator Node — 单元测试套件
===============================

覆盖范围:
  1. BehaviorCleaner: 正常行为清洗
  2. BehaviorCleaner: 挂机检测 (time_ratio > 3.0)
  3. BehaviorCleaner: 秒杀作弊检测 (高正确率 + 极短时长)
  4. BehaviorCleaner: 不一致行为 (高正确率 + 高频提问)
  5. BehaviorCleaner: 快速猜测检测
  6. BehaviorCleaner: 软门控 Sigmoid 融合
  7. PIDReplanGate: 正常区间内 (MAINTAIN)
  8. PIDReplanGate: 单次越界 (PENDING)
  9. PIDReplanGate: 连续 N 次越界触发 (TRIGGER)
 10. PIDReplanGate: 越界回正常 → 计数清零
 11. PIDReplanGate: 置信区间边界值
 12. PIDReplanController: 完整 PID 平滑评估
 13. PIDReplanController: 摩擦系数对掌握度增量的抑制
 14. EvaluatorNode: 完整端到端流程
 15. EvaluatorNode: 挂机数据不计入掌握度
 16. EvaluatorNode: 作弊数据触发摩擦 + 惩罚
 17. EvaluatorNode: C_fail 计数器更新
 18. EvaluatorNode: re_plan_triggered 生命周期
 19. EvaluatorNode: 错误类型分布 EMA 更新
 20. 边界条件: 全零 / 全满分 / 极端时长

运行方式:
    pytest tests/test_evaluator_node.py -v
"""

import pytest
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.evaluator_node import (
    EvaluatorNode,
    EvaluatorInput,
    EvaluatorOutput,
    BehaviorVector,
    CleanedBehavior,
    BehaviorCleaner,
    BehaviorAnomaly,
    AnomalyType,
    PIDReplanGate,
    PIDReplanController,
    ReplanDecision,
    GateConfig,
    create_evaluator_node,
)
from src.infrastructure.pid_controller import PIDConfig
from src.state.agent_state import (
    AgentState,
    StaticProfile,
    DynamicProfile,
    LatestBehavior,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def cleaner() -> BehaviorCleaner:
    return BehaviorCleaner()


@pytest.fixture
def gate() -> PIDReplanGate:
    return PIDReplanGate(
        node_id="N_TEST",
        window_size=5,
        stagnation_threshold=0.01,
        trigger_threshold=3,
    )


@pytest.fixture
def controller() -> PIDReplanController:
    return PIDReplanController()


@pytest.fixture
def evaluator() -> EvaluatorNode:
    return EvaluatorNode()


@pytest.fixture
def agent_state() -> AgentState:
    state = AgentState(user_id="U_TEST", course_id="CS101", current_node_id="N_TEST")
    state.dynamic_profile.knowledge_mastery["N_TEST"] = 0.50
    return state


@pytest.fixture
def normal_behavior() -> BehaviorVector:
    return BehaviorVector(
        answer_correctness=0.85,
        code_pass_rate=0.80,
        time_spent_ratio=1.2,
        help_request_count=1,
        total_attempts=3,
        node_id="N_TEST",
    )


# ============================================================================
# 1. BehaviorCleaner — 正常行为
# ============================================================================

class TestBehaviorCleanerNormal:
    """测试正常行为清洗（无异常）。"""

    def test_normal_behavior_passes_through(self, cleaner: BehaviorCleaner) -> None:
        """正常行为应完整通过，无惩罚。"""
        raw = BehaviorVector(
            answer_correctness=0.85, time_spent_ratio=1.5, help_request_count=2,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.NORMAL
        assert cleaned.is_valid is True
        assert cleaned.effective_correctness == pytest.approx(0.85, rel=1e-6)
        assert cleaned.friction_coefficient == 1.0

    def test_verified_quiz_score_only_bypasses_unmeasured_signal_gates(
        self, cleaner: BehaviorCleaner
    ) -> None:
        raw = BehaviorVector(answer_correctness=1.0, verified_quiz_score_only=True)

        cleaned = cleaner.clean(raw)

        assert cleaned.anomaly.anomaly_type == AnomalyType.NORMAL
        assert cleaned.effective_correctness == 1.0
        assert cleaned.effective_code_pass == 0.0

    def test_perfect_score_normal_time(self, cleaner: BehaviorCleaner) -> None:
        """满分 + 正常时长 → 正常。"""
        raw = BehaviorVector(
            answer_correctness=1.0, time_spent_ratio=1.0, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.NORMAL

    def test_low_score_normal_time(self, cleaner: BehaviorCleaner) -> None:
        """低分 + 正常时长 → 正常（不是作弊，只是不会）。"""
        raw = BehaviorVector(
            answer_correctness=0.3, time_spent_ratio=1.8, help_request_count=3,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.NORMAL
        assert cleaned.is_valid is True


# ============================================================================
# 2. BehaviorCleaner — 挂机检测
# ============================================================================

class TestBehaviorCleanerAFK:
    """测试挂机 (AFK) 检测。"""

    def test_afk_detected(self, cleaner: BehaviorCleaner) -> None:
        """时长比 > 3.0 → 挂机。"""
        raw = BehaviorVector(
            answer_correctness=0.5, time_spent_ratio=5.0, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.AFK
        assert cleaned.is_valid is False
        assert cleaned.effective_correctness == 0.0, "挂机数据不计入掌握度"

    def test_afk_exactly_at_threshold(self, cleaner: BehaviorCleaner) -> None:
        """时长比 = 3.0001 → 挂机 (严格大于阈值)。"""
        raw = BehaviorVector(
            answer_correctness=0.7, time_spent_ratio=3.0001, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.AFK

    def test_below_afk_threshold_not_afk(self, cleaner: BehaviorCleaner) -> None:
        """时长比 = 2.9 < 3.0 → 非挂机。"""
        raw = BehaviorVector(
            answer_correctness=0.5, time_spent_ratio=2.9, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type != AnomalyType.AFK


# ============================================================================
# 3. BehaviorCleaner — 秒杀作弊检测
# ============================================================================

class TestBehaviorCleanerCheating:
    """测试秒杀作弊检测。"""

    def test_cheating_speed_detected(self, cleaner: BehaviorCleaner) -> None:
        """正确率 ≥ 0.9 + 时长比 < 0.05 → 秒杀作弊。"""
        raw = BehaviorVector(
            answer_correctness=0.95,
            code_pass_rate=1.0,
            time_spent_ratio=0.02,
            help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.CHEATING_SPEED
        assert cleaned.anomaly.score_penalty == 0.90
        assert cleaned.friction_coefficient == 2.0
        # 有效正确率应被削减 90%
        assert cleaned.effective_correctness < 0.15, (
            f"正确率应被削减 90%, 实际 {cleaned.effective_correctness}"
        )

    def test_cheating_code_pass_also_penalized(self, cleaner: BehaviorCleaner) -> None:
        """秒杀作弊时代码通过率也应被惩罚。"""
        raw = BehaviorVector(
            answer_correctness=1.0,
            code_pass_rate=0.95,
            time_spent_ratio=0.01,
            help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.effective_code_pass < 0.15

    def test_high_score_not_cheating_with_normal_time(self, cleaner: BehaviorCleaner) -> None:
        """高正确率 + 正常时长 → 非作弊。"""
        raw = BehaviorVector(
            answer_correctness=0.95, time_spent_ratio=0.5, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type != AnomalyType.CHEATING_SPEED


# ============================================================================
# 4. BehaviorCleaner — 不一致行为
# ============================================================================

class TestBehaviorCleanerInconsistent:
    """测试不一致行为检测（高正确率 + 高频提问）。"""

    def test_inconsistent_detected(self, cleaner: BehaviorCleaner) -> None:
        """正确率 ≥ 0.9 + 提问 > 5 次 → 不一致。"""
        raw = BehaviorVector(
            answer_correctness=0.92, time_spent_ratio=0.8, help_request_count=8,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.INCONSISTENT
        assert cleaned.anomaly.score_penalty == 0.50
        assert cleaned.friction_coefficient == 1.5
        # 有效正确率应被削减 50%
        assert abs(cleaned.effective_correctness - 0.92 * 0.5) < 0.01

    def test_high_help_normal_score_not_inconsistent(self, cleaner: BehaviorCleaner) -> None:
        """高频提问 + 低正确率 → 正常（确实不会）。"""
        raw = BehaviorVector(
            answer_correctness=0.4, time_spent_ratio=1.5, help_request_count=7,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type != AnomalyType.INCONSISTENT


# ============================================================================
# 5. BehaviorCleaner — 快速猜测
# ============================================================================

class TestBehaviorCleanerRapidGuessing:
    """测试快速猜测检测。"""

    def test_rapid_guessing_detected(self, cleaner: BehaviorCleaner) -> None:
        """时长 < 0.1 + 正确率在 0.4-0.7 之间 → 快速猜测。"""
        raw = BehaviorVector(
            answer_correctness=0.55, time_spent_ratio=0.05, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.RAPID_GUESSING
        assert cleaned.friction_coefficient == 1.3
        # 正确率不被惩罚，但摩擦系数提高
        assert cleaned.effective_correctness == pytest.approx(0.55, rel=1e-6)

    def test_rapid_low_score_not_guessing(self, cleaner: BehaviorCleaner) -> None:
        """快速 + 极低正确率 → 不是猜测（只是不会做）。"""
        raw = BehaviorVector(
            answer_correctness=0.1, time_spent_ratio=0.05, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        assert cleaned.anomaly.anomaly_type == AnomalyType.NORMAL


# ============================================================================
# 6. BehaviorCleaner — 软门控 Sigmoid
# ============================================================================

class TestBehaviorCleanerSigmoidGate:
    """测试 Sigmoid 软门控行为质量评估。"""

    def test_sigmoid_numerical_stability(self, cleaner: BehaviorCleaner) -> None:
        """Sigmoid 应在极端输入下仍保持数值稳定。"""
        s = cleaner._sigmoid
        assert s(100) == pytest.approx(1.0, rel=1e-6)
        assert s(-100) == pytest.approx(0.0, rel=1e-6)
        assert s(0) == 0.5
        assert 0 < s(-5) < s(0) < s(5) <= 1, (
            f"Sigmoid 应单调递增: s(-5)={s(-5):.4f}, s(0)=0.5, s(5)={s(5):.4f}"
        )

    def test_quality_score_high_for_good_behavior(self, cleaner: BehaviorCleaner) -> None:
        """高质量行为（高正确率 + 适中时长）→ quality_score 接近 1.0。"""
        raw = BehaviorVector(
            answer_correctness=0.95, time_spent_ratio=1.0, help_request_count=1,
        )
        cleaned = cleaner.clean(raw)
        # 正常行为不会被惩罚
        assert cleaned.effective_correctness == pytest.approx(0.95, rel=1e-6)

    def test_quality_score_low_triggers_soft_penalty(self, cleaner: BehaviorCleaner) -> None:
        """低质量 + 高正确率 → 软惩罚微调。"""
        raw = BehaviorVector(
            answer_correctness=0.88, time_spent_ratio=0.06, help_request_count=0,
        )
        cleaned = cleaner.clean(raw)
        # 正常但质量偏低：正确率 0.88 但时长太短
        # 软门控应触发轻微调整
        assert cleaned.effective_correctness <= raw.answer_correctness


# ============================================================================
# 7. PIDReplanGate — 闸门状态机
# ============================================================================

class TestPIDReplanGate:
    """测试重寻路闸门的状态转移逻辑 (Δe-based 判定)。"""

    def test_decreasing_error_maintain(self, gate: PIDReplanGate) -> None:
        """误差在缩小（Δe ≤ 0）→ MAINTAIN。"""
        errors = [0.9, 0.7, 0.5, 0.3, 0.1]  # 持续进步
        for e in errors:
            decision = gate.record_control_value(e)
        assert decision == ReplanDecision.MAINTAIN
        assert gate.consecutive_out_of_bounds == 0

    def test_initial_value_no_prev(self, gate: PIDReplanGate) -> None:
        """首个值（无 prev_error）→ MAINTAIN（无法计算 Δe）。"""
        decision = gate.record_control_value(0.80)
        assert decision == ReplanDecision.MAINTAIN  # 首个值不判定

    def test_increasing_error_pending(self, gate: PIDReplanGate) -> None:
        """误差扩大（Δe > 0）→ PENDING。"""
        gate.record_control_value(0.50)  # e(t-1) = 0.50, 初始
        decision = gate.record_control_value(0.65)  # Δe = +0.15 > 0
        assert decision == ReplanDecision.PENDING
        assert gate.consecutive_out_of_bounds == 1

    def test_consecutive_increase_triggers(self, gate: PIDReplanGate) -> None:
        """连续 3 次误差扩大 → TRIGGER。"""
        decisions = []
        errors = [0.50, 0.55, 0.62, 0.70]  # 每次递增
        for e in errors:
            decisions.append(gate.record_control_value(e))
        # 首个值: MAINTAIN, 后三次: PENDING, PENDING, TRIGGER
        assert decisions[0] == ReplanDecision.MAINTAIN  # no prev
        assert decisions[1] == ReplanDecision.PENDING
        assert decisions[2] == ReplanDecision.PENDING
        assert decisions[3] == ReplanDecision.TRIGGER
        assert gate.consecutive_out_of_bounds == 3

    def test_stagnation_triggers(self, gate: PIDReplanGate) -> None:
        """误差停滞在高位（|Δe| < stagnation + error > 0.3）→ 越界。"""
        gate.record_control_value(0.60)  # e(t-1) = 0.60
        gate.record_control_value(0.605)  # Δe = 0.005 < 0.01 stagnation, error=0.605 > 0.3
        decision = gate.record_control_value(0.601)  # 继续停滞
        assert decision == ReplanDecision.PENDING, (
            f"高位停滞应判定为越界: {decision}"
        )

    def test_recovery_resets_counter(self, gate: PIDReplanGate) -> None:
        """进步后计数清零。"""
        gate.record_control_value(0.50)
        gate.record_control_value(0.52)  # PENDING
        gate.record_control_value(0.54)  # PENDING
        decision = gate.record_control_value(0.48)  # Δe = -0.06 < 0 → MAINTAIN
        assert decision == ReplanDecision.MAINTAIN
        assert gate.consecutive_out_of_bounds == 0

    def test_reset_clears_all(self, gate: PIDReplanGate) -> None:
        """reset() 应清空所有状态。"""
        for e in [0.5, 0.55, 0.60, 0.65]:
            gate.record_control_value(e)
        assert gate.decision == ReplanDecision.TRIGGER

        gate.reset()
        assert gate.consecutive_out_of_bounds == 0
        assert gate.control_history == []
        assert gate.prev_error is None
        assert gate.decision == ReplanDecision.MAINTAIN

    def test_window_truncation(self, gate: PIDReplanGate) -> None:
        """控制历史应被窗口大小截断。"""
        for i in range(10):
            gate.record_control_value(0.5 + 0.01 * i)
        assert len(gate.control_history) <= gate.window_size

    def test_trigger_threshold_custom(self) -> None:
        """自定义 trigger_threshold 应正确生效。"""
        gate = PIDReplanGate(
            node_id="N_CUSTOM",
            trigger_threshold=5,
            stagnation_threshold=0.01,
        )
        gate.record_control_value(0.5)
        for _ in range(4):
            d = gate.record_control_value(0.52)
            assert d == ReplanDecision.PENDING
        d = gate.record_control_value(0.54)
        assert d == ReplanDecision.TRIGGER


# ============================================================================
# 8. PIDReplanController — PID 平滑评估
# ============================================================================

class TestPIDReplanController:
    """测试 PID 平滑评估控制器的完整流程。"""

    def test_normal_evaluation(self, controller: PIDReplanController) -> None:
        """正常行为评估应返回合理的掌握度增量。"""
        cleaned = CleanedBehavior(
            raw=BehaviorVector(
                answer_correctness=0.85, code_pass_rate=0.80,
                time_spent_ratio=1.2, help_request_count=1,
            ),
            effective_correctness=0.85, effective_code_pass=0.80,
            is_valid=True, friction_coefficient=1.0,
        )
        updated, delta, pid_out, pid_err, decision, gate = controller.evaluate(
            node_id="N_EVAL",
            cleaned=cleaned,
            current_mastery=0.50,
            continuous_fail_counter=0,
        )
        # 当前 mastery=0.5, setpoint=1.0 → error > 0 → delta 应为正
        assert 0.0 <= updated <= 1.0
        assert delta > 0, f"掌握度低于目标时应正向增长, delta={delta}"
        assert decision == ReplanDecision.MAINTAIN

    def test_mastery_above_target(self, controller: PIDReplanController) -> None:
        """掌握度接近目标时应收敛。"""
        cleaned = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.9, time_spent_ratio=1.0),
            effective_correctness=0.9, effective_code_pass=0.0,
            is_valid=True, friction_coefficient=1.0,
        )
        updated, delta, pid_out, pid_err, decision, gate = controller.evaluate(
            node_id="N_HIGH",
            cleaned=cleaned,
            current_mastery=0.95,  # 接近 1.0
            continuous_fail_counter=0,
        )
        assert abs(delta) < 0.2, f"已接近掌握时增量应较小, delta={delta}"

    def test_friction_suppresses_mastery_gain(self, controller: PIDReplanController) -> None:
        """摩擦系数 > 1.0 应抑制掌握度增长。"""
        cleaned_no_friction = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.7, time_spent_ratio=1.0),
            effective_correctness=0.7, effective_code_pass=0.0,
            is_valid=True, friction_coefficient=1.0,
        )
        cleaned_with_friction = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.7, time_spent_ratio=1.0),
            effective_correctness=0.7, effective_code_pass=0.0,
            is_valid=True, friction_coefficient=2.0,
        )
        _, delta_no_f, _, _, _, _ = controller.evaluate(
            "N_F1", cleaned_no_friction, 0.5, 0,
        )
        _, delta_with_f, _, _, _, _ = controller.evaluate(
            "N_F2", cleaned_with_friction, 0.5, 0,
        )
        assert delta_with_f < delta_no_f, (
            f"摩擦系数 2.0 应抑制增长: no_f={delta_no_f}, with_f={delta_with_f}"
        )

    def test_invalid_behavior_no_update(self, controller: PIDReplanController) -> None:
        """挂机数据不应修改掌握度。"""
        cleaned = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.5, time_spent_ratio=5.0),
            effective_correctness=0.0, effective_code_pass=0.0,
            is_valid=False, friction_coefficient=1.0,
        )
        updated, delta, pid_out, pid_err, decision, gate = controller.evaluate(
            node_id="N_AFK",
            cleaned=cleaned,
            current_mastery=0.50,
            continuous_fail_counter=0,
        )
        assert delta == 0.0
        assert updated == 0.50
        assert decision == ReplanDecision.MAINTAIN

    def test_cfail_affects_pid_gain(self, controller: PIDReplanController) -> None:
        """C_fail 较高时 PID 输出应更大（增益调度生效）。"""
        cleaned = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.4, time_spent_ratio=1.0),
            effective_correctness=0.4, effective_code_pass=0.0,
            is_valid=True, friction_coefficient=1.0,
        )
        _, _, pid_low, _, _, _ = controller.evaluate(
            "N_CF1", cleaned, 0.5, 0,
        )
        _, _, pid_high, _, _, _ = controller.evaluate(
            "N_CF2", cleaned, 0.5, 5,  # C_fail=5 触发增益放大
        )
        assert pid_high > pid_low, (
            f"高 C_fail 应产生更强的 PID 输出: low={pid_low}, high={pid_high}"
        )

    def test_gate_independence_across_nodes(self, controller: PIDReplanController) -> None:
        """不同知识点的闸门应相互独立。"""
        cleaned = CleanedBehavior(
            raw=BehaviorVector(answer_correctness=0.5, time_spent_ratio=1.0),
            effective_correctness=0.5, effective_code_pass=0.0,
            is_valid=True, friction_coefficient=1.0,
        )
        # 节点 A: 制造误差递增 (退步)
        for m in [0.3, 0.25, 0.2]:
            controller.evaluate("N_A", cleaned, m, 0)
        gate_a = controller.get_gate("N_A")
        assert gate_a is not None and gate_a.consecutive_out_of_bounds >= 2

        # 节点 B: 独立，应从 MAINTAIN 开始
        _, _, _, _, decision_b, gate_b = controller.evaluate(
            "N_B", cleaned, 0.5, 0,
        )
        assert decision_b == ReplanDecision.MAINTAIN, (
            f"节点 B 不应受 A 的闸门影响: {decision_b}"
        )
        assert gate_b.consecutive_out_of_bounds == 0


# ============================================================================
# 9. EvaluatorNode — 端到端流程
# ============================================================================

class TestEvaluatorNodeE2E:
    """测试 Evaluator Node 的完整端到端流程。"""

    def test_full_pipeline_normal(
        self, evaluator: EvaluatorNode, agent_state: AgentState, normal_behavior: BehaviorVector
    ) -> None:
        """完整流程: 正常行为 → 清洗 → PID 评估 → AgentState 更新。"""
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=normal_behavior)
        output = evaluator(inp)

        assert isinstance(output, EvaluatorOutput)
        assert output.anomaly_detected is False
        assert output.cleaned_behavior.is_valid is True
        assert 0.0 <= output.updated_mastery <= 1.0
        assert output.replan_decision == ReplanDecision.MAINTAIN
        assert output.agent_state.latest_behavior is not None
        assert output.agent_state.iteration == 1

    def test_afk_does_not_update_mastery(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """挂机数据不应导致掌握度变化。"""
        original_mastery = agent_state.dynamic_profile.knowledge_mastery["N_TEST"]
        afk_behavior = BehaviorVector(
            answer_correctness=0.7, time_spent_ratio=10.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=afk_behavior)
        output = evaluator(inp)
        assert output.anomaly_detected is True
        assert output.cleaned_behavior.anomaly.anomaly_type == AnomalyType.AFK
        assert output.mastery_delta == 0.0
        assert output.updated_mastery == original_mastery

    def test_cheating_triggers_penalty_and_friction(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """作弊行为应触发分数惩罚和摩擦系数。"""
        cheat_behavior = BehaviorVector(
            answer_correctness=0.98,
            code_pass_rate=1.0,
            time_spent_ratio=0.01,
            help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=cheat_behavior)
        output = evaluator(inp)
        assert output.anomaly_detected is True
        assert output.cleaned_behavior.anomaly.anomaly_type == AnomalyType.CHEATING_SPEED
        assert output.cleaned_behavior.friction_coefficient == 2.0
        assert output.cleaned_behavior.effective_correctness < 0.15

    def test_cfail_counter_increments_on_failure(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """连续低正确率应递增 C_fail。"""
        agent_state.dynamic_profile.continuous_fail_counter = 1
        fail_behavior = BehaviorVector(
            answer_correctness=0.3, time_spent_ratio=1.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=fail_behavior)
        output = evaluator(inp)
        assert output.agent_state.dynamic_profile.continuous_fail_counter == 2, (
            f"C_fail 应从 1 递增到 2, 实际 {output.agent_state.dynamic_profile.continuous_fail_counter}"
        )

    def test_cfail_counter_decrements_on_recovery(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """恢复正确率后 C_fail 应递减。"""
        agent_state.dynamic_profile.continuous_fail_counter = 3
        success_behavior = BehaviorVector(
            answer_correctness=0.85, time_spent_ratio=1.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=success_behavior)
        output = evaluator(inp)
        assert output.agent_state.dynamic_profile.continuous_fail_counter == 2, (
            f"C_fail 应从 3 递减到 2, 实际 {output.agent_state.dynamic_profile.continuous_fail_counter}"
        )

    def test_cfail_doesnt_go_negative(self, evaluator: EvaluatorNode, agent_state: AgentState) -> None:
        """C_fail 不应低于 0。"""
        agent_state.dynamic_profile.continuous_fail_counter = 0
        success_behavior = BehaviorVector(
            answer_correctness=1.0, time_spent_ratio=1.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=success_behavior)
        output = evaluator(inp)
        assert output.agent_state.dynamic_profile.continuous_fail_counter == 0

    def test_replan_trigger_on_consecutive_errors(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """连续多轮极低正确率（退步）应触发 re_plan_triggered。"""
        state = agent_state
        state.dynamic_profile.knowledge_mastery["N_TEST"] = 0.6

        # 连续 4 轮极低正确率: PID 会降低 mastery → 误差扩大 → Δe > 0 → 触发
        for _ in range(4):
            behavior = BehaviorVector(
                answer_correctness=0.1,  # 极低正确率
                time_spent_ratio=1.0,
                help_request_count=0,
                node_id="N_TEST",
            )
            inp = EvaluatorInput(agent_state=state, raw_behavior=behavior)
            output = evaluator(inp)
            state = output.agent_state

        # 连续退步应触发重寻路 (第 4 轮后累计 3 次 Δe > 0)
        assert state.re_plan_triggered is True, (
            f"连续退步应触发重寻路"
        )

    def test_no_replan_on_temporary_fluctuation(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """偶发性低分不应触发重寻路（恢复后计数清零）。"""
        state = agent_state
        state.dynamic_profile.knowledge_mastery["N_TEST"] = 0.7

        # 第一轮: 低分（可能是手误）
        # 首个值无法判断趋势 → MAINTAIN
        behavior1 = BehaviorVector(
            answer_correctness=0.1, time_spent_ratio=0.5, help_request_count=0,
            node_id="N_TEST",
        )
        inp1 = EvaluatorInput(agent_state=state, raw_behavior=behavior1)
        output1 = evaluator(inp1)
        assert output1.agent_state.re_plan_triggered is False, (
            "偶发单次低分不应触发重寻路"
        )

        # 第二轮: 继续低分 → 连续退步 → PENDING (但还未触发)
        behavior1b = BehaviorVector(
            answer_correctness=0.15, time_spent_ratio=0.5, help_request_count=0,
            node_id="N_TEST",
        )
        inp1b = EvaluatorInput(agent_state=output1.agent_state, raw_behavior=behavior1b)
        output1b = evaluator(inp1b)
        # 第二轮: mastery 继续下降 → target_error 上升 → PENDING
        assert output1b.replan_decision == ReplanDecision.PENDING

        # 第三轮 + 第四轮: 持续恢复正常 → 计数应清零
        state_after_low = output1b.agent_state
        for round_idx in range(3):  # 3 轮高正确率恢复
            behavior_good = BehaviorVector(
                answer_correctness=0.85, time_spent_ratio=1.0, help_request_count=0,
                node_id="N_TEST",
            )
            inp_good = EvaluatorInput(agent_state=state_after_low, raw_behavior=behavior_good)
            output_good = evaluator(inp_good)
            state_after_low = output_good.agent_state

        # 多轮恢复后应回到 MAINTAIN 状态
        assert state_after_low.re_plan_triggered is False, (
            "偶发低分经多轮恢复后不应触发重寻路"
        )

    def test_error_distribution_ema_update(
        self, evaluator: EvaluatorNode, agent_state: AgentState
    ) -> None:
        """错误类型分布应通过 EMA 更新并保持归一化。"""
        # 使用极端的错误模式以确保 EMA 产生明显变化
        agent_state.dynamic_profile.error_type_distribution.logic_flaw = 0.9
        agent_state.dynamic_profile.error_type_distribution.syntax_error = 0.05
        agent_state.dynamic_profile.error_type_distribution.boundary_miss = 0.05

        old_etd = agent_state.dynamic_profile.error_type_distribution
        old_logic = old_etd.logic_flaw

        behavior = BehaviorVector(
            answer_correctness=0.9,  # 高正确率 → 不是 logic_flaw
            code_pass_rate=0.1,       # 低代码通过率 → syntax_error
            time_spent_ratio=0.5,
            help_request_count=1,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=behavior)
        output = evaluator(inp)
        new_etd = output.agent_state.dynamic_profile.error_type_distribution

        # EMA 后 logic_flaw 应该从 0.9 向 syntax_error 方向移动（减少）
        assert new_etd.logic_flaw < old_logic, (
            f"高正确率时 logic_flaw 应通过 EMA 减少: old={old_logic}, new={new_etd.logic_flaw}"
        )
        total = new_etd.logic_flaw + new_etd.syntax_error + new_etd.boundary_miss
        assert abs(total - 1.0) < 1e-6, f"归一化后总和应为 1.0, 实际 {total}"

    def test_latest_behavior_populated(
        self, evaluator: EvaluatorNode, agent_state: AgentState, normal_behavior: BehaviorVector
    ) -> None:
        """latest_behavior 应被正确填充。"""
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=normal_behavior)
        output = evaluator(inp)
        lb = output.agent_state.latest_behavior
        assert lb is not None
        assert lb.node_id == "N_TEST"
        assert 0.0 <= lb.correctness <= 1.0
        assert lb.help_request_count == 1

    def test_iteration_counter_increments(
        self, evaluator: EvaluatorNode, agent_state: AgentState, normal_behavior: BehaviorVector
    ) -> None:
        """每次评估应递增迭代计数器。"""
        agent_state.iteration = 5
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=normal_behavior)
        output = evaluator(inp)
        assert output.agent_state.iteration == 6


# ============================================================================
# 10. 工厂函数
# ============================================================================

class TestFactoryFunction:
    """测试工厂函数 create_evaluator_node。"""

    def test_create_with_defaults(self) -> None:
        node = create_evaluator_node()
        assert isinstance(node, EvaluatorNode)

    def test_create_with_custom_configs(self) -> None:
        pid_cfg = PIDConfig(kp_base=1.5, ki_base=0.2)
        gate_cfg = GateConfig(trigger_threshold=5)
        node = create_evaluator_node(pid_config=pid_cfg, gate_config=gate_cfg)
        assert node.controller._gate_config.trigger_threshold == 5


# ============================================================================
# 11. Pydantic 模型校验
# ============================================================================

class TestPydanticValidation:
    """测试 Pydantic 模型的字段校验。"""

    def test_behavior_vector_validation(self) -> None:
        """BehaviorVector 字段应在合法范围。"""
        with pytest.raises(Exception):
            BehaviorVector(answer_correctness=1.5)  # 超出 [0,1]
        with pytest.raises(Exception):
            BehaviorVector(time_spent_ratio=-0.1)

    def test_cleaned_behavior_defaults(self) -> None:
        """CleanedBehavior 应有合理的默认值。"""
        cb = CleanedBehavior(raw=BehaviorVector())
        assert cb.is_valid is True
        assert cb.friction_coefficient == 1.0

    def test_gate_config_defaults(self) -> None:
        """GateConfig 默认值应合理。"""
        gc = GateConfig()
        assert gc.trigger_threshold == 3
        assert gc.stagnation_threshold >= 0.0

    def test_evaluator_output_diagnostics(self) -> None:
        """EvaluatorOutput 应包含必要字段。"""
        out = EvaluatorOutput(
            agent_state=AgentState(user_id="U", course_id="C"),
            cleaned_behavior=CleanedBehavior(raw=BehaviorVector()),
        )
        assert out.replan_decision == ReplanDecision.MAINTAIN
        assert out.anomaly_detected is False


# ============================================================================
# 12. 边界条件与压力测试
# ============================================================================

class TestBoundaryAndStress:
    """边界条件与压力测试。"""

    def test_all_zero_behavior(self, evaluator: EvaluatorNode, agent_state: AgentState) -> None:
        """全零行为不应导致崩溃。"""
        raw = BehaviorVector(
            answer_correctness=0.0, code_pass_rate=0.0,
            time_spent_ratio=0.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=raw)
        output = evaluator(inp)
        assert output is not None
        assert 0.0 <= output.updated_mastery <= 1.0

    def test_all_perfect_behavior(self, evaluator: EvaluatorNode, agent_state: AgentState) -> None:
        """全满分行为不应崩溃。"""
        raw = BehaviorVector(
            answer_correctness=1.0, code_pass_rate=1.0,
            time_spent_ratio=1.0, help_request_count=0,
            node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=raw)
        output = evaluator(inp)
        assert output.updated_mastery >= agent_state.dynamic_profile.knowledge_mastery["N_TEST"]

    def test_extreme_time_ratio(self, evaluator: EvaluatorNode, agent_state: AgentState) -> None:
        """极端时长比不应导致崩溃。"""
        for tr in [0.001, 0.01, 100.0, 1000.0]:
            raw = BehaviorVector(
                answer_correctness=0.5, time_spent_ratio=tr,
                help_request_count=0, node_id="N_TEST",
            )
            inp = EvaluatorInput(agent_state=agent_state, raw_behavior=raw)
            output = evaluator(inp)
            assert output is not None

    def test_high_help_count(self, evaluator: EvaluatorNode, agent_state: AgentState) -> None:
        """极端提问次数不应崩溃。"""
        raw = BehaviorVector(
            answer_correctness=0.6, time_spent_ratio=1.0,
            help_request_count=100, node_id="N_TEST",
        )
        inp = EvaluatorInput(agent_state=agent_state, raw_behavior=raw)
        output = evaluator(inp)
        assert output is not None

    def test_rapid_sequence_no_oscillation(self, evaluator: EvaluatorNode) -> None:
        """快速连续评估不应导致掌握度震荡。"""
        state = AgentState(user_id="U_OSC", course_id="C", current_node_id="N_OSC")
        state.dynamic_profile.knowledge_mastery["N_OSC"] = 0.5

        masteries: list[float] = []
        for i in range(20):
            behavior = BehaviorVector(
                answer_correctness=0.5 + 0.02 * i,  # 缓慢进步
                time_spent_ratio=1.0, help_request_count=0,
                node_id="N_OSC",
            )
            inp = EvaluatorInput(agent_state=state, raw_behavior=behavior)
            output = evaluator(inp)
            state = output.agent_state
            masteries.append(output.updated_mastery)

        # 掌握度应单调递增（无震荡）
        for i in range(1, len(masteries)):
            assert masteries[i] >= masteries[i - 1] - 1e-6, (
                f"掌握度在稳定进步时应单调不减: [{i-1}]={masteries[i-1]:.4f}, [{i}]={masteries[i]:.4f}"
            )


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
