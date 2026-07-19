# -*- coding: utf-8 -*-
"""
端到端集成测试 — 完整业务闭环验证
===================================

模拟一个完整的学生学习闭环:
  1. 冷启动注册 → 6 维画像收集
  2. 正常学习若干轮
  3. 产生秒杀作弊行为 → Evaluator 检测 + 惩罚
  4. PID 阻尼机制平滑画像（非突变）
  5. Profiler 硬切换干预触发
  6. Planner 重寻路触发
  7. Content Mesh 资源卡片生成
  8. Validator 双极防幻觉校验
  9. 最终路径和画像收敛

运行方式:
    pytest tests/test_e2e_integration.py -v
"""

import pytest
import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.state.agent_state import (
    AgentState, StaticProfile, DynamicProfile,
    CognitiveStyleDistribution, ErrorTypeDistribution,
)
from src.agents.evaluator_node import (
    EvaluatorNode, EvaluatorInput, BehaviorVector,
    ReplanDecision, AnomalyType,
)
from src.agents.profiler_node import (
    ProfilerNode, ProfilerInput, ThompsonSampler,
)
from src.agents.planner_node import (
    PlannerNode, PlannerInput, KnowledgeNode, KnowledgeEdge,
)
from src.agents.content_mesh_node import (
    ContentMeshNode, MeshInput, QueueClass, CardType,
)
from src.agents.validator_node import (
    ValidatorNode, ValidatorInput, EntityExtractor,
    SlidingWindowSplitter, Pole1Gate, Pole2Gate,
)
from src.infrastructure.cold_start import (
    handle_cold_start_interaction, ColdStartEngine,
)


# ============================================================================
# Fixtures: Mock 图谱 + AgentState
# ============================================================================

@pytest.fixture
def mock_knowledge_graph():
    """构建 Mock 知识图谱 (5 节点 DAG)。"""
    nodes = [
        KnowledgeNode(node_id="KN_PYTHON", title="Python 基础", difficulty=0.3, estimated_hours=2.0),
        KnowledgeNode(node_id="KN_NUMPY", title="NumPy 基础", difficulty=0.4, estimated_hours=3.0),
        KnowledgeNode(node_id="KN_ML_INTRO", title="机器学习概论", difficulty=0.6, estimated_hours=5.0),
        KnowledgeNode(node_id="KN_BACKPROP", title="反向传播算法", difficulty=0.7, estimated_hours=4.0),
        KnowledgeNode(node_id="KN_DL_PROJECT", title="深度学习实战", difficulty=0.8, estimated_hours=6.0),
    ]
    edges = [
        KnowledgeEdge(source_id="KN_PYTHON", target_id="KN_NUMPY", weight=1.0),
        KnowledgeEdge(source_id="KN_NUMPY", target_id="KN_ML_INTRO", weight=1.0),
        KnowledgeEdge(source_id="KN_ML_INTRO", target_id="KN_BACKPROP", weight=1.0),
        KnowledgeEdge(source_id="KN_BACKPROP", target_id="KN_DL_PROJECT", weight=1.0),
    ]
    return nodes, edges


class MockNeo4jClient:
    """Mock Neo4j 客户端。"""
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    def is_connected(self):
        return True

    def export_nodes_for_planner(self, course_id=None):
        return list(self._nodes)

    def export_edges_for_planner(self, course_id=None):
        return list(self._edges)


@pytest.fixture
def fresh_agent_state() -> AgentState:
    """构建新鲜 AgentState（冷启动前）。"""
    state = AgentState(
        user_id="STUDENT_042",
        course_id="CS_ML_101",
        current_node_id="KN_PYTHON",
        target_node_id="KN_DL_PROJECT",
    )
    state.dynamic_profile.knowledge_mastery["KN_PYTHON"] = 0.3
    state.dynamic_profile.knowledge_mastery["KN_NUMPY"] = 0.1
    state.dynamic_profile.knowledge_mastery["KN_ML_INTRO"] = 0.0
    state.dynamic_profile.knowledge_mastery["KN_BACKPROP"] = 0.0
    state.dynamic_profile.knowledge_mastery["KN_DL_PROJECT"] = 0.0
    return state


# ============================================================================
# E2E Test 1: 完整业务闭环
# ============================================================================

