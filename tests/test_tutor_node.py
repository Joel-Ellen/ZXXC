# -*- coding: utf-8 -*-
"""
Tutor Agent Node — 单元测试套件
================================

覆盖范围:
  1. MermaidSyntaxGuard: 空字符串与缺失 graph 声明
  2. MermaidSyntaxGuard: 方括号不匹配修复
  3. MermaidSyntaxGuard: 花括号/圆括号不匹配修复
  4. MermaidSyntaxGuard: 非法控制字符替换
  5. MermaidSyntaxGuard: 尾部多余箭头清理
  6. MermaidSyntaxGuard: 无边的合法 Mermaid（自动补边）
  7. TutorAgentNode: 正常三轨答疑流程
  8. TutorAgentNode: 空查询直接跳过
  9. TutorAgentNode: Milvus 不可用时的离线兜底
 10. TutorAgentNode: LLM 不可用时的模板化 Mermaid 回退
 11. TutorAgentNode: 视频切片检索回退
 12. VideoHydrationCard / TutorResponseCard: Pydantic 序列化

运行方式:
    pytest tests/test_tutor_node.py -v
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.tutor_node import (
    TutorAgentNode,
    TutorInput,
    TutorOutput,
    TutorResponseCard,
    VideoHydrationCard,
    MermaidSyntaxGuard,
    create_tutor_node,
)
from src.api_models.tutor_request import TutorRequest
from src.state.agent_state import (
    AgentState,
    LatestBehavior,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tutor_node() -> TutorAgentNode:
    """创建一个无外部依赖的 TutorAgentNode（离线模式）。"""
    return TutorAgentNode(milvus_client=None, llm_generator=None)


@pytest.fixture
def agent_state_with_query() -> AgentState:
    """创建带有答疑请求的 AgentState。"""
    state = AgentState(user_id="U1", course_id="CS101")
    state.latest_behavior = LatestBehavior(
        node_id="N_BST",
        correctness=0.8,
        tutor_query="二叉搜索树的插入操作如何实现？",
    )
    return state


@pytest.fixture
def agent_state_without_query() -> AgentState:
    """创建没有答疑请求的 AgentState。"""
    state = AgentState(user_id="U2", course_id="CS101")
    state.latest_behavior = LatestBehavior(
        node_id="N_SORT",
        correctness=0.9,
        tutor_query=None,
    )
    return state


@pytest.fixture
def agent_state_empty_behavior() -> AgentState:
    """创建 latest_behavior 为空的 AgentState。"""
    return AgentState(user_id="U3", course_id="CS101")


# ============================================================================
# 1. MermaidSyntaxGuard 测试
# ============================================================================

class TestMermaidSyntaxGuard:
    """Mermaid 语法词法卫兵与修复器的完整测试套件。"""

    def test_empty_string_returns_fallback(self) -> None:
        """空字符串应返回兜底空白图。"""
        result = MermaidSyntaxGuard.validate_and_repair("")
        assert "graph TD" in result
        assert "暂无可用图解" in result

    def test_none_returns_fallback(self) -> None:
        """None 应返回兜底空白图。"""
        result = MermaidSyntaxGuard.validate_and_repair(None)  # type: ignore
        assert "graph TD" in result
        assert "暂无可用图解" in result

    def test_missing_graph_keyword_returns_fallback(self) -> None:
        """缺少 'graph' 关键字的字符串应返回兜底图。"""
        result = MermaidSyntaxGuard.validate_and_repair("just some text")
        assert "graph TD" in result

    def test_valid_mermaid_passes_through(self) -> None:
        """合法的 Mermaid 流程图应原样返回（去除尾部空白）。"""
        valid = "graph TD\n    A[Start] --> B[End]"
        result = MermaidSyntaxGuard.validate_and_repair(valid)
        assert "graph TD" in result
        assert "A[Start]" in result
        assert "B[End]" in result
        assert "Start" in result

    def test_unmatched_brackets_repaired(self) -> None:
        """方括号不匹配时应自动补全闭合括号。"""
        broken = "graph TD\n    A[二叉树 --> B[遍历"
        result = MermaidSyntaxGuard.validate_and_repair(broken)
        assert result.count("[") == result.count("]"), (
            f"括号应成对匹配, 实际: [{result.count('[')} vs ]{result.count(']')}"
        )

    def test_unmatched_braces_repaired(self) -> None:
        """花括号不匹配时应自动补全。"""
        broken = "graph TD\n    A{条件 --> B{结果"
        result = MermaidSyntaxGuard.validate_and_repair(broken)
        assert result.count("{") == result.count("}")

    def test_unmatched_parens_repaired(self) -> None:
        """圆括号不匹配时应自动补全。"""
        broken = "graph TD\n    A((圆形节点"
        result = MermaidSyntaxGuard.validate_and_repair(broken)
        assert result.count("(") == result.count(")")

    def test_illegal_arrow_syntax_fixed(self) -> None:
        """':->' 非法控制字符应替换为 '-->'。"""
        broken = "graph TD\n    A[Start] :-> B[End]"
        result = MermaidSyntaxGuard.validate_and_repair(broken)
        assert ":->" not in result
        assert "-->" in result

    def test_trailing_arrow_cleaned(self) -> None:
        """尾部多余的 '-->' 应被清理。"""
        broken = "graph TD\n    A --> B -->"
        result = MermaidSyntaxGuard.validate_and_repair(broken)
        assert not result.rstrip().endswith("-->")

    def test_no_edges_auto_added(self) -> None:
        """没有边的合法图应自动添加一条边。"""
        no_edges = "graph TD\n    A[概念]\n    B[详解]"
        result = MermaidSyntaxGuard.validate_and_repair(no_edges)
        assert "-->" in result or "---" in result

    def test_multiple_issues_repaired(self) -> None:
        """多种缺陷同时存在时应全部修复。"""
        messy = "graph TD\n    A[开始 :-> B[中间 --> C -->"
        result = MermaidSyntaxGuard.validate_and_repair(messy)
        assert ":->" not in result
        assert not result.rstrip().endswith("-->")
        assert result.count("[") == result.count("]")


# ============================================================================
# 2. TutorAgentNode 核心流程测试
# ============================================================================

class TestTutorAgentNode:
    """TutorAgentNode 离线模式下的功能测试。"""

    def test_normal_tutor_query_produces_response(
        self, tutor_node: TutorAgentNode, agent_state_with_query: AgentState
    ) -> None:
        """正常答疑请求应产生三轨响应卡片。"""
        inp = TutorInput(agent_state=agent_state_with_query)
        out = tutor_node(inp)

        assert out.agent_state.tutor_response is not None
        resp = out.agent_state.tutor_response
        assert "text_explanation" in resp
        assert "mermaid_src" in resp
        assert "video_hydration" in resp
        # 离线模式：文字解答包含回退提示
        assert len(resp["text_explanation"]) > 0
        # Mermaid 应为合法 graph
        assert "graph TD" in resp["mermaid_src"]

    def test_code_debug_request_reaches_mode_prompt(self) -> None:
        class DebugLlm:
            def __init__(self) -> None:
                self.messages = []

            def chat_sync(self, messages, **kwargs):
                self.messages = messages
                return {"content": "{}"}

            def extract_json(self, _content):
                return {"text_explanation": "The index is out of range.", "root_cause": "empty list"}

        llm = DebugLlm()
        node = TutorAgentNode(llm_generator=llm)
        state = AgentState(user_id="U-debug", course_id="CS101", current_node_id="N_BST")
        request = TutorRequest(
            question="Why does the lookup fail?",
            contextType="code_debug",
            codeSnippet="items[0]",
            errorMessage="IndexError: list index out of range",
        )

        result = node(TutorInput(agent_state=state, request=request))

        prompt = llm.messages[1]["content"]
        assert "items[0]" in prompt
        assert "IndexError: list index out of range" in prompt
        assert result.agent_state.tutor_response["tutoring_mode"] == "code_debug"
        assert result.agent_state.tutor_response["root_cause"] == "empty list"

    def test_empty_behavior_skips_tutor(
        self, tutor_node: TutorAgentNode, agent_state_empty_behavior: AgentState
    ) -> None:
        """latest_behavior 为 None 时应跳过答疑。"""
        inp = TutorInput(agent_state=agent_state_empty_behavior)
        out = tutor_node(inp)
        # tutor_response 应保持原状（不更新）
        assert out.agent_state.tutor_response is None

    def test_null_tutor_query_skips_tutor(
        self, tutor_node: TutorAgentNode, agent_state_without_query: AgentState
    ) -> None:
        """tutor_query 为 None 时应跳过答疑。"""
        inp = TutorInput(agent_state=agent_state_without_query)
        out = tutor_node(inp)
        assert out.agent_state.tutor_response is None

    def test_offline_fallback_text_generation(
        self, tutor_node: TutorAgentNode, agent_state_with_query: AgentState
    ) -> None:
        """离线模式下文字解答应包含提问关键词和fallback提示。"""
        inp = TutorInput(agent_state=agent_state_with_query)
        out = tutor_node(inp)
        text = out.agent_state.tutor_response["text_explanation"]
        assert "二叉搜索树" in text
        assert "离线模式" in text or "无法从知识库中检索" in text

    def test_template_mermaid_generation(
        self, tutor_node: TutorAgentNode, agent_state_with_query: AgentState
    ) -> None:
        """模板化 Mermaid 生成应包含核心节点。"""
        inp = TutorInput(agent_state=agent_state_with_query)
        out = tutor_node(inp)
        mermaid = out.agent_state.tutor_response["mermaid_src"]
        assert "graph TD" in mermaid
        assert "核心概念" in mermaid
        assert "-->" in mermaid

    def test_video_fallback_when_no_milvus(
        self, tutor_node: TutorAgentNode, agent_state_with_query: AgentState
    ) -> None:
        """Milvus 不可用时视频轨应返回兜底URL。"""
        inp = TutorInput(agent_state=agent_state_with_query)
        out = tutor_node(inp)
        video = out.agent_state.tutor_response["video_hydration"]
        assert video["url"] == "https://default_course_cdn/fallback.mp4"
        assert video["timestamp_range"] == "00:00-01:00"
        assert video["similarity"] == 0.0

    def test_response_card_contains_original_query(
        self, tutor_node: TutorAgentNode, agent_state_with_query: AgentState
    ) -> None:
        """响应卡片应回传原始提问。"""
        inp = TutorInput(agent_state=agent_state_with_query)
        out = tutor_node(inp)
        resp = out.agent_state.tutor_response
        assert resp["query"] == "二叉搜索树的插入操作如何实现？"


# ============================================================================
# 3. Pydantic 模型测试
# ============================================================================

class TestTutorPydanticModels:
    """Tutor Node 相关的 Pydantic 模型序列化/反序列化测试。"""

    def test_video_hydration_card_creation(self) -> None:
        """VideoHydrationCard 应正确构造并可序列化。"""
        card = VideoHydrationCard(
            url="https://cdn.example.com/video.mp4",
            timestamp_range="00:30-01:15",
            similarity=0.85,
        )
        d = card.model_dump()
        assert d["url"] == "https://cdn.example.com/video.mp4"
        assert d["timestamp_range"] == "00:30-01:15"
        assert d["similarity"] == 0.85

    def test_tutor_response_card_full(self) -> None:
        """TutorResponseCard 应完整封装三轨输出。"""
        video = VideoHydrationCard(
            url="https://cdn.example.com/v.mp4",
            timestamp_range="01:00-02:00",
            similarity=0.92,
        )
        card = TutorResponseCard(
            text_explanation="## 详解\n...",
            mermaid_src="graph TD\n    A-->B",
            video_hydration=video,
            query="测试问题",
        )
        d = card.model_dump()
        assert d["text_explanation"] == "## 详解\n..."
        assert d["mermaid_src"] == "graph TD\n    A-->B"
        assert d["video_hydration"]["url"] == "https://cdn.example.com/v.mp4"
        assert d["query"] == "测试问题"

    def test_tutor_response_card_no_video(self) -> None:
        """TutorResponseCard 允许 video_hydration 为 None。"""
        card = TutorResponseCard(
            text_explanation="只有文字",
            mermaid_src="graph TD\n    A-->B",
            query="问题",
        )
        assert card.video_hydration is None
        d = card.model_dump()
        assert d["video_hydration"] is None


# ============================================================================
# 4. 工厂函数测试
# ============================================================================

class TestTutorFactory:
    """create_tutor_node 工厂函数测试。"""

    def test_create_tutor_node_default(self) -> None:
        """默认参数创建的 TutorAgentNode 应可用。"""
        node = create_tutor_node()
        assert isinstance(node, TutorAgentNode)
        assert node._milvus is None
        assert node._llm is None

    def test_create_tutor_node_with_deps(self) -> None:
        """传入 Milvus 和 LLM 后创建的节点应持有引用。"""
        mock_milvus = object()
        mock_llm = object()
        node = create_tutor_node(
            milvus_client=mock_milvus,
            llm_generator=mock_llm,
        )
        assert node._milvus is mock_milvus
        assert node._llm is mock_llm
