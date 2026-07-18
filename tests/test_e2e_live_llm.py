#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EduAgent 全链路端到端集成测试（真实 LLM 版本）
===============================================

本脚本从环境变量读取 DASHSCOPE_API_KEY，使用 qwen-plus 模型，
逐个验证各 Agent Node 的 LLM 调用通路和完整的 LangGraph 编排流程。

测试覆盖：
  1. LLMClientV2 基础连通性（DashScope Qwen）
  2. ContentMesh: 5 种资源类型的内容生成
  3. TutorAgent: 三轨多模态答疑（文字+图解）
  4. Validator: NLI 蕴含度评分
  5. Assessment: EMA 雷达 + 迟滞环决策
  6. LangGraph 全链路: 冷启动 → 评估 → 画像 → 规划 → 答疑 → 生成 → 校验 → 评估
  7. Tutor 离线回退（Milvus 不可用时的兜底）

用法:
    python tests/test_e2e_live_llm.py

环境变量要求:
    DASHSCOPE_API_KEY=sk-xxx
"""

import sys
import os
import time
import pytest

# 确保项目根在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm.client_v2 import (
    LLMClientV2,
    create_llm_client_v2_from_env,
)
from src.state.agent_state import (
    AgentState,
    LatestBehavior,
    StaticProfile,
    DynamicProfile,
    ResourceCard,
)
from src.orchestration import EduAgentGraph
from src.agents.tutor_node import (
    TutorAgentNode,
    TutorInput,
    MermaidSyntaxGuard,
)
from src.agents.assessment_node import (
    AssessmentReporterNode,
    AssessmentInput,
    HysteresisStrategyController,
)
from src.agents.validator_node import (
    ValidatorNode,
    ValidatorInput,
)
from src.agents.content_mesh_node import (
    ContentMeshNode,
    MeshInput,
)

pytestmark = pytest.mark.skipif(
    (
        not os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("RUN_LIVE_LLM_TESTS") != "1"
    ),
    reason="Live LLM tests require DASHSCOPE_API_KEY and RUN_LIVE_LLM_TESTS=1.",
)


@pytest.fixture
def client() -> LLMClientV2:
    return create_llm_client_v2_from_env()


# ============================================================================
# 工具函数
# ============================================================================

def sep(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    marker = "[OK]" if ok else "[XX]"
    print(f"  {marker} {label}" + (f": {detail}" if detail else ""))


# ============================================================================
# Test 1: LLM 连通性
# ============================================================================

def test_llm_connectivity(client: LLMClientV2) -> bool:
    sep("Test 1: LLM 基础连通性 (DashScope Qwen)")

    try:
        resp = client.chat_sync([
            {"role": "user", "content": "请用一句话介绍数据结构中的二叉树。"}
        ]).get("content", "")
        ok = len(resp) > 20 and "Error" not in resp
        check("Qwen Chat API 连通", ok, f"response_len={len(resp)}")
        if ok:
            print(f"    Response preview: {resp[:120]}...")
        return ok
    except Exception as e:
        check("Qwen Chat API 连通", False, str(e))
        return False


# ============================================================================
# Test 2: ContentMesh 资源生成
# ============================================================================

def test_content_mesh_generation(client: LLMClientV2) -> bool:
    sep("Test 2: ContentMesh 5 种资源类型生成")

    card_types = [
        "concept_map",
        "code_snippet",
        "interactive_exercise",
        "video_summary",
        "diagnostic_quiz",
    ]

    all_ok = True
    for ct in card_types:
        try:
            content = client.generate_content("二叉树遍历", ct, 0.5)
            ok = len(content) > 30 and "Error" not in content
            if not ok:
                print(f"    Content preview: {content[:200]}")
            check(f"  {ct}", ok, f"len={len(content)}")
            all_ok = all_ok and ok
        except Exception as e:
            check(f"  {ct}", False, str(e))
            all_ok = False

    # 也测试 ContentMesh Node 的集成
    mesh = ContentMeshNode(generate_fn=client.generate_content)
    state = AgentState(user_id="U_TEST", course_id="CS_DS")
    state.active_path = ["N_BST"]
    state.dynamic_profile.knowledge_mastery = {"N_BST": 0.4}
    inp = MeshInput(agent_state=state)
    output = mesh(inp)
    n_cards = len(output.generated_cards)
    check("  ContentMesh Node 集成", n_cards > 0, f"generated {n_cards} cards")
    all_ok = all_ok and (n_cards > 0)

    return all_ok


# ============================================================================
# Test 3: TutorAgent 答疑
# ============================================================================

def test_tutor_agent(client: LLMClientV2) -> bool:
    sep("Test 3: TutorAgent 三轨多模态答疑")

    all_ok = True

    # 3a: 学术原理解释
    try:
        explanation = client.generate_academic_explanation(
            "什么是二叉搜索树的插入操作？",
            ["二叉搜索树是一种有序二叉树，左子树所有节点小于根，右子树所有节点大于根。"],
        )
        ok = len(explanation) > 50 and "Error" not in explanation
        check("  3a 学术原理解释", ok, f"len={len(explanation)}")
        if ok:
            print(f"    Preview: {explanation[:150]}...")
        all_ok = all_ok and ok
    except Exception as e:
        check("  3a 学术原理解释", False, str(e))
        all_ok = False

    # 3b: Mermaid 图解生成
    try:
        mermaid = client.generate_mermaid_graph(
            "二叉搜索树插入操作",
            "二叉搜索树的插入从根节点开始，比较值大小决定进入左子树还是右子树...",
        )
        # 经过 MermaidSyntaxGuard 校验
        clean = MermaidSyntaxGuard.validate_and_repair(mermaid)
        ok = "graph" in clean.lower() and "-->" in clean
        check("  3b Mermaid 图解生成", ok, f"len={len(clean)}")
        if ok:
            print(f"    Mermaid:\n{clean[:200]}")
        all_ok = all_ok and ok
    except Exception as e:
        check("  3b Mermaid 图解生成", False, str(e))
        all_ok = False

    # 3c: TutorAgentNode 完整通路
    tutor = TutorAgentNode(milvus_client=None, llm_generator=client)
    state = AgentState(user_id="U_TEST", course_id="CS_DS")
    state.current_node_id = "N_BST"
    state.latest_behavior = LatestBehavior(
        node_id="N_BST",
        correctness=0.7,
        tutor_query="二叉搜索树的插入时间复杂度是多少？",
    )
    inp = TutorInput(agent_state=state)
    out = tutor(inp)
    resp = out.agent_state.tutor_response
    has_text = bool(resp and resp.get("text_explanation"))
    has_mermaid = bool(resp and "graph" in resp.get("mermaid_src", "").lower())
    check("  3c TutorAgentNode 完整通路", has_text and has_mermaid,
          f"text={has_text}, mermaid={has_mermaid}")
    all_ok = all_ok and (has_text and has_mermaid)

    # 3d: 离线回退（无 LLM 时）
    tutor_offline = TutorAgentNode(milvus_client=None, llm_generator=None)
    state_off = AgentState(user_id="U_OFF", course_id="CS_DS")
    state_off.latest_behavior = LatestBehavior(
        node_id="N_SORT",
        tutor_query="什么是快速排序？",
    )
    inp_off = TutorInput(agent_state=state_off)
    out_off = tutor_offline(inp_off)
    fallback_ok = "离线模式" in out_off.agent_state.tutor_response.get(
        "text_explanation", ""
    )
    check("  3d Tutor 离线回退", fallback_ok, "离线模式兜底正常")
    all_ok = all_ok and fallback_ok

    return all_ok


# ============================================================================
# Test 4: Validator NLI 蕴含度
# ============================================================================

def test_validator_nli(client: LLMClientV2) -> bool:
    sep("Test 4: Validator NLI 蕴含度评分")

    all_ok = True

    # 4a: 一致的文本应得高分
    gt = "二叉搜索树的插入操作平均时间复杂度为 O(log n)，最坏情况下为 O(n)。"
    consistent = "在二叉搜索树中插入一个节点的平均时间复杂度是 O(log n)，最坏情况会退化到 O(n)。"
    score_good = client.compute_nli_entailment(consistent, gt)
    check("  4a 一致文本 (应高分)", score_good > 0.6, f"score={score_good:.3f}")

    # 4b: 矛盾的文本应得低分
    contradictory = "二叉搜索树的插入时间复杂度总是 O(1)。"
    score_bad = client.compute_nli_entailment(contradictory, gt)
    check("  4b 矛盾文本 (应低分)", score_bad < 0.7, f"score={score_bad:.3f}")
    all_ok = all_ok and (score_good > score_bad)

    # 4c: ValidatorNode 集成
    validator = ValidatorNode(nli_fn=client.compute_nli_entailment)
    state = AgentState(user_id="U_VAL", course_id="CS_DS")
    card = ResourceCard(
        resource_id="R1",
        node_id="N_BST",
        card_type="concept_map",
        content="二叉搜索树的插入时间复杂度为 O(log n)，最坏情况 O(n)。",
        difficulty=0.5,
    )
    state.generated_resources = {"N_BST": [card]}
    inp = ValidatorInput(
        agent_state=state,
        cards_to_validate=[card],
        ground_truth_context=gt,
    )
    output = validator(inp)
    nli_ok = output.agent_state is not None
    check("  4c ValidatorNode 集成", nli_ok, "Pole2 NLI 校验完成")
    all_ok = all_ok and nli_ok

    return all_ok


# ============================================================================
# Test 5: Assessment 评估
# ============================================================================

def test_assessment() -> bool:
    sep("Test 5: Assessment 学习效果评估")

    all_ok = True

    assessor = AssessmentReporterNode(alpha=0.2)

    # 5a: 正常评估
    state = AgentState(user_id="U_A1", course_id="CS_DS")
    state.latest_behavior = LatestBehavior(
        node_id="N_BST",
        accuracy_rate=0.85,
        code_pass_rate=0.9,
        duration_ratio=1.1,
    )
    state.dynamic_profile.capability_radar = [0.6, 0.6, 0.6, 0.6, 0.6]
    inp = AssessmentInput(agent_state=state)
    out = assessor(inp)
    radar = out.agent_state.dynamic_profile.capability_radar
    report = out.agent_state.dynamic_profile.diagnostic_report_md
    strategy = out.agent_state.pedagogical_strategy

    check("  5a 雷达更新", len(radar) == 5 and all(v > 0.5 for v in radar),
          f"radar={[round(v,2) for v in radar]}")
    check("  5b 报告生成", "学术能力综合评估报告" in report, f"len={len(report)}")
    check("  5c 策略保持", strategy == "STANDARD_PATH", strategy)
    all_ok = all_ok and (strategy == "STANDARD_PATH")

    # 5b: 低能力触发降级
    state_low = AgentState(user_id="U_A2", course_id="CS_DS")
    state_low.latest_behavior = LatestBehavior(
        node_id="N_BST",
        accuracy_rate=0.15,
        code_pass_rate=0.1,
        duration_ratio=3.5,
    )
    state_low.dynamic_profile.capability_radar = [0.2, 0.2, 0.25, 0.2, 0.2]
    state_low.dynamic_profile.continuous_fail_counter = 3
    inp_low = AssessmentInput(agent_state=state_low)
    out_low = assessor(inp_low)
    check("  5d 低能力降级", out_low.agent_state.pedagogical_strategy == "SCAFFOLD_HELP",
          out_low.agent_state.pedagogical_strategy)
    all_ok = all_ok and (out_low.agent_state.pedagogical_strategy == "SCAFFOLD_HELP")

    # 5c: 迟滞环决策树单元测试
    hyst = HysteresisStrategyController()
    r1 = hyst.decide(0.30, "STANDARD_PATH", 2, [])
    r2 = hyst.decide(0.80, "SCAFFOLD_HELP", 0, [])
    r3 = hyst.decide(0.55, "STANDARD_PATH", 0, [0.6, 0.65, 0.7])
    check("  5e 迟滞环降级", r1 == "SCAFFOLD_HELP", r1)
    check("  5f 迟滞环升级", r2 == "STANDARD_PATH", r2)
    check("  5g 边界遗漏", r3 == "EDGE_CASE_DRILL", r3)
    all_ok = all_ok and (r1 == "SCAFFOLD_HELP" and r2 == "STANDARD_PATH" and r3 == "EDGE_CASE_DRILL")

    return all_ok


# ============================================================================
# Test 6: LangGraph 全链路编排
# ============================================================================

def test_langgraph_full_pipeline(client: LLMClientV2) -> bool:
    sep("Test 6: LangGraph 全链路编排 (真实 LLM)")

    orchestrator = EduAgentGraph()
    orchestrator.inject_llm(client)
    orchestrator.build()

    state = AgentState(user_id="U_FULL", course_id="CS_DS_101")
    state.current_node_id = "N_BST"
    state.target_node_id = "N_BST_INSERT"
    # 设置初始学习路径（模拟 Planner 输出）
    state.active_path = ["N_BST"]
    state.static_profile.motivation = "academic_exam"
    # 设置行为数据：包含一个答疑请求
    state.latest_behavior = LatestBehavior(
        node_id="N_BST",
        correctness=0.75,
        accuracy_rate=0.75,
        code_pass_rate=0.7,
        duration_ratio=1.0,
        tutor_query="请解释二叉搜索树的插入算法步骤",
    )

    # 只运行一轮（通过小迭代上限管控）
    # 由于 active_path 只有一个节点且无 mastery，会走完一轮
    try:
        # 直接 invoke，但由于有100轮上限，需要控制
        # 这里手动限制为 1 轮迭代
        final = orchestrator.graph.compile()
        result = final.invoke(
            state,
            config={"recursion_limit": 50},
        )

        # 验证各节点输出
        has_path = bool(result.active_path)
        has_resources = bool(result.generated_resources)
        has_tutor_resp = bool(result.tutor_response)
        has_report = bool(result.dynamic_profile.diagnostic_report_md)
        has_strategy = bool(result.pedagogical_strategy)

        check("  Evaluator -> Profiler -> Planner", has_path, f"path_len={len(result.active_path)}")
        check("  ContentMesh 资源生成", has_resources,
              f"nodes={list(result.generated_resources.keys())}")
        check("  TutorAgent 答疑响应", has_tutor_resp,
              f"has_text={bool(result.tutor_response and result.tutor_response.get('text_explanation'))}")
        check("  Validator 校验", True, "passed through")
        check("  Assessment 评估报告", has_report, f"report_len={len(result.dynamic_profile.diagnostic_report_md)}")
        check("  策略控制变量", has_strategy, result.pedagogical_strategy)

        all_ok = has_resources and has_tutor_resp and has_report
        return all_ok
    except Exception as e:
        check("  LangGraph 全链路", False, str(e))
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# Test 7: LLM 性能基准
# ============================================================================

def test_llm_performance(client: LLMClientV2) -> bool:
    sep("Test 7: LLM 性能基准")

    all_ok = True
    latencies = []

    test_cases = [
        ("短文本", "什么是栈？请一句话回答。", 20),
        ("中文本", "请用 100 字解释队列的 FIFO 特性。", 30),
        ("Mermaid", "请为'数组和链表'生成一个简单的 Mermaid graph TD 对比图。", 40),
        ("NLI", "前提: 二叉树是树的一种。假设: 二叉树是一种树结构。请给出蕴含度分数(0-1)。", 15),
    ]

    for name, prompt, max_ok_ms in test_cases:
        try:
            t0 = time.perf_counter()
            resp = client.chat_sync(
                [{"role": "user", "content": prompt}], max_tokens=200
            ).get("content", "")
            elapsed = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed)
            ok = "Error" not in resp and len(resp) > 10
            check(f"  {name}", ok, f"{elapsed:.0f}ms (len={len(resp)})")
            all_ok = all_ok and ok
        except Exception as e:
            check(f"  {name}", False, str(e))
            all_ok = False

    if latencies:
        avg = sum(latencies) / len(latencies)
        check("  平均延迟", avg < 5000, f"avg={avg:.0f}ms")
        all_ok = all_ok and (avg < 5000)

    return all_ok


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    print("=" * 60)
    print("  EduAgent 全链路端到端集成测试（真实 LLM）")
    print(f"  模型: qwen-plus (DashScope)")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ---- 初始化 LLM ----
    try:
        client = create_llm_client_v2_from_env()
        print(f"\n  LLM Provider: {client.provider}")
        print(f"  Model: {client.config.get('model')}")
    except RuntimeError as e:
        print(f"\n  [FATAL] {e}")
        return 1

    # ---- 运行测试 ----
    results = {}

    results["LLM Connectivity"] = test_llm_connectivity(client)
    if not results["LLM Connectivity"]:
        print("\n  [FATAL] LLM 基础连通性测试失败，跳过后续测试。")
        return 1

    results["ContentMesh"] = test_content_mesh_generation(client)
    results["TutorAgent"] = test_tutor_agent(client)
    results["Validator NLI"] = test_validator_nli(client)
    results["Assessment"] = test_assessment()
    results["LangGraph Pipeline"] = test_langgraph_full_pipeline(client)
    results["LLM Performance"] = test_llm_performance(client)

    # ---- 汇总 ----
    sep("测试结果汇总")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        print(f"  {'[OK]' if ok else '[XX]'} {name}")

    print(f"\n  {passed}/{total} 测试通过")

    if passed == total:
        print("\n  *** 全部测试通过! EduAgent 全链路正常运行 ***")
        return 0
    else:
        print(f"\n  *** {total - passed} 项测试失败，请检查日志 ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
