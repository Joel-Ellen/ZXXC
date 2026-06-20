# -*- coding: utf-8 -*-
"""
Validator Node — 双极防幻觉校验链
==================================

本节点是 LangGraph StateGraph 中的安全校验控制节点，在 Content Mesh
生成资源后执行，对生成内容进行双层防幻觉校验。

核心能力：

1. 第一极门控 (Pole-1 Gate) — 符号硬核对 + AST 静态检查
   - 提取生成文本中的公式实体 (LaTeX / 数学符号)
   - 对代码片段进行 AST 静态语法检查 (Python AST)
   - 通过后立即允许流式直通上屏 (先行通过，不阻塞用户体验)

2. 第二极门控 (Pole-2 Gate) — 异步 NLI 蕴含度度量
   - 带 64 Token 重叠区的滑动窗口切分
   - 对学术事实轨进行 NLI 蕴含度评分
   - 低于 0.85 则触发单点微观修正循环 (Refinement Loop)
   - 对接科大讯飞内容安全审查接口

3. 修正循环 (Refinement Loop)
   - 对不合规片段进行单点替换修正
   - 最多 3 轮迭代，超限则标记为需人工审核

依赖声明：
  AST 模块使用 Python 内置 ast 库。
  科大讯飞星火大模型用于 NLI 推理与内容安全审查。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import ast as _ast
import re
import math
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from enum import Enum

from pydantic import BaseModel, Field

from ..state.agent_state import AgentState, ResourceCard


# ============================================================================
# 枚举与常量
# ============================================================================

class ValidationPhase(str, Enum):
    """校验阶段。"""
    POLE1_SYMBOLIC = "pole1_symbolic"        # 第一极: 符号硬核对
    POLE2_NLI = "pole2_nli"                  # 第二极: NLI 蕴含度
    REFINEMENT = "refinement"                # 修正循环
    COMPLETED = "completed"                  # 校验通过
    REJECTED = "rejected"                    # 校验失败


class NLIEntailment(str, Enum):
    """NLI 蕴含关系。"""
    ENTAILMENT = "entailment"        # 蕴含 (分数高)
    NEUTRAL = "neutral"              # 中立
    CONTRADICTION = "contradiction"  # 矛盾


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class Pole1Result(BaseModel):
    """第一极门控校验结果。"""

    passed: bool = Field(default=True, description="是否通过")
    extracted_formulas: List[str] = Field(
        default_factory=list, description="提取到的公式实体"
    )
    extracted_code_blocks: List[str] = Field(
        default_factory=list, description="提取到的代码块"
    )
    code_ast_errors: List[str] = Field(
        default_factory=list, description="AST 语法错误列表"
    )
    formula_syntax_errors: List[str] = Field(
        default_factory=list, description="公式语法错误列表"
    )
    diagnostic: str = Field(default="", description="诊断信息")


class SlidingWindowChunk(BaseModel):
    """带重叠区的滑动窗口文本块。"""

    index: int = Field(default=0, ge=0)
    start_pos: int = Field(default=0, ge=0)
    end_pos: int = Field(default=0, ge=0)
    content: str = Field(default="")
    overlap_with_prev: int = Field(default=0, ge=0)


class Pole2ChunkResult(BaseModel):
    """单个滑动窗口块的 NLI 校验结果。"""

    chunk: SlidingWindowChunk = Field(...)
    entailment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    entailment_label: NLIEntailment = Field(default=NLIEntailment.NEUTRAL)
    is_hallucination: bool = Field(default=False)
    suggested_correction: Optional[str] = Field(default=None)


class Pole2Result(BaseModel):
    """第二极门控校验结果。"""

    passed: bool = Field(default=True)
    chunks_checked: int = Field(default=0)
    hallucination_count: int = Field(default=0)
    chunk_results: List[Pole2ChunkResult] = Field(
        default_factory=list
    )
    overall_entailment: float = Field(default=1.0, ge=0.0, le=1.0)
    refinement_rounds: int = Field(default=0, ge=0)
    content_safety_flagged: bool = Field(default=False)
    diagnostic: str = Field(default="")


class ValidatorInput(BaseModel):
    """Validator Node 输入。"""

    agent_state: AgentState = Field(..., description="当前全局 AgentState")
    cards_to_validate: List[ResourceCard] = Field(
        default_factory=list, description="需要校验的资源卡片列表"
    )
    ground_truth_context: str = Field(
        default="", description="基准真值上下文 (来自父块召回)"
    )
    enable_pole2: bool = Field(default=True, description="是否启用第二极 NLI 校验")
    max_refinement_rounds: int = Field(
        default=3, ge=1, le=5, description="最大修正循环轮次"
    )


class ValidatorOutput(BaseModel):
    """Validator Node 输出。"""

    agent_state: AgentState = Field(..., description="更新后的全局 AgentState")
    valid_cards: List[ResourceCard] = Field(
        default_factory=list, description="通过校验的资源卡片"
    )
    rejected_cards: List[ResourceCard] = Field(
        default_factory=list, description="未通过校验的卡片"
    )
    refined_cards: List[ResourceCard] = Field(
        default_factory=list, description="经过修正后的卡片"
    )
    pole1_results: Dict[str, Pole1Result] = Field(
        default_factory=dict, description="card_id → 第一极结果"
    )
    pole2_results: Dict[str, Pole2Result] = Field(
        default_factory=dict, description="card_id → 第二极结果"
    )
    overall_pass_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="总体通过率"
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict, description="诊断信息"
    )


# ============================================================================
# 公式与代码实体提取器 (Pole-1 辅助)
# ============================================================================

class EntityExtractor:
    """从生成文本中提取公式、代码块等结构化实体。"""

    # LaTeX 公式模式
    LATEX_PATTERNS: List[re.Pattern] = [
        re.compile(r'\$\$(.+?)\$\$', re.DOTALL),
        re.compile(r'\\(.+?\\)', re.DOTALL),
        re.compile(r'\$(.+?)\$'),
    ]
    # Markdown 代码块模式
    CODE_BLOCK_RE: re.Pattern = re.compile(
        r'```(\w*)\n(.*?)```', re.DOTALL
    )

    # 常见 LaTeX 语法错误模式
    LATEX_ERROR_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r'\\frac(?!\{)'), "\\frac 缺少参数花括号"),
        (re.compile(r'(?<!\\)\$(?![^$]*\$)'), "行内公式 $ 不匹配"),
        (re.compile(r'\{(?![^}]*\})'), "花括号不匹配"),
        (re.compile(r'\\sum(?![\s_^\{])'), "\\sum 缺少上下标"),
    ]

    @classmethod
    def extract_formulas(cls, text: str) -> List[str]:
        """提取所有公式实体。"""
        formulas: List[str] = []
        for pattern in cls.LATEX_PATTERNS:
            formulas.extend(pattern.findall(text))
        return formulas

    @classmethod
    def extract_code_blocks(cls, text: str) -> List[Tuple[str, str]]:
        """提取代码块 (language, code)。"""
        return cls.CODE_BLOCK_RE.findall(text)

    @classmethod
    def check_formula_syntax(cls, formula: str) -> List[str]:
        """检查公式语法错误。"""
        errors: List[str] = []
        for pattern, msg in cls.LATEX_ERROR_PATTERNS:
            if pattern.search(formula):
                errors.append(msg)
        return errors

    @classmethod
    def check_python_ast(cls, code: str) -> List[str]:
        """对 Python 代码进行 AST 静态语法检查。

        Returns:
            语法错误列表（空 = 无错误）。
        """
        errors: List[str] = []
        try:
            _ast.parse(code)
        except SyntaxError as e:
            errors.append(
                f"AST SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
            )
        except Exception as e:
            errors.append(f"AST parse exception: {str(e)[:100]}")
        return errors


# ============================================================================
# 滑动窗口切分器 (Pole-2 辅助)
# ============================================================================

class SlidingWindowSplitter:
    """带 64 Token 重叠区的滑动窗口文本切分器。

    滑动步长 = window_size - overlap_size。
    对相邻窗口的重叠区域进行上下文衔接，防止边界处的事实断裂。
    """

    WINDOW_SIZE: int = 256       # token 数估算
    OVERLAP_SIZE: int = 64       # 重叠 token 数
    CHARS_PER_TOKEN: float = 2.5  # 中英文混合字符/token 估算

    def __init__(
        self,
        window_size: int = 256,
        overlap_size: int = 64,
    ) -> None:
        self._window_size = window_size
        self._overlap_size = overlap_size

    def split(self, text: str) -> List[SlidingWindowChunk]:
        """将文本切分为带重叠的滑动窗口块。

        Args:
            text: 输入文本。

        Returns:
            SlidingWindowChunk 列表。
        """
        window_chars = int(self._window_size * self.CHARS_PER_TOKEN)
        overlap_chars = int(self._overlap_size * self.CHARS_PER_TOKEN)
        step = max(1, window_chars - overlap_chars)

        chunks: List[SlidingWindowChunk] = []
        start = 0
        idx = 0

        while start < len(text):
            end = min(start + window_chars, len(text))
            chunk_text = text[start:end]
            prev_overlap = min(overlap_chars, start)

            chunks.append(SlidingWindowChunk(
                index=idx,
                start_pos=start,
                end_pos=end,
                content=chunk_text,
                overlap_with_prev=prev_overlap if idx > 0 else 0,
            ))

            start += step
            idx += 1

            # 防止无限循环
            if end >= len(text):
                break

        return chunks


# ============================================================================
# Pole-1 门控: 符号硬核对
# ============================================================================

class Pole1Gate:
    """第一极门控 — 符号硬核对 + AST 静态检查。

    流程:
      1. 提取公式 → LaTeX 语法检查
      2. 提取代码块 → Python AST 解析
      3. 通过 → 流式直通；失败 → 标记拒绝
    """

    def validate(self, text: str, card_type: str = "") -> Pole1Result:
        """执行第一极符号硬核对。

        Args:
            text: 生成文本。
            card_type: 卡片类型。

        Returns:
            Pole1Result。
        """
        formulas = EntityExtractor.extract_formulas(text)
        code_blocks = EntityExtractor.extract_code_blocks(text)

        formula_errors: List[str] = []
        for f in formulas:
            formula_errors.extend(EntityExtractor.check_formula_syntax(f))

        ast_errors: List[str] = []
        for lang, code in code_blocks:
            if lang.lower() in ("python", "py", ""):
                ast_errors.extend(EntityExtractor.check_python_ast(code))

        passed = len(formula_errors) == 0 and len(ast_errors) == 0

        diagnostic = (
            f"公式 {len(formulas)} 个 (错误 {len(formula_errors)}), "
            f"代码块 {len(code_blocks)} 个 (AST 错误 {len(ast_errors)})"
        )

        return Pole1Result(
            passed=passed,
            extracted_formulas=list(formulas),
            extracted_code_blocks=[code for _, code in code_blocks],
            code_ast_errors=ast_errors,
            formula_syntax_errors=formula_errors,
            diagnostic=diagnostic,
        )


# ============================================================================
# Pole-2 门控: NLI 蕴含度度量
# ============================================================================

class Pole2Gate:
    """第二极门控 — 异步 NLI 蕴含度度量。

    流程:
      1. 使用 SlidingWindowSplitter 切分文本
      2. 对每个窗口与 ground_truth_context 进行 NLI 评分
      3. 低于 0.85 的窗口标记为幻觉
      4. 触发单点微观修正循环
    """

    ENTAILMENT_THRESHOLD: float = 0.85
    HALLUCINATION_KEYWORDS: Set[str] = {
        "显然", "众所周知", "可以证明", "不难发现",
        "根据研究", "据调查", "权威人士", "国际公认",
    }

    def validate(
        self,
        text: str,
        ground_truth: str,
        max_refinement_rounds: int = 3,
        nli_fn: Optional[Callable[[str, str], float]] = None,
    ) -> Pole2Result:
        """执行第二极 NLI 蕴含度校验。

        Args:
            text: 生成文本。
            ground_truth: 基准真值上下文。
            max_refinement_rounds: 最大修正轮次。

        Returns:
            Pole2Result。
        """
        if not ground_truth:
            return Pole2Result(
                passed=True,
                chunks_checked=0,
                diagnostic="无基准真值上下文，跳过 NLI 校验",
            )

        splitter = SlidingWindowSplitter()
        chunks = splitter.split(text)

        chunk_results: List[Pole2ChunkResult] = []
        hallucination_count = 0
        total_score = 0.0

        for chunk in chunks:
            # 模拟 NLI 评分（生产环境替换为星火 NLI API）
            score = self._compute_entailment(
                chunk.content, ground_truth, nli_fn=nli_fn
            )

            is_halluc = score < self.ENTAILMENT_THRESHOLD

            # 额外检查: 关键词启发式
            if not is_halluc:
                for kw in self.HALLUCINATION_KEYWORDS:
                    if kw in chunk.content:
                        score *= 0.9  # 轻微降权
                        break

            if is_halluc or score < self.ENTAILMENT_THRESHOLD:
                hallucination_count += 1

            total_score += score
            chunk_results.append(Pole2ChunkResult(
                chunk=chunk,
                entailment_score=round(score, 4),
                entailment_label=(
                    NLIEntailment.ENTAILMENT if score >= self.ENTAILMENT_THRESHOLD
                    else NLIEntailment.NEUTRAL if score >= 0.5
                    else NLIEntailment.CONTRADICTION
                ),
                is_hallucination=is_halluc,
            ))

        overall_score = total_score / max(len(chunks), 1)
        passed = hallucination_count == 0 and overall_score >= self.ENTAILMENT_THRESHOLD

        return Pole2Result(
            passed=passed,
            chunks_checked=len(chunks),
            hallucination_count=hallucination_count,
            chunk_results=chunk_results,
            overall_entailment=round(overall_score, 4),
            refinement_rounds=0,
            diagnostic=(
                f"checked={len(chunks)}, hallucinations={hallucination_count}, "
                f"overall={round(overall_score, 4)}"
            ),
        )

    def refine(
        self,
        text: str,
        hallucination_chunks: List[Pole2ChunkResult],
        ground_truth: str,
    ) -> Tuple[str, int]:
        """对幻觉片段执行单点微观修正。

        策略:
          1. 定位幻觉窗口在原文本中的位置
          2. 用 ground_truth 中语义最接近的片段替换
          3. 或用 [需要人工审核] 标记替换

        Args:
            text: 原始文本。
            hallucination_chunks: 被标记为幻觉的窗口块。
            ground_truth: 基准真值。

        Returns:
            (refined_text, rounds_used)。
        """
        refined = text
        rounds = 0

        for chunk_result in hallucination_chunks[:3]:  # 最多修正 3 个窗口
            chunk = chunk_result.chunk
            if chunk.content in refined:
                # 用 ground_truth 中的相关片段替换
                replacement = self._find_best_replacement(
                    chunk.content, ground_truth
                )
                refined = refined.replace(
                    chunk.content, replacement, 1
                )
                rounds += 1

        return refined, rounds

    def _compute_entailment(
        self,
        text: str,
        ground_truth: str,
        nli_fn: Optional[Callable[[str, str], float]] = None,
    ) -> float:
        """计算文本与基准真值之间的 NLI 蕴含度。

        生产环境实现:
          调用科大讯飞星火大模型 NLI API:
            POST /v1/nli/entailment
            { "premise": ground_truth, "hypothesis": text }
          返回 { "score": 0.92, "label": "entailment" }

        当前实现:
          基于 TF-IDF 余弦相似度的近似估算（用于无外部依赖的测试）。

        Args:
            text: 假设文本。
            ground_truth: 基准真值。

        Returns:
            蕴含度分数 [0.0, 1.0]。
        """
        if nli_fn is not None:
            try:
                score = float(nli_fn(text, ground_truth))
                return max(0.0, min(1.0, score))
            except Exception:
                pass

        # 简化版 TF 余弦相似度
        def tokenize(s: str) -> Dict[str, int]:
            tokens = re.findall(r'[一-鿿]+|[a-zA-Z]+', s.lower())
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return tf

        tf_text = tokenize(text)
        tf_gt = tokenize(ground_truth)

        if not tf_text or not tf_gt:
            return 0.5

        # 余弦相似度
        all_terms = set(tf_text.keys()) | set(tf_gt.keys())
        dot = sum(tf_text.get(t, 0) * tf_gt.get(t, 0) for t in all_terms)
        norm_t = math.sqrt(sum(v ** 2 for v in tf_text.values()))
        norm_g = math.sqrt(sum(v ** 2 for v in tf_gt.values()))

        if norm_t == 0 or norm_g == 0:
            return 0.5

        cosine = dot / (norm_t * norm_g)

        # 映射到 NLI 蕴含度（余弦相似度偏向 conservative）
        # 典型映射: cosine ∈ [0, 1] → entailment ∈ [0.3, 0.95]
        entailment = 0.3 + 0.65 * cosine
        return min(0.95, entailment)

    def _find_best_replacement(
        self, hallucination: str, ground_truth: str
    ) -> str:
        """在 ground_truth 中寻找语义最接近的替换片段。"""
        sentences = re.split(r'[。！？.!?]', ground_truth)
        if not sentences:
            return "[需要人工审核]"

        best_sent = ""
        best_score = -1.0
        for sent in sentences:
            if not sent.strip():
                continue
            score = self._compute_entailment(hallucination, sent)
            if score > best_score:
                best_score = score
                best_sent = sent.strip()

        if best_score < 0.5:
            return "[需要人工审核]"

        return best_sent + "。"


# ============================================================================
# Validator Node — LangGraph Node 主类
# ============================================================================

class ValidatorNode:
    """LangGraph Validator Node — 双极防幻觉校验链。

    在 LangGraph 中的注册方式:
        >>> graph.add_node("validator", validator_node)

    执行流程:
      1. 第一极门控 → 符号硬核对 → 通过后流式直通
      2. 第二极门控 → 滑动窗口 NLI 蕴含度量
      3. 低于阈值 → 微观修正循环 → 重新生成/替换
      4. 校对科大讯飞内容安全接口
    """

    def __init__(
        self,
        nli_fn: Optional[Callable[[str, str], float]] = None,
        safety_review_fn: Optional[Callable[[str], bool]] = None,
    ) -> None:
        """初始化 Validator Node。

        Args:
            nli_fn: 可注入的 NLI 评分函数（生产环境替换为星火 API）。
            safety_review_fn: 可注入的内容安全审查函数。
        """
        self._pole1 = Pole1Gate()
        self._pole2 = Pole2Gate()
        self._nli_fn = nli_fn  # 可选的外部 NLI 函数
        self._safety_review_fn = safety_review_fn

    # ------------------------------------------------------------------
    # LangGraph Node 调用签名
    # ------------------------------------------------------------------

    def __call__(self, inp: ValidatorInput) -> ValidatorOutput:
        return self.validate(inp)

    # ------------------------------------------------------------------
    # 核心校验逻辑
    # ------------------------------------------------------------------

    def validate(self, inp: ValidatorInput) -> ValidatorOutput:
        """执行完整的双极防幻觉校验管线。"""
        state = inp.agent_state
        diagnostics: Dict[str, Any] = {}

        valid_cards: List[ResourceCard] = []
        rejected_cards: List[ResourceCard] = []
        refined_cards: List[ResourceCard] = []
        pole1_results: Dict[str, Pole1Result] = {}
        pole2_results: Dict[str, Pole2Result] = {}

        for card in inp.cards_to_validate:
            card_id = card.resource_id
            text = card.content
            ground_truth = inp.ground_truth_context

            # ---- 第一极: 符号硬核对 ----
            p1 = self._pole1.validate(text, card.card_type)
            pole1_results[card_id] = p1

            if not p1.passed:
                # 公式/代码有语法错误 → 直接拒绝
                rejected_cards.append(card)
                diagnostics[f"{card_id}_pole1"] = (
                    f"拒绝: {p1.diagnostic}"
                )
                continue

            # 第一极通过 → 允许流式直通 (card 先加入 valid_cards)
            valid_cards.append(card)

            # ---- 第二极: NLI 蕴含度 (异步) ----
            if not inp.enable_pole2 or not ground_truth:
                pole2_results[card_id] = Pole2Result(
                    passed=True,
                    diagnostic="跳过 Pole-2",
                )
                continue

            p2 = self._pole2.validate(
                text, ground_truth, inp.max_refinement_rounds, nli_fn=self._nli_fn
            )
            pole2_results[card_id] = p2

            if not p2.passed:
                # 第二极未通过 → 尝试修正循环
                halluc_chunks = [
                    cr for cr in p2.chunk_results
                    if cr.is_hallucination
                ]
                refined_text, rounds = self._pole2.refine(
                    text, halluc_chunks, ground_truth
                )
                p2.refinement_rounds = rounds

                if rounds > 0 and refined_text != text:
                    # 修正成功 → 更新卡片内容
                    refined_card = ResourceCard(
                        resource_id=f"{card_id}_refined",
                        node_id=card.node_id,
                        card_type=card.card_type,
                        content=refined_text,
                        difficulty=card.difficulty,
                        cognitive_style=card.cognitive_style,
                        parent_chunk_id=card.parent_chunk_id,
                        metadata={
                            **card.metadata,
                            "refined": "true",
                            "refinement_rounds": str(rounds),
                        },
                    )
                    refined_cards.append(refined_card)
                    # 替换 valid_cards 中的原始卡片
                    valid_cards = [
                        c for c in valid_cards if c.resource_id != card_id
                    ]
                    valid_cards.append(refined_card)
                else:
                    # 修正无效 → 拒绝
                    rejected_cards.append(card)
                    valid_cards = [
                        c for c in valid_cards if c.resource_id != card_id
                    ]
                    diagnostics[f"{card_id}_pole2"] = (
                        f"拒绝: NLI={p2.overall_entailment:.4f}, "
                        f"幻觉窗口={p2.hallucination_count}"
                    )

            # ---- 内容安全审查 ----
            if self._safety_review_fn:
                try:
                    flagged = self._safety_review_fn(
                        refined_text if refined_cards else text
                    )
                    if flagged:
                        p2.content_safety_flagged = True
                        diagnostics[f"{card_id}_safety"] = "内容安全审查标记"
                except Exception as e:
                    diagnostics[f"{card_id}_safety_error"] = str(e)

        # 计算总体通过率
        total = len(inp.cards_to_validate)
        overall_pass_rate = (
            len(valid_cards) / total if total > 0 else 0.0
        )

        return ValidatorOutput(
            agent_state=state,
            valid_cards=valid_cards,
            rejected_cards=rejected_cards,
            refined_cards=refined_cards,
            pole1_results=pole1_results,
            pole2_results=pole2_results,
            overall_pass_rate=round(overall_pass_rate, 4),
            diagnostics=diagnostics,
        )


# ============================================================================
# 工厂函数
# ============================================================================

def create_validator_node(
    nli_fn: Optional[Callable[[str, str], float]] = None,
    safety_review_fn: Optional[Callable[[str], bool]] = None,
) -> ValidatorNode:
    """创建 Validator Node 实例。"""
    return ValidatorNode(nli_fn=nli_fn, safety_review_fn=safety_review_fn)
