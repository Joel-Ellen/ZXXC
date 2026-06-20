# -*- coding: utf-8 -*-
"""
Assessment Reporter Node — 单元测试套件
=========================================

覆盖范围:
  1. CapabilityRadar: 创建与序列化
  2. CapabilityRadar: compute_mean 综合指标计算
  3. CapabilityRadar: describe 人类可读诊断
  4. CapabilityRadar: from_list 工厂方法
  5. HysteresisStrategyController: 降级门控 (A_mix < 0.40 & C_fail >= 2)
  6. HysteresisStrategyController: 升级解除 (A_mix > 0.75)
  7. HysteresisStrategyController: 常态保持 (不触发切换)
  8. HysteresisStrategyController: EDGE_CASE_DRILL 边界遗漏分支
  9. HysteresisStrategyController: SCAFFOLD_HELP → STANDARD_PATH 恢复
 10. AssessmentReporterNode: EMA 能力雷达增量更新
 11. AssessmentReporterNode: 策略决策完整流程
 12. AssessmentReporterNode: 诊断报告生成
 13. AssessmentReporterNode: 边界遗漏 EMA 序列维护
 14. AssessmentReporterNode: alpha 参数校验
 15. AssessmentReporterNode: 阈值参数校验

运行方式:
    pytest tests/test_assessment_node.py -v
"""

