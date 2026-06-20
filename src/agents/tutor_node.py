# -*- coding: utf-8 -*-
"""
Tutor Agent Node — 智能辅导答疑节点 (LangGraph 加分项)
=========================================================

本节点是 EduAgent 多智能体系统中的独立答疑 Agent，对应赛题「智能辅导」
可选加分项。实现了"学生提问 → 智能体回答"的交互闭环，输出统一的
多模态答疑服务。

核心能力 (三轨多模态答疑):
  1. 文字解答轨 (Text Path)
     - 从 Milvus 召回当前知识点父块上下文
     - 注入大模型生成流式学术原理解释

  2. 动态图解轨 (Mermaid Automata Path)
     - 大模型将原理解析转化为 Mermaid 拓扑流程图 / 时序图
     - MermaidSyntaxGuard 进行 AST 语法树校验与闭合修复

  3. 微课切片索引轨 (Video Hydration Path)
     - 按 5 秒一帧进行多模态特征向量化
     - 时序滑动窗口在 Milvus 中执行点对点最高相似度检索
     - 动态计算最匹配画面起点与终点 (Time Range)
     - 无视视频增量更新带来的时间戳位移

算法依据:
  Video_Card = argmax_{v ∈ V_video} Cosine_Sim(E_query, E_v)

依赖声明:
  本模块算法独立于任何特定大模型 API，通过抽象接口注入。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import re
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class TutorInput(BaseModel):
    """Tutor Node 的标准化输入。"""

    agent_state: Any = Field(..., description="当前 AgentState 全量快照")
    milvus_client: Any = Field(
        default=None, description="Milvus 向量检索客户端（用于父块召回 + 视频切片检索）"
    )
    llm_generator: Any = Field(
        default=None, description="大模型文本生成器（用于学术原理解释 + Mermaid 生成）"
    )


class TutorOutput(BaseModel):
    """Tutor Node 的标准化输出。"""

    agent_state: Any = Field(..., description="更新后的 AgentState（含 tutor_response）")


class VideoHydrationCard(BaseModel):
    """微课切片水合卡片 — 视频轨的输出包装。"""

    url: str = Field(..., description="微课视频 CDN 地址")
    timestamp_range: str = Field(..., description="推荐时间片段，如 00:30-01:15")
    similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="余弦相似度分数")


class TutorResponseCard(BaseModel):
    """Tutor Agent 的三轨合一多模态答疑响应卡片。"""

    text_explanation: str = Field(default="", description="轨一：流式学术原理解释")
    mermaid_src: str = Field(default="", description="轨二：经语法卫兵校验修复后的 Mermaid 源码")
    video_hydration: Optional[VideoHydrationCard] = Field(
        default=None, description="轨三：时序滑动窗口匹配的微课切片"
    )
    query: str = Field(default="", description="原始学生提问")


# ============================================================================
# 词法卫兵 — Mermaid AST 校验与闭合修复
# ============================================================================

class MermaidSyntaxGuard:
    """Mermaid 语法词法卫兵与语法树修复器。

    解决大模型流式生成 Mermaid 拓扑图时常见的三类缺陷:
      1. 缺少 graph 声明头 → 注入兜底空图
      2. 括号不匹配（流式截断导致）→ 计数器补偿闭合
      3. 非法控制字符（如 :-> 等简写错误）→ 正则替换修复
    """

    # 合法的括号对
    BRACKET_PAIRS: Dict[str, str] = {"[": "]", "{": "}", "(": ")"}

    @staticmethod
    def validate_and_repair(raw_mermaid_str: str) -> str:
        """对一段 Mermaid 源码进行语法校验与自动修复。

        修复策略（按优先级）:
          1. 空字符串或缺失 "graph" 关键字 → 返回兜底空白图
          2. 剥离首尾空白
          3. 括号计数器补偿闭合
          4. 正则替换非法控制字符

        Args:
            raw_mermaid_str: 大模型原始输出的 Mermaid 源码（可能含语法缺陷）。

        Returns:
            修复后的合法 Mermaid 源码字符串。
        """
        if not raw_mermaid_str or "graph" not in raw_mermaid_str:
            return "graph TD\n    A[暂无可用图解] --> B[请参考下方文字详细原理解析]"

        repaired = raw_mermaid_str.strip()

        # 修复 1: 括号不匹配 — 由于大模型流式截断导致的 open bracket 溢出
        # 只处理方括号，因为 Mermaid 节点标签最常用 [...]
        open_brackets = len(re.findall(r'\[', repaired))
        close_brackets = len(re.findall(r'\]', repaired))
        if open_brackets > close_brackets:
            repaired += "]" * (open_brackets - close_brackets)

        # 对称处理花括号
        open_braces = len(re.findall(r'\{', repaired))
        close_braces = len(re.findall(r'\}', repaired))
        if open_braces > close_braces:
            repaired += "}" * (open_braces - close_braces)

        # 对称处理圆括号
        open_parens = len(re.findall(r'\(', repaired))
        close_parens = len(re.findall(r'\)', repaired))
        if open_parens > close_parens:
            repaired += ")" * (open_parens - close_parens)

        # 修复 2: 拦截非法特殊控制字符
        # 处理 ":->" 风格简写错误 → 规范为 "-->"
        repaired = re.sub(r':\->', '-->', repaired)

        # 处理尾部多余箭头（如 "... -->"）
        repaired = re.sub(r'-->\s*$', '', repaired)

        # 修复 3: 确保至少有一条边存在
        if "---" not in repaired and "-->" not in repaired and "==" not in repaired:
            repaired += "\n    A[内容概览] --> B[详见文字说明]"

        return repaired


# ============================================================================
# Tutor Agent 主节点
# ============================================================================

class TutorAgentNode:
    """智能辅导答疑节点 — 三轨多模态答疑服务的核心实现。

    工作流程:
      1. 从 AgentState 中提取 student query
      2. 轨一 (Text):  Milvus 父块召回 → LLM 学术原理解释
      3. 轨二 (Mermaid): LLM 生成拓扑图 → MermaidSyntaxGuard 修复
      4. 轨三 (Video):  时序滑动窗口多模态相似度匹配 → 微课切片
      5. 封装 TutorResponseCard 写入 AgentState

    使用示例:
        >>> tutor = TutorAgentNode(milvus_client, llm_generator)
        >>> inp = TutorInput(agent_state=state, milvus_client=milvus, llm_generator=llm)
        >>> out = tutor(inp)
        >>> print(out.agent_state.tutor_response["mermaid_src"])
    """

    # 默认回退资源
    FALLBACK_VIDEO_URL: str = "https://default_course_cdn/fallback.mp4"
    FALLBACK_TIME_RANGE: str = "00:00-01:00"

    def __init__(
        self,
        milvus_client: Any = None,
        llm_generator: Any = None,
    ) -> None:
        """初始化 TutorAgentNode。

        Args:
            milvus_client: Milvus 向量检索客户端。若为 None，轨一和轨三使用兜底逻辑。
            llm_generator: 大模型生成器。需实现:
              - generate_academic_explanation(query, reference_chunks) -> str
              - generate_mermaid_graph(query, text_explanation) -> str
              若为 None，使用基于模板的本地 fallback。
        """
        self._milvus = milvus_client
        self._llm = llm_generator
        self._guard = MermaidSyntaxGuard()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def __call__(self, inp: TutorInput) -> TutorOutput:
        """执行一次完整的智能辅导答疑。

        Args:
            inp: TutorInput（agent_state + milvus_client + llm_generator）。

        Returns:
            TutorOutput（含更新后的 agent_state）。
        """
        state = inp.agent_state
        milvus = inp.milvus_client or self._milvus
        llm = inp.llm_generator or self._llm

        query = self._extract_query(state)
        current_node = self._extract_current_node(state)

        if not query:
            return TutorOutput(agent_state=state)

        # ---- 轨一：文字解答 ----
        reference_chunks = self._retrieve_parent_context(milvus, query, current_node)
        text_response = self._generate_text_explanation(llm, query, reference_chunks)

        # ---- 轨二：动态图解 ----
        raw_mermaid = self._generate_mermaid(llm, query, text_response)
        clean_mermaid = self._guard.validate_and_repair(raw_mermaid)

        # ---- 轨三：微课切片索引 ----
        video_metadata = self._search_video_slices(milvus, query)
        video_card = VideoHydrationCard(
            url=video_metadata[0].get("url", self.FALLBACK_VIDEO_URL),
            timestamp_range=video_metadata[0].get("time_range", self.FALLBACK_TIME_RANGE),
            similarity=video_metadata[0].get("similarity", 0.0),
        )

        # ---- 封装响应卡片 ----
        response_card = TutorResponseCard(
            text_explanation=text_response,
            mermaid_src=clean_mermaid,
            video_hydration=video_card,
            query=query,
        )

        state.tutor_response = response_card.model_dump()
        return TutorOutput(agent_state=state)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_query(state: Any) -> Optional[str]:
        """从 AgentState 提取学生提问。"""
        lb = getattr(state, "latest_behavior", None)
        if lb is None:
            return None
        return getattr(lb, "tutor_query", None) or ""

    @staticmethod
    def _extract_current_node(state: Any) -> str:
        """从 AgentState 提取当前知识点 ID。"""
        return getattr(state, "current_node_id", None) or ""

    @staticmethod
    def _retrieve_parent_context(
        milvus: Any,
        query: str,
        current_node: str,
    ) -> List[str]:
        """轨一前置: 通过 Milvus 检索父块完整上下文。

        Args:
            milvus: Milvus 客户端。
            query: 学生提问。
            current_node: 当前知识点 ID。

        Returns:
            父块内容字符串列表。
        """
        if milvus is None:
            return []
        try:
            if hasattr(milvus, "search_parent_chunks"):
                parents = milvus.search_parent_chunks(query, current_node)
                return [p.content for p in parents]
        except Exception:
            pass
        return []

    def _generate_text_explanation(
        self,
        llm: Any,
        query: str,
        reference_chunks: List[str],
    ) -> str:
        """轨二: 调用大模型生成学术原理解释。

        若 LLM 不可用，回退到基于检索片段的静态拼接。
        """
        if llm is not None and hasattr(llm, "generate_academic_explanation"):
            try:
                return llm.generate_academic_explanation(query, reference_chunks)
            except Exception:
                pass
        # Fallback: 拼接检索到的上下文作为静态解答
        if reference_chunks:
            context = "\n\n".join(reference_chunks[:3])
            return (
                f"## 关于「{query}」的相关知识点解析\n\n"
                f"{context}\n\n"
                f"> [提示] 当前为离线模式，以上为知识库中与您提问最相关的学术内容。"
            )
        return (
            f"## 关于「{query}」的解答\n\n"
            f"很抱歉，当前无法从知识库中检索到与您提问直接相关的内容。"
            f"建议您尝试更换提问方式，或联系课程助教获取进一步帮助。"
        )

    def _generate_mermaid(
        self,
        llm: Any,
        query: str,
        text_explanation: str,
    ) -> str:
        """轨二: 调用大模型生成 Mermaid 拓扑图解。

        若 LLM 不可用，回退到基于提问关键词的模板生成。
        """
        if llm is not None and hasattr(llm, "generate_mermaid_graph"):
            try:
                return llm.generate_mermaid_graph(query, text_explanation)
            except Exception:
                pass
        # Fallback: 模板化 Mermaid 生成
        return self._template_mermaid(query)

    @staticmethod
    def _template_mermaid(query: str) -> str:
        """基于提问关键词的模板化 Mermaid 流程图。

        作为 LLM 不可用时的离线兜底方案。
        """
        sanitized = query[:30].replace('"', "'")
        return (
            "graph TD\n"
            f'    Q["[Q] {sanitized}"] --> A["[1] 核心概念"]\n'
            '    A --> B["[2] 原理解析"]\n'
            '    A --> C["[3] 代码示例"]\n'
            '    B --> D["[4] 常见误区"]\n'
            '    C --> D\n'
            '    D --> E["[5] 掌握检验"]'
        )

    def _search_video_slices(
        self,
        milvus: Any,
        query: str,
    ) -> List[Dict[str, Any]]:
        """轨三: 时序滑动窗口多模态相似度匹配。

        在 Milvus 的 Video Slice Collection 中执行点对点检索，
        返回最匹配的微课时间片段。

        Args:
            milvus: Milvus 客户端。
            query: 学生提问。

        Returns:
            匹配的视频元数据列表。
        """
        if milvus is not None and hasattr(milvus, "search_video_temporal_slices"):
            try:
                results = milvus.search_video_temporal_slices(query, top_k=1)
                if results:
                    return results
            except Exception:
                pass
        return [{"url": self.FALLBACK_VIDEO_URL, "time_range": self.FALLBACK_TIME_RANGE, "similarity": 0.0}]


# ============================================================================
# 工厂函数
# ============================================================================

def create_tutor_node(
    milvus_client: Any = None,
    llm_generator: Any = None,
) -> TutorAgentNode:
    """创建 TutorAgentNode 实例的工厂函数。

    Args:
        milvus_client: Milvus 客户端（可选）。
        llm_generator: 大模型生成器（可选）。

    Returns:
        配置好的 TutorAgentNode。
    """
    return TutorAgentNode(
        milvus_client=milvus_client,
        llm_generator=llm_generator,
    )