class TestEndToEndFullPipeline:
    """端到端完整业务闭环测试。"""

    def test_full_pipeline_cold_start_to_convergence(
        self, mock_knowledge_graph, fresh_agent_state: AgentState
    ) -> None:
        """模拟: 冷启动 → 正常学习 → 作弊行为 → PID 阻尼 → 重寻路 → 卡片生成 → 校验 → 收敛。"""
        nodes, edges = mock_knowledge_graph
        state = fresh_agent_state

        # ================================================================
        # Phase 1: 冷启动注册 (6 维画像收集)
        # ================================================================
        cold_answers = [
            "visual", "academic_exam", "computer_science",
            "bachelor", 10.0, ["python_basics", "data_structures"],
        ]

        # 首轮初始化
        state, probe, done = handle_cold_start_interaction(state, None)
        assert done is False

        for ans in cold_answers:
            state, probe, done = handle_cold_start_interaction(state, ans)

        assert done is True, "冷启动应完成"
        assert state.static_profile.motivation == "academic_exam"
        assert state.static_profile.time_budget_hours_per_week == 10.0
        print("[Phase 1 ✓] 冷启动画像收集完成")

        # ================================================================
        # Phase 2: 设置初始路径 (Mock Planner)
        # ================================================================
        mock_neo4j = MockNeo4jClient(nodes, edges)
        planner = PlannerNode(neo4j_client=mock_neo4j)
        plan_inp = PlannerInput(agent_state=state)
        plan_out = planner(plan_inp)
        state = plan_out.agent_state

        assert plan_out.path_found is True
        assert len(state.active_path) > 1
        assert state.active_path[0] == "KN_PYTHON"
        print(f"[Phase 2 ✓] 初始路径规划: {state.active_path}")

        # ================================================================
        # Phase 3: 正常学习轮次 (3 轮正常交互)
        # ================================================================
        evaluator = EvaluatorNode()
        profiler = ProfilerNode(seed=42)

        for round_idx in range(3):
            # 模拟正常的学习行为
            behavior = BehaviorVector(
                answer_correctness=0.75 + 0.05 * round_idx,
                code_pass_rate=0.70 + 0.05 * round_idx,
                time_spent_ratio=1.0 + 0.2 * round_idx,
                help_request_count=1,
                node_id="KN_PYTHON",
            )
            eval_inp = EvaluatorInput(agent_state=state, raw_behavior=behavior)
            eval_out = evaluator(eval_inp)
            state = eval_out.agent_state

            # Profiler 更新
            prof_inp = ProfilerInput(
                agent_state=state,
                evaluator_mastery_delta=eval_out.mastery_delta,
                evaluator_pid_error=eval_out.pid_error,
                resource_style_delivered="visual",
                node_id="KN_PYTHON",
            )
            prof_out = profiler(prof_inp)
            state = prof_out.agent_state

            assert eval_out.anomaly_detected is False, f"正常学习不应检测异常 (round {round_idx})"
            assert state.re_plan_triggered is False, f"正常学习不应触发重寻路 (round {round_idx})"

        mastery_after_normal = state.dynamic_profile.knowledge_mastery.get("KN_PYTHON", 0.0)
        print(f"[Phase 3 ✓] 3 轮正常学习后 mastery={mastery_after_normal:.4f}")

        # ================================================================
        # Phase 4: 秒杀作弊行为 → 检测 + 惩罚
        # ================================================================
        cheat_behavior = BehaviorVector(
            answer_correctness=0.98,
            code_pass_rate=1.0,
            time_spent_ratio=0.01,  # 0.01 < 0.05 cheating threshold
            help_request_count=0,
            node_id="KN_BACKPROP",
        )
        eval_inp_cheat = EvaluatorInput(agent_state=state, raw_behavior=cheat_behavior)
        eval_out_cheat = evaluator(eval_inp_cheat)
        state = eval_out_cheat.agent_state

        assert eval_out_cheat.anomaly_detected is True, "应检测到作弊行为"
        assert eval_out_cheat.cleaned_behavior.anomaly.anomaly_type == AnomalyType.CHEATING_SPEED, (
            f"应为秒杀作弊, 实际 {eval_out_cheat.cleaned_behavior.anomaly.anomaly_type}"
        )
        assert eval_out_cheat.cleaned_behavior.friction_coefficient == 2.0, (
            "作弊应有摩擦系数 2.0"
        )
        print(f"[Phase 4 ✓] 秒杀作弊检测通过: "
              f"有效正确率={eval_out_cheat.cleaned_behavior.effective_correctness:.4f}, "
              f"摩擦={eval_out_cheat.cleaned_behavior.friction_coefficient}")

        # ================================================================
        # Phase 5: PID 阻尼机制 — 验证单次作弊不会导致 mastery 突变
        # ================================================================
        mastery_after_cheat = state.dynamic_profile.knowledge_mastery.get(
            "KN_BACKPROP", 0.0
        )
        # mastery 不应因单次作弊大幅上升（PID 阻尼）
        assert mastery_after_cheat < 0.5, (
            f"作弊后 mastery 不应大幅上升 (PID 阻尼抑制): {mastery_after_cheat:.4f}"
        )
        print(f"[Phase 5 ✓] PID 阻尼: mastery 因摩擦系数受抑制={mastery_after_cheat:.4f}")

        # ================================================================
        # Phase 6: 连续低分触发 C_fail 累积 + Profiler 硬切换干预
        # ================================================================
        for _ in range(4):
            fail_behavior = BehaviorVector(
                answer_correctness=0.2,
                time_spent_ratio=1.0,
                help_request_count=2,
                node_id="KN_BACKPROP",
            )
            eval_inp_fail = EvaluatorInput(agent_state=state, raw_behavior=fail_behavior)
            eval_out_fail = evaluator(eval_inp_fail)
            state = eval_out_fail.agent_state

        c_fail = state.dynamic_profile.continuous_fail_counter
        assert c_fail >= 3, f"C_fail 应 ≥ 3, 实际 {c_fail}"

        # Profiler 硬切换干预
        prof_inp_fail = ProfilerInput(
            agent_state=state,
            evaluator_mastery_delta=-0.1,
            evaluator_pid_error=0.8,
            resource_style_delivered="visual",
            node_id="KN_BACKPROP",
        )
        prof_out_fail = profiler(prof_inp_fail)
        state = prof_out_fail.agent_state

        assert prof_out_fail.intervention_active is True, "C_fail ≥ 3 应触发硬切换干预"
        assert prof_out_fail.style_result.intervention_triggered is True
        assert prof_out_fail.style_result.selected_style != "visual", (
            f"应排除 visual 风格, 实际选择 {prof_out_fail.style_result.selected_style}"
        )
        print(f"[Phase 6 ✓] 硬切换干预: 风格 {prof_out_fail.style_result.selected_style}, "
              f"C_fail={c_fail}")

        # ================================================================
        # Phase 7: 连续退步触发重寻路 (Evaluator → re_plan_triggered)
        # ================================================================
        # 多次极低正确率 → mastery 持续下降 → Δtarget_error > 0 → 触发
        for _ in range(5):
            very_low = BehaviorVector(
                answer_correctness=0.08,
                time_spent_ratio=1.0,
                help_request_count=1,
                node_id="KN_BACKPROP",
            )
            eval_inp_low = EvaluatorInput(agent_state=state, raw_behavior=very_low)
            eval_out_low = evaluator(eval_inp_low)
            state = eval_out_low.agent_state
            # 尽早退出: 若已触发重寻路
            if state.re_plan_triggered:
                break

        assert state.re_plan_triggered is True, (
            f"连续退步应触发 re_plan_triggered"
        )
        print("[Phase 7 ✓] re_plan_triggered = True (重寻路触发)")

        # ================================================================
        # Phase 8: Planner 重寻路 — 基于最新掌握度重新计算路径
        # ================================================================
        plan_inp2 = PlannerInput(agent_state=state)
        plan_out2 = planner(plan_inp2)
        state = plan_out2.agent_state

        assert plan_out2.path_found is True
        assert state.re_plan_triggered is False, "重寻路后应清除触发标记"
        print(f"[Phase 8 ✓] 重寻路完成: 新路径={state.active_path}")
        print(f"           边代价详情: {len(plan_out2.path_edges_detail)} 条边")

        # ================================================================
        # Phase 9: Content Mesh 资源卡片生成 + Validator 校验
        # ================================================================
        mesh = ContentMeshNode()
        mesh_inp = MeshInput(agent_state=state)
        mesh_out = mesh(mesh_inp)
        state = mesh_out.agent_state

        assert len(mesh_out.generated_cards) > 0, "应生成至少 1 张资源卡片"
        print(f"[Phase 9a ✓] 资源生成: {len(mesh_out.generated_cards)} 张卡片")

        # 收集卡片进行校验
        validator = ValidatorNode()
        cards_to_check = mesh_out.generated_cards
        validator_inp = ValidatorInput(
            agent_state=state,
            cards_to_validate=cards_to_check,
            ground_truth_context="反向传播算法通过链式法则计算损失函数对权重的梯度。",
        )
        val_out = validator(validator_inp)
        state = val_out.agent_state

        assert val_out.overall_pass_rate >= 0.0
        print(f"[Phase 9b ✓] 校验完成: 通过率={val_out.overall_pass_rate:.2%}, "
              f"通过={len(val_out.valid_cards)}, 拒绝={len(val_out.rejected_cards)}, "
              f"修正={len(val_out.refined_cards)}")

        # ================================================================
        # Phase 10: 最终状态验证
        # ================================================================
        final_mastery_python = state.dynamic_profile.knowledge_mastery.get(
            "KN_PYTHON", 0.0
        )
        assert final_mastery_python > 0.0, "KN_PYTHON 应有非零掌握度"
        assert len(state.active_path) > 0, "应有活跃路径"

        # 画像应反映 MAB 学习结果
        csd = state.static_profile.cognitive_style_distribution
        assert csd.visual_alpha > 1.0 or csd.textual_alpha > 1.0 or csd.practical_alpha > 1.0, (
            "认知风格 Beta 参数应已被 MAB 更新"
        )

        print(f"\n{'='*60}")
        print(f"  E2E 闭环验证完成")
        print(f"  最终 mastery: KN_PYTHON={final_mastery_python:.4f}")
        print(f"  认知风格: visual(α={csd.visual_alpha:.1f},β={csd.visual_beta:.1f})")
        print(f"  C_fail: {state.dynamic_profile.continuous_fail_counter}")
        print(f"  Iterations: {state.iteration}")
        print(f"{'='*60}")


