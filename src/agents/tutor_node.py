# -*- coding: utf-8 -*-
"""
Tutor Agent Node — 智能辅导答疑节点 (LangGraph 加分项) 【已合并 LearningCoach】
==============================================================================

核心能力 (三轨多模态 + 五模式苏格拉底辅导):
  1. 文字解答轨 (Text Path) — Milvus 父块召回 → LLM 学术原理解释
  2. 动态图解轨 (Mermaid Automata Path) — LLM 拓扑图 + 语法卫兵修复
  3. 微课切片索引轨 (Video Hydration Path) — 时序滑动窗口多模态匹配

  4. 五模式辅导 (合并自 LearningCoachAgent):
     - concept:         概念深度讲解（类比 + 图解 + 代码示例 + 误区）
     - problem_solving: 苏格拉底式问题引导（不给答案）
     - code_debug:      代码调试（错误分析 + 修复引导 + 最佳实践）
     - exam_prep:       考试准备（重点复习 + 模拟考题 + 速记表）
     - general:         通用学习问题解答

算法依据:
  Video_Card = argmax_{v ∈ V_video} Cosine_Sim(E_query, E_v)

依赖声明:
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import re
import json
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# 辅导模式枚举（合并自 LearningCoach）
# ============================================================================

class TutoringMode(str, Enum):
    """辅导模式。"""
    CONCEPT = "concept"              # 概念讲解
    PROBLEM_SOLVING = "problem_solving"  # 问题引导
    CODE_DEBUG = "code_debug"        # 代码调试
    EXAM_PREP = "exam_prep"          # 考试准备
    GENERAL = "general"              # 通用辅导


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
    """Tutor Agent 的三轨合一多模态答疑响应卡片 + 五模式辅导字段。"""

    # ── 原有三轨 ──
    text_explanation: str = Field(default="", description="轨一：流式学术原理解释")
    mermaid_src: str = Field(default="", description="轨二：经语法卫兵校验修复后的 Mermaid 源码")
    video_hydration: Optional[VideoHydrationCard] = Field(
        default=None, description="轨三：时序滑动窗口匹配的微课切片"
    )
    query: str = Field(default="", description="原始学生提问")

    # ── 合并自 LearningCoach 的五模式辅导字段 ──
    tutoring_mode: str = Field(default="general", description="辅导模式: concept/problem_solving/code_debug/exam_prep/general")
    core_definition: Optional[str] = Field(default=None, description="概念核心定义")
    analogy: Optional[str] = Field(default=None, description="生活化类比")
    detailed_explanation: Optional[str] = Field(default=None, description="详细技术解释")
    code_example: Optional[str] = Field(default=None, description="代码示例")
    common_misconceptions: Optional[List[str]] = Field(default=None, description="常见误区")
    hints: Optional[List[str]] = Field(default=None, description="引导提示")
    solution_approach: Optional[str] = Field(default=None, description="解题思路框架")
    error_analysis: Optional[str] = Field(default=None, description="错误分析（调试模式）")
    root_cause: Optional[str] = Field(default=None, description="根本原因（调试模式）")
    best_practices: Optional[List[str]] = Field(default=None, description="最佳实践")
    key_topics: Optional[List[str]] = Field(default=None, description="重点复习主题（备考模式）")
    cheat_sheet: Optional[str] = Field(default=None, description="速记表（备考模式）")
    extension_questions: Optional[List[str]] = Field(default=None, description="延伸思考问题")
    follow_up_questions: Optional[List[str]] = Field(default=None, description="可追问的问题")


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
        """轨三: 时序滑动窗口多模态相似度匹配。"""
        if milvus is not None and hasattr(milvus, "search_video_temporal_slices"):
            try:
                results = milvus.search_video_temporal_slices(query, top_k=1)
                if results:
                    return results
            except Exception:
                pass
        return [{"url": self.FALLBACK_VIDEO_URL, "time_range": self.FALLBACK_TIME_RANGE, "similarity": 0.0}]

    # ==================================================================
    # 五模式苏格拉底辅导（合并自 LearningCoachAgent）
    # ==================================================================

    def tutor_with_mode(
        self,
        query: str,
        mode: str = "general",
        course_name: str = "",
        code_snippet: str = "",
        error_message: str = "",
        student_context: str = "",
    ) -> Dict[str, Any]:
        """按指定模式进行辅导答疑（新增统一入口）。"""
        if mode == TutoringMode.CONCEPT:
            return self._tutor_concept(query, course_name, student_context)
        elif mode == TutoringMode.PROBLEM_SOLVING:
            return self._tutor_problem_solving(query, course_name, student_context)
        elif mode == TutoringMode.CODE_DEBUG:
            return self._tutor_code_debug(query, code_snippet, error_message, student_context)
        elif mode == TutoringMode.EXAM_PREP:
            return self._tutor_exam_prep(query, course_name, student_context)
        else:
            return self._tutor_general(query, course_name, student_context)

    def _build_tutoring_prompt(self, user_prompt: str, temperature: float = 0.7) -> Optional[Dict]:
        """调用 LLM 获取 JSON 格式辅导结果。"""
        llm = self._llm
        if llm is None:
            return None
        system_prompt = (
            "你是一位耐心的AI学习导师。苏格拉底式引导、脚手架式教学、"
            "类比解释、多角度讲解、鼓励试错。禁止直接给出完整答案。必须返回严格的JSON格式。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if hasattr(llm, 'chat_sync'):
                result = llm.chat_sync(messages, temperature=temperature, json_mode=True)
            elif hasattr(llm, 'chat'):
                result = {"content": llm.chat(messages)}
            else:
                return None
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if hasattr(llm, 'extract_json'):
                return llm.extract_json(content)
            return json.loads(content)
        except Exception:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

    def _tutor_concept(self, query: str, course_name: str, ctx: str) -> Dict[str, Any]:
        """概念深度讲解。"""
        prompt = f"""讲解概念。学生画像：{ctx}，课程：{course_name}，问题：{query}