import pytest
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.assessment_node import (
    AssessmentReporterNode,
    AssessmentInput,
    AssessmentOutput,
    CapabilityRadar,
    HysteresisStrategyController,
    create_assessment_node,
    STRATEGY_STANDARD,
    STRATEGY_SCAFFOLD,
    STRATEGY_EDGE_CASE,
    RADAR_DIM_CONCEPT,
    RADAR_DIM_CODE,
    RADAR_DIM_LOGIC,
    RADAR_DIM_RESILIENCE,
    RADAR_DIM_TIME,
)
from src.state.agent_state import (
    AgentState,
    LatestBehavior,
    DynamicProfile,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def assessor() -> AssessmentReporterNode:
    """创建默认参数的 AssessmentReporterNode。"""
    return AssessmentReporterNode(alpha=0.2, t_low=0.40, t_high=0.75)


@pytest.fixture
def default_state() -> AgentState:
    """创建带中性行为数据的 AgentState。"""
    state = AgentState(user_id="U1", course_id="CS101")
    state.current_node_id = "N_SORT"
    state.latest_behavior = LatestBehavior(
        node_id="N_SORT",
        accuracy_rate=0.8,
        code_pass_rate=0.75,
        duration_ratio=1.0,
    )
    return state


@pytest.fixture
def low_ability_state() -> AgentState:
    """创建低能力水平（触发降级）的 AgentState。"""
    state = AgentState(user_id="U2", course_id="CS101")
    state.current_node_id = "N_SORT"
    state.latest_behavior = LatestBehavior(
        node_id="N_SORT",
        accuracy_rate=0.2,
        code_pass_rate=0.2,
        duration_ratio=3.0,
    )
    state.dynamic_profile.continuous_fail_counter = 3
    # 预设低能力雷达
    state.dynamic_profile.capability_radar = [0.25, 0.25, 0.3, 0.3, 0.3]
    return state


@pytest.fixture
def high_ability_state() -> AgentState:
    """创建高能力水平（触发升级）当前在 SCAFFOLD_HELP 的 AgentState。"""
    state = AgentState(user_id="U3", course_id="CS101")
    state.current_node_id = "N_TREE"
    state.latest_behavior = LatestBehavior(
        node_id="N_TREE",
        accuracy_rate=0.9,
        code_pass_rate=0.92,
        duration_ratio=0.9,
    )
    state.pedagogical_strategy = STRATEGY_SCAFFOLD
    state.dynamic_profile.capability_radar = [0.8, 0.82, 0.78, 0.8, 0.8]
    return state


@pytest.fixture
def boundary_miss_state() -> AgentState:
    """创建边界遗漏连续走高的 AgentState。"""
    state = AgentState(user_id="U4", course_id="CS101")
    state.current_node_id = "N_ARRAY"
    state.latest_behavior = LatestBehavior(
        node_id="N_ARRAY",
        accuracy_rate=0.6,
        code_pass_rate=0.5,
        duration_ratio=1.2,
        error_types=["boundary_miss"],
    )
    state.pedagogical_strategy = STRATEGY_STANDARD
    state.dynamic_profile.capability_radar = [0.55, 0.5, 0.55, 0.5, 0.5]
    state.dynamic_profile.boundary_miss_ema_sequence = [0.7, 0.72, 0.71]
    return state


# ============================================================================
# 1. CapabilityRadar 模型测试
# ============================================================================

class TestCapabilityRadar:
    """5 维能力雷达图模型测试。"""

    def test_default_values(self) -> None:
        """默认构造应为全 0.5 中性值。"""
        radar = CapabilityRadar()
        assert radar.concept_understanding == 0.5
        assert radar.code_engineering == 0.5
        assert radar.logical_reasoning == 0.5
        assert radar.error_resilience == 0.5
        assert radar.time_management == 0.5

    def test_to_list_and_back(self) -> None:
        """to_list → from_list 应保持数据一致。"""
        original = CapabilityRadar(
            concept_understanding=0.8,
            code_engineering=0.7,
            logical_reasoning=0.9,
            error_resilience=0.6,
            time_management=0.5,
        )
        lst = original.to_list()
        assert lst == [0.8, 0.7, 0.9, 0.6, 0.5]

        restored = CapabilityRadar.from_list(lst)
        assert restored.concept_understanding == 0.8
        assert restored.code_engineering == 0.7

    def test_from_list_wrong_length_raises(self) -> None:
        """from_list 传入错误长度应抛出 ValueError。"""
        with pytest.raises(ValueError, match="必须包含 5 个值"):
            CapabilityRadar.from_list([0.5, 0.5, 0.5])

    def test_compute_mean(self) -> None:
        """compute_mean 应正确计算 5 维均值。"""
        radar = CapabilityRadar(
            concept_understanding=0.8,
            code_engineering=0.6,
            logical_reasoning=0.7,
            error_resilience=0.5,
            time_management=0.4,
        )
        expected = (0.8 + 0.6 + 0.7 + 0.5 + 0.4) / 5.0
        assert abs(radar.compute_mean() - expected) < 0.001

    def test_describe_contains_labels(self) -> None:
        """describe 应包含各维度名称与评级标签。"""
        radar = CapabilityRadar(
            concept_understanding=0.9,
            code_engineering=0.3,
            logical_reasoning=0.7,
            error_resilience=0.5,
            time_management=0.2,
        )
        desc = radar.describe()
        assert "概念理解力" in desc
        assert "代码工程力" in desc
        assert "逻辑推理力" in desc
        assert "错题抗挫力" in desc
        assert "时间管理力" in desc
        # 0.9 应对应优秀标签
        assert "优秀" in desc
        # 0.2 应对应亟需加强标签
        assert "亟需" in desc

    def test_serialization_roundtrip(self) -> None:
        """Pydantic 序列化往返应保持所有字段。"""
        radar = CapabilityRadar(
            concept_understanding=0.75,
            code_engineering=0.65,
            logical_reasoning=0.55,
            error_resilience=0.45,
            time_management=0.35,
        )
        json_str = radar.model_dump_json()
        restored = CapabilityRadar.model_validate_json(json_str)
        assert restored.concept_understanding == 0.75
        assert restored.time_management == 0.35


# ============================================================================
# 2. HysteresisStrategyController 测试
# ============================================================================

class TestHysteresisStrategyController:
    """控制论迟滞环决策树测试。"""

    @pytest.fixture
    def controller(self) -> HysteresisStrategyController:
        return HysteresisStrategyController()

    def test_standard_to_scaffold_downgrade(self, controller) -> None:
        """A_mix 跌破 0.40 且 C_fail >= 2 时应触发降级。"""
        result = controller.decide(
            a_mix=0.30,
            current_strategy=STRATEGY_STANDARD,
            fail_counter=2,
            boundary_miss_ema_sequence=[],
        )
        assert result == STRATEGY_SCAFFOLD

    def test_no_downgrade_if_fail_insufficient(self, controller) -> None:
        """A_mix < 0.40 但 C_fail < 2 时不应降级。"""
        result = controller.decide(
            a_mix=0.30,
            current_strategy=STRATEGY_STANDARD,
            fail_counter=1,
            boundary_miss_ema_sequence=[],
        )
        assert result == STRATEGY_STANDARD

    def test_no_downgrade_if_already_scaffold(self, controller) -> None:
        """已在 SCAFFOLD_HELP 时不应重复降级。"""
        result = controller.decide(
            a_mix=0.20,
            current_strategy=STRATEGY_SCAFFOLD,
            fail_counter=5,
            boundary_miss_ema_sequence=[],
        )
        # 不会重复降级，停留在 SCAFFOLD
        assert result == STRATEGY_SCAFFOLD

    def test_scaffold_to_standard_upgrade(self, controller) -> None:
        """A_mix > 0.75 时应从 SCAFFOLD_HELP 升级回 STANDARD_PATH。"""
        result = controller.decide(
            a_mix=0.80,
            current_strategy=STRATEGY_SCAFFOLD,
            fail_counter=0,
            boundary_miss_ema_sequence=[],
        )
        assert result == STRATEGY_STANDARD

    def test_scaffold_no_upgrade_if_below_threshold(self, controller) -> None:
        """A_mix 未超过 0.75 时应保持 SCAFFOLD_HELP。"""
        result = controller.decide(
            a_mix=0.70,
            current_strategy=STRATEGY_SCAFFOLD,
            fail_counter=0,
            boundary_miss_ema_sequence=[],
        )
        assert result == STRATEGY_SCAFFOLD

    def test_hysteresis_band_no_thrashing(self, controller) -> None:
        """在 0.40-0.75 的迟滞带内，不应在 SCAFFOLD 与 STANDARD 之间震荡。"""
        # 场景：学生在 0.39 降级后，回升到 0.41（仍在迟滞带内）
        result = controller.decide(
            a_mix=0.41,
            current_strategy=STRATEGY_SCAFFOLD,
            fail_counter=0,
            boundary_miss_ema_sequence=[],
        )
        # 应保持 SCAFFOLD_HELP（因为迟滞环要求冲破 T_high=0.75 才切换）
        assert result == STRATEGY_SCAFFOLD

    def test_edge_case_drill_detection(self, controller) -> None:
        """边界遗漏 EMA 连续 3 次走高时应触发 EDGE_CASE_DRILL。"""
        boundary_seq = [0.6, 0.65, 0.7]  # 全部 > 0.5
        result = controller.decide(
            a_mix=0.55,
            current_strategy=STRATEGY_STANDARD,
            fail_counter=0,
            boundary_miss_ema_sequence=boundary_seq,
        )
        assert result == STRATEGY_EDGE_CASE

    def test_edge_case_not_enough_history(self, controller) -> None:
        """边界遗漏 EMA 不足 3 次时应不触发 EDGE_CASE_DRILL。"""
        boundary_seq = [0.6, 0.65]  # 只有 2 次
        result = controller.decide(
            a_mix=0.55,
            current_strategy=STRATEGY_STANDARD,
            fail_counter=0,
            boundary_miss_ema_sequence=boundary_seq,
        )
        assert result == STRATEGY_STANDARD

    def test_edge_case_not_all_above_threshold(self, controller) -> None:
        """边界遗漏 EMA 不全超过 0.5 时不触发。"""
        boundary_seq = [0.6, 0.4, 0.7]  # 中间一次低于 0.5
        result = controller.decide(
            a_mix=0.55,
            current_strategy=STRATEGY_STANDARD,
            fail_counter=0,
            boundary_miss_ema_sequence=boundary_seq,
        )
        assert result == STRATEGY_STANDARD

    def test_edge_case_to_standard_recovery(self, controller) -> None:
        """EDGE_CASE_DRILL 状态下 A_mix > 0.75 应恢复到 STANDARD_PATH。"""
        result = controller.decide(
            a_mix=0.80,
            current_strategy=STRATEGY_EDGE_CASE,
            fail_counter=0,
            boundary_miss_ema_sequence=[],
        )
        assert result == STRATEGY_STANDARD


# ============================================================================
# 3. AssessmentReporterNode 核心流程测试
# ============================================================================

class TestAssessmentReporterNode:
    """AssessmentReporterNode 主节点的功能测试。"""

    def test_ema_radar_update_normal(
        self, assessor: AssessmentReporterNode, default_state: AgentState
    ) -> None:
        """正常行为数据的 EMA 雷达更新。"""
        inp = AssessmentInput(agent_state=default_state)
        out = assessor(inp)

        radar = out.agent_state.dynamic_profile.capability_radar
        assert len(radar) == 5
        assert all(0.0 <= v <= 1.0 for v in radar)

        # accuracy=0.8, code_pass=0.75, duration=1.0
        # 默认初始值 [0.5, 0.5, 0.5, 0.5, 0.5]
        # alpha=0.2: new = 0.2*score + 0.8*0.5
        # 概念理解力 score = 0.8 → 0.2*0.8 + 0.8*0.5 = 0.56
        assert radar[RADAR_DIM_CONCEPT] > 0.5  # 应上升
        assert radar[RADAR_DIM_CODE] > 0.5      # 应上升（code_pass=0.75）

    def test_ema_radar_update_low_ability(
        self, assessor: AssessmentReporterNode, low_ability_state: AgentState
    ) -> None:
        """低能力行为数据的 EMA 雷达应下降。"""
        inp = AssessmentInput(agent_state=low_ability_state)
        out = assessor(inp)

        radar = out.agent_state.dynamic_profile.capability_radar
        # accuracy=0.2, 初始=0.25(预设) → 0.2*0.2 + 0.8*0.25 = 0.24
        assert radar[RADAR_DIM_CONCEPT] < 0.26  # 应下降

    def test_strategy_downgrade_triggered(
        self, assessor: AssessmentReporterNode, low_ability_state: AgentState
    ) -> None:
        """低能力+连续失败应触发 SCAFFOLD_HELP 降级。"""
        inp = AssessmentInput(agent_state=low_ability_state)
        out = assessor(inp)

        assert out.agent_state.pedagogical_strategy == STRATEGY_SCAFFOLD

    def test_strategy_upgrade_recovery(
        self, assessor: AssessmentReporterNode, high_ability_state: AgentState
    ) -> None:
        """高能力水平应从 SCAFFOLD_HELP 恢复到 STANDARD_PATH。"""
        inp = AssessmentInput(agent_state=high_ability_state)
        out = assessor(inp)

        assert out.agent_state.pedagogical_strategy == STRATEGY_STANDARD

    def test_edge_case_drill_detection_integration(
        self, assessor: AssessmentReporterNode, boundary_miss_state: AgentState
    ) -> None:
        """边界遗漏连续走高应触发 EDGE_CASE_DRILL。"""
        inp = AssessmentInput(agent_state=boundary_miss_state)
        out = assessor(inp)

        assert out.agent_state.pedagogical_strategy == STRATEGY_EDGE_CASE

    def test_diagnostic_report_generated(
        self, assessor: AssessmentReporterNode, default_state: AgentState
    ) -> None:
        """每次评估都应生成诊断报告。"""
        inp = AssessmentInput(agent_state=default_state)
        out = assessor(inp)

        report = out.agent_state.dynamic_profile.diagnostic_report_md
        assert "学术能力综合评估报告" in report
        assert "能力雷达" in report or "概念理解力" in report
        assert "A_mix" in report
        assert "调控策略" in report

    def test_diagnostic_report_contains_strategy(
        self, assessor: AssessmentReporterNode, default_state: AgentState
    ) -> None:
        """诊断报告应包含当前策略名称。"""
        inp = AssessmentInput(agent_state=default_state)
        out = assessor(inp)

        report = out.agent_state.dynamic_profile.diagnostic_report_md
        assert STRATEGY_STANDARD in report

    def test_boundary_ema_sequence_maintained(
        self, assessor: AssessmentReporterNode, boundary_miss_state: AgentState
    ) -> None:
        """边界遗漏 EMA 序列应正确维护（不丢失历史）。"""
        previous_len = len(boundary_miss_state.dynamic_profile.boundary_miss_ema_sequence)

        inp = AssessmentInput(agent_state=boundary_miss_state)
        out = assessor(inp)

        new_seq = out.agent_state.dynamic_profile.boundary_miss_ema_sequence
        assert len(new_seq) >= previous_len  # 至少不缩短
        assert all(0.0 <= v <= 1.0 for v in new_seq)

    def test_boundary_ema_truncation(self, assessor: AssessmentReporterNode) -> None:
        """边界遗漏 EMA 序列超过 10 轮应截断为最近 10 轮。"""
        state = AgentState(user_id="U5", course_id="CS101")
        state.latest_behavior = LatestBehavior(
            node_id="N_GRAPH",
            accuracy_rate=0.5,
            error_types=["boundary_miss"],
        )
        state.dynamic_profile.boundary_miss_ema_sequence = [0.5] * 12

        inp = AssessmentInput(agent_state=state)
        out = assessor(inp)

        seq = out.agent_state.dynamic_profile.boundary_miss_ema_sequence
        assert len(seq) <= 10

    def test_strategy_no_unnecessary_change(
        self, assessor: AssessmentReporterNode, default_state: AgentState
    ) -> None:
        """正常能力水平不应触发策略切换。"""
        inp = AssessmentInput(agent_state=default_state)
        out = assessor(inp)

        assert out.agent_state.pedagogical_strategy == STRATEGY_STANDARD

    def test_missing_behavior_handled_gracefully(self, assessor: AssessmentReporterNode) -> None:
        """latest_behavior 为空时应平稳降级为默认值。"""
        state = AgentState(user_id="U6", course_id="CS101")
        state.latest_behavior = None
        state.dynamic_profile.capability_radar = [0.5, 0.5, 0.5, 0.5, 0.5]

        inp = AssessmentInput(agent_state=state)
        out = assessor(inp)

        radar = out.agent_state.dynamic_profile.capability_radar
        assert len(radar) == 5
        # 应有诊断报告
        assert len(out.agent_state.dynamic_profile.diagnostic_report_md) > 0

    def test_missing_capability_radar_initialized(
        self, assessor: AssessmentReporterNode, default_state: AgentState
    ) -> None:
        """capability_radar 缺失时应自动初始化为中性值。"""
        # 清空现有雷达
        default_state.dynamic_profile.capability_radar = []

        inp = AssessmentInput(agent_state=default_state)
        out = assessor(inp)

        radar = out.agent_state.dynamic_profile.capability_radar
        assert len(radar) == 5
        assert all(0.0 <= v <= 1.0 for v in radar)


# ============================================================================
# 4. 参数校验测试
# ============================================================================

class TestAssessmentParameterValidation:
    """参数校验与边界条件测试。"""

    def test_default_alpha(self) -> None:
        """默认 alpha=0.2 应被接受。"""
        node = AssessmentReporterNode(alpha=0.2)
        assert node.alpha == 0.2

    def test_alpha_too_low_raises(self) -> None:
        """alpha <= 0 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            AssessmentReporterNode(alpha=0.0)
        with pytest.raises(ValueError):
            AssessmentReporterNode(alpha=-0.1)

    def test_alpha_too_high_raises(self) -> None:
        """alpha > 1 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            AssessmentReporterNode(alpha=1.1)

    def test_alpha_equal_one_accepted(self) -> None:
        """alpha=1.0 应被接受（完全不平滑）。"""
        node = AssessmentReporterNode(alpha=1.0)
        assert node.alpha == 1.0

    def test_thresholds_invalid_raises(self) -> None:
        """t_low >= t_high 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            AssessmentReporterNode(t_low=0.5, t_high=0.5)
        with pytest.raises(ValueError):
            AssessmentReporterNode(t_low=0.8, t_high=0.4)

    def test_custom_thresholds_accepted(self) -> None:
        """自定义合法阈值应被接受。"""
        node = AssessmentReporterNode(t_low=0.35, t_high=0.80)
        assert node.t_low == 0.35
        assert node.t_high == 0.80


# ============================================================================
# 5. 工厂函数测试
# ============================================================================

class TestAssessmentFactory:
    """create_assessment_node 工厂函数测试。"""

    def test_create_assessment_node_default(self) -> None:
        """默认参数创建的节点应使用默认值。"""
        node = create_assessment_node()
        assert isinstance(node, AssessmentReporterNode)
        assert node.alpha == 0.2
        assert node.t_low == 0.40
        assert node.t_high == 0.75

    def test_create_assessment_node_custom(self) -> None:
        """自定义参数应正确传递。"""
        node = create_assessment_node(alpha=0.3, t_low=0.35, t_high=0.85)
        assert node.alpha == 0.3
        assert node.t_low == 0.35
        assert node.t_high == 0.85