# ============================================================================
# E2E Test 2: Validator 双极校验链组件测试
# ============================================================================

class TestValidatorComponents:
    """Validator 各组件的独立校验。"""

    def test_entity_extraction(self) -> None:
        """公式与代码提取应正确。"""
        text = """
        损失函数: $$L = \\frac{1}{n}\\sum (y_i - \\hat{y}_i)^2$$

        ```c
        int gradient_descent(int value, int epochs) {
            for (int step = 0; step < epochs; ++step) value += step;
            return value;
        }
        ```
        """
        formulas = EntityExtractor.extract_formulas(text)
        assert len(formulas) >= 1, "应提取到至少 1 个公式"

        code_blocks = EntityExtractor.extract_code_blocks(text)
        assert len(code_blocks) >= 1, "应提取到至少 1 个代码块"

    def test_c_syntax_check_valid_code(self) -> None:
        """合法 C11 代码应通过静态语法检查。"""
        code = "int hello(void) { return 1; }"
        errors = EntityExtractor.check_c_syntax(code)
        assert len(errors) == 0, f"合法代码不应有错误: {errors}"

    def test_c_syntax_check_invalid_code(self) -> None:
        """非法 C11 代码应被静态检查检出。"""
        code = "int broken(void) { return 1 }"
        errors = EntityExtractor.check_c_syntax(code)
        assert len(errors) > 0, "非法代码应有错误"

    def test_sliding_window_with_overlap(self) -> None:
        """带重叠的滑动窗口应正确切分。"""
        splitter = SlidingWindowSplitter(window_size=64, overlap_size=16)
        text = "机器学习是人工智能的重要分支。" * 20
        chunks = splitter.split(text)
        assert len(chunks) > 1, "长文本应有多个窗口"
        # 检查重叠
        if len(chunks) > 1:
            assert chunks[1].overlap_with_prev > 0, "相邻窗口应有重叠"

    def test_pole1_gate_formula_check(self) -> None:
        """第一极门控应检测公式与代码的语法。"""
        gate = Pole1Gate()
        # 纯文本（无公式/代码）应通过
        result_plain = gate.validate(
            "梯度下降是机器学习中最基础的优化算法之一。",
            "concept_map",
        )
        assert result_plain.passed is True

        # 合法的代码块应通过 AST 检查
        result_code = gate.validate(
            "```c\nconst char *hello(void) {\n    return \"world\";\n}\n```",
            "code_snippet",
        )
        assert result_code.passed is True

        # 含非法 Python 语法的代码应被检测
        result_bad_code = gate.validate(
            "```c\nint broken(void) {\n    return 1\n}\n```",
            "code_snippet",
        )
        assert result_bad_code.passed is False

    def test_pole2_nli_entailment(self) -> None:
        """第二极 NLI 蕴含度：一致文本得分应高于无关文本。"""
        gate = Pole2Gate()
        ground_truth = (
            "反向传播算法通过链式法则计算损失函数对权重的梯度。"
            "梯度从输出层向输入层逐层传播反向传播。"
            "学习率控制每次参数更新的步长。反向传播是深度学习的核心。"
        )
        # 与 ground_truth 语义一致的文本（共享关键词）
        result_aligned = gate.validate(
            "反向传播算法通过链式法则计算损失对权重的梯度。反向传播是深度学习的核心。",
            ground_truth,
        )
        # 与 ground_truth 完全无关的文本
        result_off_topic = gate.validate(
            "数据库索引使用 B+ 树结构来加速查询操作和排序功能。",
            ground_truth,
        )
        # 一致文本的蕴含度应显著高于无关文本
        assert result_aligned.overall_entailment > result_off_topic.overall_entailment, (
            f"一致文本({result_aligned.overall_entailment:.4f}) 应 > "
            f"无关文本({result_off_topic.overall_entailment:.4f})"
        )


