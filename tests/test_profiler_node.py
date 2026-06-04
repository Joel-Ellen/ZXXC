# -*- coding: utf-8 -*-
"""
Profiler Node — 单元测试套件
==============================

覆盖范围:
  1. ThompsonSampler: Beta 分布采样正确性
  2. ThompsonSampler: 奖励更新 α/β 收敛
  3. ThompsonSampler: 排除风格采样
  4. ThompsonSampler: AgentState ↔ 参数双向同步
  5. EbbinghausForgettingEngine: 遗忘曲线衰减
  6. EbbinghausForgettingEngine: 记忆强度更新
  7. EbbinghausForgettingEngine: 最低保底值
  8. ProfilerNode: 完整画像演进管线
  9. ProfilerNode: C_fail ≥ 3 硬切换干预
 10. ProfilerNode: 推荐风格选择
 11. 边界条件: 零 reward, 极端 mastery, 长时间衰减

运行方式:
    pytest tests/test_profiler_node.py -v
"""

import pytest
import math
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.profiler_node import (
    ProfilerNode,
    ProfilerInput,
    ProfilerOutput,
    ThompsonSampler,
    EbbinghausForgettingEngine,
    StyleProfileResult,
    ForgettingCurveResult,
    create_profiler_node,
)
from src.state.agent_state import (
    AgentState,
    CognitiveStyleDistribution,
    KnowledgeMasteryRecord,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mab() -> ThompsonSampler:
    """创建汤普森采样器（固定种子保证可复现）。"""
    import numpy as np
    return ThompsonSampler(rng=np.random.default_rng(42))


@pytest.fixture
def forgetting() -> EbbinghausForgettingEngine:
    return EbbinghausForgettingEngine()


@pytest.fixture
def profiler() -> ProfilerNode:
    return ProfilerNode(seed=42)


@pytest.fixture
def agent_state() -> AgentState:
    state = AgentState(user_id="U_PROF", course_id="CS101", current_node_id="N_PROF")
    state.dynamic_profile.knowledge_mastery["N_PROF"] = 0.65
    return state


# ============================================================================
# 1. ThompsonSampler — 基础采样
# ============================================================================

class TestThompsonSamplerBasic:
    """测试汤普森采样的基础功能。"""

    def test_initial_params_uniform(self, mab: ThompsonSampler) -> None:
        """初始参数应为均匀 Beta(1,1)。"""
        for name in mab.ARM_NAMES:
            a, b = mab.get_params(name)
            assert a == 1.0
            assert b == 1.0

    def test_sample_returns_valid_style(self, mab: ThompsonSampler) -> None:
        """采样应返回合法风格名称。"""
        style, samples = mab.sample()
        assert style in mab.ARM_NAMES
        assert len(samples) == 3
        assert all(0.0 <= v <= 1.0 for v in samples.values())

    def test_sample_distribution_changes_with_params(self, mab: ThompsonSampler) -> None:
        """修改参数后采样分布应变化。"""
        # 将 visual 的 α 设得很高 → 其期望值应接近 1.0
        mab.set_params("visual", 100.0, 1.0)
        mab.set_params("textual", 1.0, 100.0)
        mab.set_params("practical", 1.0, 100.0)

        # 多次采样应高度倾向 visual
        results = [mab.sample()[0] for _ in range(50)]
        visual_wins = sum(1 for r in results if r == "visual")
        assert visual_wins >= 35, (
            f"高 α 的 visual 应被频繁选中: {visual_wins}/50"
        )

    def test_expected_rewards(self, mab: ThompsonSampler) -> None:
        """期望奖励 E[Beta(α,β)] = α/(α+β)。"""
        mab.set_params("visual", 10.0, 5.0)   # E = 10/15 = 0.667
        mab.set_params("textual", 5.0, 10.0)   # E = 5/15 = 0.333
        means = mab.get_expected_rewards()
        assert means["visual"] == pytest.approx(10.0 / 15.0, rel=1e-4)
        assert means["textual"] == pytest.approx(5.0 / 15.0, rel=1e-4)


# ============================================================================
# 2. ThompsonSampler — 奖励更新
# ============================================================================

class TestThompsonSamplerUpdate:
    """测试奖励更新与收敛。"""

    def test_success_increases_alpha(self, mab: ThompsonSampler) -> None:
        """高 reward → α 增加。"""
        old_a, old_b = mab.get_params("visual")
        mab.update("visual", 0.85)  # reward ≥ 0.6
        new_a, new_b = mab.get_params("visual")
        assert new_a > old_a
        assert new_b == old_b  # β 不变

    def test_failure_increases_beta(self, mab: ThompsonSampler) -> None:
        """低 reward → β 增加。"""
        old_a, old_b = mab.get_params("visual")
        mab.update("visual", 0.3)  # reward < 0.6
        new_a, new_b = mab.get_params("visual")
        assert new_a == old_a
        assert new_b > old_b

    def test_params_never_degenerate(self, mab: ThompsonSampler) -> None:
        """参数不应退化到零。"""
        mab.set_params("visual", 0.005, 0.005)
        mab.update("visual", 0.0)
        a, b = mab.get_params("visual")
        assert a >= 0.01
        assert b >= 0.01

    def test_convergence_after_many_updates(self, mab: ThompsonSampler) -> None:
        """大量更新后，最优臂的期望奖励应收敛。"""
        # 模拟 visual 持续优于 textual
        for _ in range(20):
            mab.update("visual", 0.8)   # 持续成功
            mab.update("textual", 0.3)  # 持续失败
        means = mab.get_expected_rewards()
        assert means["visual"] > means["textual"], (
            f"visual 应优于 textual: {means}"
        )


# ============================================================================
# 3. ThompsonSampler — AgentState 同步
# ============================================================================

class TestThompsonSamplerSync:
    """测试与 AgentState 的双向同步。"""

    def test_load_from_cognitive_distribution(self, mab: ThompsonSampler) -> None:
        """从 CognitiveStyleDistribution 加载参数。"""
        csd = CognitiveStyleDistribution(
            visual_alpha=5.0, visual_beta=3.0,
            textual_alpha=2.0, textual_beta=7.0,
            practical_alpha=4.0, practical_beta=4.0,
        )
        mab.load_from_cognitive_distribution(csd)
        assert mab.get_params("visual") == (5.0, 3.0)
        assert mab.get_params("textual") == (2.0, 7.0)

    def test_save_to_cognitive_distribution(self, mab: ThompsonSampler) -> None:
        """写回 CognitiveStyleDistribution 应保持一致性。"""
        mab.set_params("visual", 6.0, 2.0)
        mab.set_params("textual", 3.0, 8.0)
        mab.set_params("practical", 5.0, 3.0)

        csd = mab.save_to_cognitive_distribution()
        assert csd.visual_alpha == 6.0
        assert csd.textual_beta == 8.0
        assert csd.practical_alpha == 5.0


# ============================================================================
# 4. EbbinghausForgettingEngine — 遗忘曲线
# ============================================================================

class TestEbbinghausForgetting:
    """测试艾宾浩斯遗忘曲线引擎。"""

    def test_no_decay_immediate(self, forgetting: EbbinghausForgettingEngine) -> None:
        """零时间间隔 → 无衰减。"""
        now = time.time()
        result = forgetting.apply_decay("N1", 0.8, now, now)
        assert result.decay_factor == pytest.approx(1.0, rel=1e-6)
        assert result.mastery_after == pytest.approx(0.8, rel=1e-6)

    def test_decay_over_time(self, forgetting: EbbinghausForgettingEngine) -> None:
        """长时间后应有显著衰减。"""
        now = time.time()
        # 100 小时前
        result = forgetting.apply_decay("N2", 1.0, now - 360000, now)
        assert result.decay_factor < 0.5, (
            f"100h 后应有显著衰减, decay={result.decay_factor:.4f}"
        )
        assert result.mastery_after < 0.5

    def test_mastery_floor(self, forgetting: EbbinghausForgettingEngine) -> None:
        """掌握度不应跌破保底值 0.15。"""
        now = time.time()
        result = forgetting.apply_decay("N3", 1.0, now - 3600000, now)
        assert result.mastery_after >= 0.15

    def test_stronger_memory_decays_slower(self, forgetting: EbbinghausForgettingEngine) -> None:
        """高记忆强度应导致更慢的衰减。"""
        now = time.time()
        past = now - 36000  # 10 小时前

        forgetting.set_strength("N_STRONG", 20.0)
        r_strong = forgetting.apply_decay("N_STRONG", 0.9, past, now)

        forgetting.set_strength("N_WEAK", 1.0)
        r_weak = forgetting.apply_decay("N_WEAK", 0.9, past, now)

        assert r_strong.decay_factor > r_weak.decay_factor, (
            f"强记忆衰减应更慢: strong={r_strong.decay_factor:.4f}, "
            f"weak={r_weak.decay_factor:.4f}"
        )

    def test_strength_update_on_success(self, forgetting: EbbinghausForgettingEngine) -> None:
        """成功交互应增强记忆强度。"""
        forgetting.set_strength("N4", 5.0)
        new_s = forgetting.update_strength("N4", 0.85)
        assert new_s > 5.0, f"成功应增强记忆: {new_s}"

    def test_strength_update_on_failure(self, forgetting: EbbinghausForgettingEngine) -> None:
        """失败交互应减弱记忆强度。"""
        forgetting.set_strength("N5", 5.0)
        new_s = forgetting.update_strength("N5", 0.3)
        assert new_s < 5.0

    def test_strength_within_bounds(self, forgetting: EbbinghausForgettingEngine) -> None:
        """记忆强度应在 [0.5, 20.0] 范围内。"""
        forgetting.set_strength("N6", 100.0)
        assert forgetting.get_strength("N6") <= 20.0
        forgetting.set_strength("N7", 0.01)
        assert forgetting.get_strength("N7") >= 0.5


# ============================================================================
# 5. ProfilerNode — 完整画像演进
# ============================================================================

class TestProfilerNodeFull:
    """测试 Profiler Node 的完整画像演进管线。"""

    def test_full_pipeline(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """完整管线: 采样 → 推荐 → 更新 → 衰减 → 写回。"""
        inp = ProfilerInput(
            agent_state=agent_state,
            evaluator_mastery_delta=0.05,
            evaluator_pid_error=0.1,
            resource_style_delivered="visual",
            node_id="N_PROF",
        )
        output = profiler(inp)

        assert isinstance(output, ProfilerOutput)
        assert output.recommended_resource_style in ThompsonSampler.ARM_NAMES
        assert output.style_result.selected_style in ThompsonSampler.ARM_NAMES
        # AgentState 中的认知风格应被更新
        csd = output.agent_state.static_profile.cognitive_style_distribution
        assert csd.visual_alpha > 1.0 or csd.textual_alpha > 1.0 or csd.practical_alpha > 1.0

    def test_recommended_style_is_valid(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """推荐的资源推送风格应为合法值。"""
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output.recommended_resource_style in ("visual", "textual", "practical")

    def test_forgetting_applied(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """遗忘衰减应在有历史记录时被应用。"""
        # 先设置一个较旧的时间戳
        import datetime
        agent_state.dynamic_profile.knowledge_mastery_records["N_PROF"] = (
            KnowledgeMasteryRecord(
                node_id="N_PROF",
                mastery=0.65,
                last_updated="2020-01-01T00:00:00",  # 很久以前
                interaction_count=3,
            )
        )
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="N_PROF",
            current_timestamp=time.time(),
        )
        output = profiler(inp)
        assert output.forgetting_result is not None
        assert output.forgetting_result.mastery_after <= output.forgetting_result.mastery_before

    def test_no_forgetting_without_record(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """无历史记录时遗忘引擎不应崩溃。"""
        # mastery 在 knowledge_mastery 中但不在 records 中
        agent_state.dynamic_profile.knowledge_mastery["N_NEW"] = 0.7
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="N_NEW",
            current_timestamp=time.time(),
        )
        output = profiler(inp)
        # 应该不报错，可能返回 None 或轻微衰减
        assert output is not None


# ============================================================================
# 6. ProfilerNode — 硬切换干预
# ============================================================================

class TestProfilerIntervention:
    """测试 C_fail ≥ 3 时的硬切换干预机制。"""

    def test_intervention_triggered(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """C_fail ≥ 3 + 有当前风格 → 排除当前风格，硬切换。"""
        agent_state.dynamic_profile.continuous_fail_counter = 4

        inp = ProfilerInput(
            agent_state=agent_state,
            resource_style_delivered="visual",  # 当前风格
            evaluator_mastery_delta=-0.1,
            evaluator_pid_error=0.8,
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output.intervention_active is True
        assert output.style_result.intervention_triggered is True
        # 硬切换不应选择 visual
        assert output.style_result.selected_style != "visual", (
            f"硬切换应排除 visual, 实际选择 {output.style_result.selected_style}"
        )

    def test_no_intervention_below_threshold(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """C_fail < 3 → 不触发硬切换。"""
        agent_state.dynamic_profile.continuous_fail_counter = 2
        inp = ProfilerInput(
            agent_state=agent_state,
            resource_style_delivered="visual",
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output.intervention_active is False

    def test_no_intervention_without_current_style(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """无 resource_style_delivered → 不触发干预（无法确定当前风格）。"""
        agent_state.dynamic_profile.continuous_fail_counter = 5
        inp = ProfilerInput(
            agent_state=agent_state,
            resource_style_delivered=None,  # 无当前风格
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output.intervention_active is False


# ============================================================================
# 7. ProfilerNode — MAB 学习
# ============================================================================

class TestProfilerMABLearning:
    """测试 MAB 在多次交互中的学习与收敛。"""

    def test_mab_learns_preferred_style(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """多次成功后 MAB 应倾向于选择成功风格。"""
        # 模拟 textual 持续成功
        results = []
        state = agent_state
        for _ in range(10):
            inp = ProfilerInput(
                agent_state=state,
                evaluator_mastery_delta=0.05,
                evaluator_pid_error=0.05,  # 小误差 → 高 reward
                resource_style_delivered="textual",
                node_id="N_PROF",
            )
            output = profiler(inp)
            state = output.agent_state
            results.append(output.style_result.selected_style)

        # 经过多轮学习后, textual 应被更频繁选中
        textual_count = results.count("textual")
        assert textual_count >= 3, (
            f"10 轮后 textual 应被频繁选中: {textual_count}/10"
        )


# ============================================================================
# 8. 边界条件
# ============================================================================

class TestBoundaryConditions:
    """边界条件与鲁棒性测试。"""

    def test_zero_mastery(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """掌握度为 0 时不应崩溃。"""
        agent_state.dynamic_profile.knowledge_mastery["N_PROF"] = 0.0
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output is not None

    def test_perfect_mastery(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """掌握度为 1.0 时不应崩溃。"""
        agent_state.dynamic_profile.knowledge_mastery["N_PROF"] = 1.0
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="N_PROF",
        )
        output = profiler(inp)
        assert output is not None

    def test_unknown_node_id(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """未知知识点 ID 不应崩溃。"""
        inp = ProfilerInput(
            agent_state=agent_state,
            node_id="NONEXISTENT_NODE",
        )
        output = profiler(inp)
        assert output is not None

    def test_extreme_reward(self, profiler: ProfilerNode, agent_state: AgentState) -> None:
        """极端 reward 值不应导致参数异常。"""
        for reward_signal in [0.0, 1.0, -999, 999]:
            inp = ProfilerInput(
                agent_state=agent_state,
                evaluator_mastery_delta=reward_signal,
                evaluator_pid_error=reward_signal,
                resource_style_delivered="visual",
                node_id="N_PROF",
            )
            output = profiler(inp)
            # 所有参数应在合理范围内
            for name in ThompsonSampler.ARM_NAMES:
                a, b = profiler.mab.get_params(name)
                assert 0.01 <= a <= 1000, f"{name} α={a} 越界"
                assert 0.01 <= b <= 1000, f"{name} β={b} 越界"

    def test_deterministic_with_seed(self) -> None:
        """相同种子应产生相同的采样序列。"""
        p1 = ProfilerNode(seed=123)
        p2 = ProfilerNode(seed=123)
        styles1 = [p1.mab.sample()[0] for _ in range(20)]
        styles2 = [p2.mab.sample()[0] for _ in range(20)]
        assert styles1 == styles2, "相同种子应产生相同序列"


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