返回JSON：{{"core_definition":"", "analogy":"", "detailed_explanation":"", "diagram":"", "code_example":"", "common_misconceptions":[], "extension_questions":[], "learning_tip":""}}"""
        data = self._build_tutoring_prompt(prompt)
        return {"mode": "concept", **(data or {"text_explanation": query})}

    def _tutor_problem_solving(self, query: str, course_name: str, ctx: str) -> Dict[str, Any]:
        """苏格拉底式问题引导。"""
        prompt = f"""引导解决问题（不给答案）。学生画像：{ctx}，课程：{course_name}，问题：{query}
返回JSON：{{"hints":[], "solution_approach":"", "common_mistakes":[], "check_points":[]}}"""
        data = self._build_tutoring_prompt(prompt, temperature=0.6)
        return {"mode": "problem_solving", **(data or {"text_explanation": query})}

    def _tutor_code_debug(self, query: str, code: str, error: str, ctx: str) -> Dict[str, Any]:
        """代码调试指导。"""
        prompt = f"""调试代码。学生画像：{ctx}，问题：{query}，代码：```python\n{code}\n```，错误：{error}
返回JSON：{{"error_analysis":"", "root_cause":"", "fix_guidance":"", "best_practices":[], "debugging_tips":[]}}"""
        data = self._build_tutoring_prompt(prompt, temperature=0.4)
        return {"mode": "code_debug", **(data or {"text_explanation": query})}

    def _tutor_exam_prep(self, query: str, course_name: str, ctx: str) -> Dict[str, Any]:
        """考试准备指导。"""
        prompt = f"""考试准备。学生画像：{ctx}，课程：{course_name}，问题：{query}
返回JSON：{{"key_topics":[], "review_strategy":"", "practice_questions":[], "common_exam_traps":[], "cheat_sheet":""}}"""
        data = self._build_tutoring_prompt(prompt, temperature=0.6)
        return {"mode": "exam_prep", **(data or {"text_explanation": query})}

    def _tutor_general(self, query: str, course_name: str, ctx: str) -> Dict[str, Any]:
        """通用辅导。"""
        prompt = f"""一般辅导。学生画像：{ctx}，课程：{course_name}，问题：{query}
返回JSON：{{"response":"", "diagram":"", "code_example":"", "follow_up_questions":[]}}"""
        data = self._build_tutoring_prompt(prompt)
        return {"mode": "general", **(data or {"text_explanation": query})}


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