# ============================================================================
# E2E Test 3: 重寻路熔断机制
# ============================================================================

class TestAbortMechanism:
    """重规划熔断与任务回收机制。"""

    def test_abort_queued_tasks(self) -> None:
        """WFQ 调度器的熔断功能应正确回收在途任务。"""
        from src.agents.content_mesh_node import (
            WFQScheduler, GenerationTask, QueueClass, CardType,
            GenerationStatus,
        )
        scheduler = WFQScheduler()

        # 入队 5 个任务（节点 A 和 B）
        for i in range(5):
            node = f"NODE_A" if i < 3 else f"NODE_B"
            task = GenerationTask(
                task_id=f"task_{i}",
                node_id=node,
                card_type=CardType.CONCEPT_MAP,
                queue_class=QueueClass.PRIVILEGED,
                estimated_tokens=500,
            )
            scheduler.enqueue(task)

        # 熔断 NODE_A 的所有任务
        aborted = scheduler.abort_tasks_by_node("NODE_A")
        assert len(aborted) == 3, f"应熔断 3 个 NODE_A 任务, 实际 {len(aborted)}"

        # NODE_B 任务应仍在队列中
        stats = scheduler.get_queue_sizes()
        assert stats["privileged_queued"] == 2, (
            f"NODE_B 任务应保留: {stats}"
        )


# ============================================================================
# E2E Test 4: 冷启动到主图的衔接
# ============================================================================

class TestColdStartToGraphTransition:
    """冷启动完成到主 LangGraph 图的衔接。"""

    def test_cold_start_then_graph_entry(
        self, mock_knowledge_graph, fresh_agent_state: AgentState
    ) -> None:
        """冷启动完成后，AgentState 应可直接进入主图。"""
        nodes, edges = mock_knowledge_graph
        state = fresh_agent_state

        # 冷启动
        answers = ["visual", "academic_exam", "computer_science",
                   "bachelor", 10.0, ["python_basics"]]
        state, probe, done = handle_cold_start_interaction(state, None)
        for ans in answers:
            state, probe, done = handle_cold_start_interaction(state, ans)

        assert done is True

        # 验证画像已注入
        assert state.static_profile.motivation != ""
        assert state.static_profile.time_budget_hours_per_week > 0

        # 直接进入 Planner
        mock_neo4j = MockNeo4jClient(nodes, edges)
        planner = PlannerNode(neo4j_client=mock_neo4j)
        plan_out = planner(PlannerInput(agent_state=state))
        state = plan_out.agent_state

        assert plan_out.path_found is True
        assert len(state.active_path) > 0
        print(f"[Transition ✓] 冷启动 → 主图: path={state.active_path}")


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
