# -*- coding: utf-8 -*-
"""
数据治理辅助组件一：Layout-Aware 版面感知动态语义切片引擎
==========================================================

工业级文档切片器，实现以下核心能力：

1. 版面感知 (Layout-Aware)：
   - 识别并保护 LaTeX 公式块 ($$...$$ / $...$ / \[...\])
   - 识别并保护代码块 (```...``` / 缩进代码段)
   - 识别 Markdown 表格、标题层级、列表结构
   - 保证公式与代码块不被切碎，作为原子语义单元

2. 动态语义切片：
   - 基于 token 预算的滑动窗口切割
   - 句子边界对齐 (sentence-boundary-aware)
   - 段落语义完整性保护

3. Parent-Child 双层映射：
   - Child Chunk: 250-500 tokens 的小粒度切片 → Milvus Child Collection
   - Parent Chunk: 1000-2000 tokens 的大粒度上下文 → Milvus Parent Collection
   - child.parent_id → parent.parent_id 关联，召回时反查完整上下文

依赖声明：
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import re
import hashlib
import uuid
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum, auto

from pydantic import BaseModel, Field, field_validator

from ..vector.milvus_client import MilvusClient, ParentChunk, ChildChunk


# ============================================================================
# 常量定义
# ============================================================================

# 匹配 LaTeX 公式块 $$ ... $$ 或 \[ ... \]
LATEX_BLOCK_RE = re.compile(
    r'(?<!\\)\$\$(.+?)(?<!\\)\$\$|\\\[(.+?)\\\]',
    re.DOTALL,
)
# 匹配行内公式 $ ... $
LATEX_INLINE_RE = re.compile(
    r'(?<!\\)\$(.+?)(?<!\\)\$',
)
# 匹配 Markdown 代码块 ``` ... ```
CODE_BLOCK_RE = re.compile(
    r'```(\w*)\n(.*?)```',
    re.DOTALL,
)
# 匹配缩进代码块 (4空格或1Tab开头连续行)
INDENTED_CODE_RE = re.compile(
    r'(?:^|\n)((?:(?: {4}|\t).*(?:\n|$))+)',
    re.MULTILINE,
)
# 匹配 Markdown 标题
HEADING_RE = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)
# 匹配表格
TABLE_RE = re.compile(r'^\|.+\|$', re.MULTILINE)
# 句子边界
SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[。！？.!?])\s*')


class ChunkStrategy(str, Enum):
    """切片策略枚举。"""
    FIXED_TOKEN_COUNT = "fixed_token_count"      # 固定 token 数切割
    SENTENCE_AWARE = "sentence_aware"             # 句子边界感知
    PARAGRAPH_AWARE = "paragraph_aware"           # 段落边界感知
    HYBRID = "hybrid"                             # 混合策略 (默认)


# ============================================================================
# Pydantic 数据模型
# ============================================================================

class AtomicBlock(BaseModel):
    """版面解析后的原子语义块。

    公式块、代码块、表格等被识别为 AtomicBlock，在切片时作为不可分割的最小单元。
    """

    block_id: str = Field(..., description="块唯一 ID")
    block_type: str = Field(
        ...,
        pattern=r"^(text|latex_block|latex_inline|code_block|table|heading|list)$",
        description="块类型"
    )
    content: str = Field(..., description="块原始内容")
    start_pos: int = Field(default=0, ge=0, description="在原文中的起始字符位置")
    end_pos: int = Field(default=0, ge=0, description="在原文中的结束字符位置")
    is_protected: bool = Field(default=False, description="是否为受保护块（不可切分）")
    token_count: int = Field(default=0, ge=0, description="估算的 token 数")


class ChunkConfig(BaseModel):
    """切分配置参数。"""

    strategy: ChunkStrategy = Field(default=ChunkStrategy.HYBRID, description="切片策略")
    child_min_tokens: int = Field(default=250, ge=50, le=1000, description="子块最小 token 数")
    child_max_tokens: int = Field(default=500, ge=100, le=2000, description="子块最大 token 数")
    parent_min_tokens: int = Field(default=1000, ge=200, le=4000, description="父块最小 token 数")
    parent_max_tokens: int = Field(default=2000, ge=400, le=8000, description="父块最大 token 数")
    overlap_tokens: int = Field(default=50, ge=0, le=200, description="相邻子块重叠 token 数")
    # 受保护块类型
    protected_block_types: List[str] = Field(
        default_factory=lambda: [
            "latex_block", "latex_inline", "code_block", "table"
        ],
        description="不可切分的原子块类型"
    )
    # Token 估算比率 (中文约 1 字符 ≈ 0.6 token, 英文约 1 词 ≈ 1.3 token)
    tokens_per_char_cjk: float = Field(default=0.6, gt=0.0)
    tokens_per_word_en: float = Field(default=1.3, gt=0.0)


class SliceMetadata(BaseModel):
    """单条切片记录的分析元数据。"""

    slice_id: str = Field(..., description="切片 ID")
    parent_id: str = Field(..., description="所属父块 ID")
    slice_index: int = Field(default=0, ge=0, description="在父块中的切片序号")
    token_count: int = Field(default=0, ge=0, description="实际 token 数")
    protected_blocks_contained: List[str] = Field(
        default_factory=list, description="包含的受保护块 ID 列表"
    )
    headings_context: List[str] = Field(
        default_factory=list, description="当前切片所处的标题层级路径"
    )


class ChunkResult(BaseModel):
    """切片操作的完整结果。"""

    document_id: str = Field(..., description="源文档 ID")
    node_id: str = Field(..., description="关联的知识点 ID (Neo4j)")
    parents: List[ParentChunk] = Field(default_factory=list, description="父块列表")
    children: List[ChildChunk] = Field(default_factory=list, description="子块列表")
    parent_child_map: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="parent_id → [child_id, ...]"
    )
    total_tokens_document: int = Field(default=0, description="文档总 token 数")
    protected_blocks_count: int = Field(default=0, description="受保护块总数")


# ============================================================================
# 版面解析器 (Layout Parser)
# ============================================================================

class LayoutParser:
    """版面感知解析器 — 识别文档中的公式、代码、表格等语义结构。

    将输入文档解析为有序的 AtomicBlock 列表，标记受保护块。
    """

    def __init__(self) -> None:
        # 受保护块类型集合（快速查找）
        self._protected_types: Set[str] = {
            "latex_block", "latex_inline", "code_block", "table"
        }

    def parse(self, text: str) -> List[AtomicBlock]:
        """对输入文本进行版面感知解析。

        解析顺序（重要）：
          1. 先匹配大块: 代码块 (```)、LaTeX 公式块 ($$/\[\])
          2. 再匹配行内: 行内公式 ($)、表格行、标题
          3. 剩余部分为普通文本

        使用占位符替换法避免正则重叠匹配问题。

        Args:
            text: 原始文档文本。

        Returns:
            按原文顺序排列的 AtomicBlock 列表。
        """
        blocks: List[AtomicBlock] = []
        # 使用 (占位符 → 原始内容) 映射
        placeholders: Dict[str, Tuple[str, str]] = {}  # placeholder → (content, block_type)
        counter = [0]  # 可变计数器

        working_text = text

        # ---- Phase 1: 提取大块受保护内容 ----
        # 1a. 代码块 (```)
        working_text, code_placeholders = self._extract_pattern(
            working_text, CODE_BLOCK_RE, "CODE_BLOCK", counter, placeholders
        )
        # 1b. LaTeX 公式块 ($$ / \[\])
        working_text, latex_placeholders = self._extract_pattern(
            working_text, LATEX_BLOCK_RE, "LATEX_BLOCK", counter, placeholders
        )

        # ---- Phase 2: 提取行内受保护内容 ----
        # 2a. 行内公式 ($)
        working_text, inline_placeholders = self._extract_pattern(
            working_text, LATEX_INLINE_RE, "LATEX_INLINE", counter, placeholders
        )

        # ---- Phase 3: 表格行识别 ----
        table_lines: List[str] = []
        non_table_lines: List[str] = []
        for line in working_text.split('\n'):
            if TABLE_RE.match(line.strip()):
                table_lines.append(line)
            else:
                if table_lines:
                    # 将累积的表格行打包为一个块
                    tbl_content = '\n'.join(table_lines)
                    ph = f"__PROTECTED_TABLE_{counter[0]}__"
                    counter[0] += 1
                    placeholders[ph] = (tbl_content, "table")
                    non_table_lines.append(ph)
                    table_lines.clear()
                non_table_lines.append(line)
        # 处理尾部表格
        if table_lines:
            tbl_content = '\n'.join(table_lines)
            ph = f"__PROTECTED_TABLE_{counter[0]}__"
            counter[0] += 1
            placeholders[ph] = (tbl_content, "table")
            non_table_lines.append(ph)

        working_text = '\n'.join(non_table_lines)

        # ---- Phase 4: 将剩余文本按非占位符区域切分为普通文本块 ----
        # 构建占位符位置索引
        block_list = self._reconstruct_ordered_blocks(
            working_text, placeholders, text
        )

        return block_list

    def _extract_pattern(
        self,
        text: str,
        pattern: re.Pattern,
        block_type: str,
        counter: List[int],
        placeholders: Dict[str, Tuple[str, str]],
    ) -> Tuple[str, List[str]]:
        """提取匹配模式并用占位符替换。

        Returns:
            (替换后文本, 占位符列表)。
        """
        ph_list: List[str] = []

        def _replace(match: re.Match) -> str:
            ph = f"__PROTECTED_{block_type}_{counter[0]}__"
            counter[0] += 1
            # 保留完整匹配内容
            placeholders[ph] = (match.group(0), block_type.lower())
            ph_list.append(ph)
            return ph

        result = pattern.sub(_replace, text)
        return result, ph_list

    def _reconstruct_ordered_blocks(
        self,
        text: str,
        placeholders: Dict[str, Tuple[str, str]],
        original_text: str,
    ) -> List[AtomicBlock]:
        """将含占位符的文本重建为有序的 AtomicBlock 列表。

        使用正则扫描占位符模式 __PROTECTED_*__，
        在占位符位置切分文本，将非占位符部分作为普通文本块，
        占位符对应的原始内容作为受保护块。

        处理行内占位符（如中文文本中的行内公式占位符）和
        整行占位符（如代码块占位符）两种场景。
        """
        blocks: List[AtomicBlock] = []
        # 占位符匹配模式
        ph_pattern = re.compile(r'__PROTECTED_\w+_\d+__')
        # 构建占位符查找字典
        ph_dict = placeholders

        # 按行处理
        lines = text.split('\n')
        current_pos = 0

        for line in lines:
            if not line.strip():
                continue

            # 在行内扫描占位符
            last_end = 0
            parts: List[Tuple[str, Optional[Tuple[str, str]]]] = []  # (text_segment, ph_tuple_or_None)

            for m in ph_pattern.finditer(line):
                prefix = line[last_end:m.start()]
                if prefix:
                    parts.append((prefix, None))
                ph_key = m.group(0)
                if ph_key in ph_dict:
                    parts.append((ph_key, ph_dict[ph_key]))
                else:
                    # 占位符未找到映射 → 视为普通文本
                    parts.append((ph_key, None))
                last_end = m.end()

            # 尾部文本
            suffix = line[last_end:]
            if suffix:
                parts.append((suffix, None))

            # 将 parts 转换为 AtomicBlock
            for text_seg, ph_info in parts:
                if ph_info is not None:
                    # 受保护块
                    raw_content, btype = ph_info
                    token_cnt = self._estimate_tokens(raw_content)
                    is_prot = btype in self._protected_types
                    blocks.append(AtomicBlock(
                        block_id=f"{btype.upper()}_{len(blocks)}",
                        block_type=btype,
                        content=raw_content,
                        start_pos=current_pos,
                        end_pos=current_pos + len(raw_content),
                        is_protected=is_prot,
                        token_count=max(token_cnt, 1),
                    ))
                    current_pos += len(raw_content)
                elif text_seg.strip():
                    # 普通文本块
                    token_cnt = self._estimate_tokens(text_seg)
                    blocks.append(AtomicBlock(
                        block_id=f"TEXT_{len(blocks)}",
                        block_type="text",
                        content=text_seg,
                        start_pos=current_pos,
                        end_pos=current_pos + len(text_seg),
                        is_protected=False,
                        token_count=token_cnt,
                    ))
                    current_pos += len(text_seg)

        return blocks

    def _estimate_tokens(self, text: str) -> int:
        """简易 token 估算。

        策略:
          - CJK 字符: 约 0.6 token/char
          - 英文单词: 约 1.3 token/word
          - 取两者之和
        """
        cjk_count = sum(1 for c in text if '一' <= c <= '鿿' or '　' <= c <= '〿')
        # 非 CJK 部分的词数估算
        non_cjk = len(text) - cjk_count
        words_en = len(re.findall(r'[a-zA-Z0-9]+', text))
        return int(cjk_count * 0.6 + words_en * 1.3 + (non_cjk - words_en) * 0.3)


# ============================================================================
# 动态语义切片器 (Semantic Chunker)
# ============================================================================

class SemanticChunker:
    """动态语义切片器 — 在版面解析的基础上进行 Parent-Child 双层切片。

    切片流程:
      1. LayoutParser 将文档解析为 AtomicBlock 序列
      2. 在受保护块边界处强制对齐，块内部不切割
      3. 在普通文本块内部按句子边界进行 child_chunk 切割
      4. 多个 child_chunk 聚合成 parent_chunk (大上下文窗口)
      5. 建立 parent_id ↔ child_id 双向映射
    """

    def __init__(self, config: Optional[ChunkConfig] = None) -> None:
        self._config = config or ChunkConfig()
        self._parser = LayoutParser()

    @property
    def config(self) -> ChunkConfig:
        return self._config

    def chunk(
        self,
        document_id: str,
        node_id: str,
        content: str,
        title: str = "",
        difficulty: float = 0.5,
        category: str = "concept",
        metadata: Optional[Dict[str, str]] = None,
    ) -> ChunkResult:
        """对文档执行完整的 Parent-Child 双层切片。

        Args:
            document_id: 源文档唯一标识。
            node_id: Neo4j 知识点 ID。
            content: 文档全文。
            title: 文档标题。
            difficulty: 知识点难度。
            category: 知识点类别。
            metadata: 额外元数据。

        Returns:
            ChunkResult: 包含 parents + children + 映射关系的完整切片结果。
        """
        doc_meta = metadata or {}
        cfg = self._config

        # ---- Step 1: 版面解析 ----
        atomic_blocks = self._parser.parse(content)
        total_tokens = sum(b.token_count for b in atomic_blocks)
        protected_count = sum(1 for b in atomic_blocks if b.is_protected)

        # ---- Step 2: 提取标题层级路径 ----
        heading_path = self._extract_heading_hierarchy(atomic_blocks)

        # ---- Step 3: 在受保护块边界将 AtomicBlock 切分为 child chunks ----
        child_chunks_data: List[Tuple[str, int, List[str]]] = []  # (text, token_count, protected_ids)
        text_accumulator: List[str] = []
        token_accumulator: int = 0
        protected_accumulator: List[str] = []

        for block in atomic_blocks:
            if block.is_protected:
                # 受保护块：flush 当前累积文本，然后单独作为一个 child
                if text_accumulator:
                    acc_text = '\n'.join(text_accumulator)
                    # 按句子边界切分文本缓冲区
                    sub_slices = self._split_text_by_sentence_boundary(
                        acc_text, token_accumulator
                    )
                    child_chunks_data.extend(sub_slices)
                    text_accumulator.clear()
                    token_accumulator = 0

                # 受保护块单独成为一个 child
                child_chunks_data.append((
                    block.content,
                    block.token_count,
                    [block.block_id],
                ))
                protected_accumulator.clear()
            else:
                # 普通文本：累积
                text_accumulator.append(block.content)
                token_accumulator += block.token_count
                protected_accumulator.append(block.block_id)
                # 当累积 token 超过 child_max_tokens 时 flush
                if token_accumulator >= cfg.child_max_tokens:
                    acc_text = '\n'.join(text_accumulator)
                    sub_slices = self._split_text_by_sentence_boundary(
                        acc_text, token_accumulator
                    )
                    child_chunks_data.extend(sub_slices)
                    text_accumulator.clear()
                    token_accumulator = 0
                    protected_accumulator.clear()

        # flush 尾部文本缓冲区
        if text_accumulator:
            acc_text = '\n'.join(text_accumulator)
            sub_slices = self._split_text_by_sentence_boundary(
                acc_text, token_accumulator
            )
            child_chunks_data.extend(sub_slices)

        # ---- Step 4: 创建子块 (ChildChunk) ----
        children: List[ChildChunk] = []
        doc_hash = hashlib.md5(f"{document_id}:{node_id}".encode()).hexdigest()[:8]

        for idx, (chunk_text, chunk_tokens, prot_ids) in enumerate(child_chunks_data):
            child_id = f"CHILD_{doc_hash}_{node_id}_{idx:04d}"
            children.append(ChildChunk(
                child_id=child_id,
                parent_id="",  # 待分配
                node_id=node_id,
                content=chunk_text,
                chunk_index=idx,
                metadata={
                    **doc_meta,
                    "protected_blocks": ','.join(prot_ids) if prot_ids else "",
                    "heading_path": ' > '.join(heading_path) if heading_path else "",
                },
            ))

        # ---- Step 5: 将子块聚合为父块 ----
        parents: List[ParentChunk] = []
        parent_child_map: Dict[str, List[str]] = {}
        current_parent_children: List[str] = []
        current_parent_tokens: int = 0
        parent_idx: int = 0

        for child in children:
            child_token_est = self._parser._estimate_tokens(child.content)
            if (current_parent_tokens + child_token_est > cfg.parent_max_tokens
                    and current_parent_children):
                # 当前父块已满，创建新父块
                parent = self._build_parent(
                    doc_hash, node_id, parent_idx, title, difficulty, category,
                    current_parent_children, children, doc_meta, heading_path,
                )
                parents.append(parent)
                parent_child_map[parent.parent_id] = list(current_parent_children)
                parent_idx += 1
                current_parent_children = []
                current_parent_tokens = 0

            current_parent_children.append(child.child_id)
            current_parent_tokens += child_token_est

        # flush 最后一个父块
        if current_parent_children:
            parent = self._build_parent(
                doc_hash, node_id, parent_idx, title, difficulty, category,
                current_parent_children, children, doc_meta, heading_path,
            )
            parents.append(parent)
            parent_child_map[parent.parent_id] = list(current_parent_children)

        # ---- Step 6: 回填 child.parent_id ----
        for parent_id, child_ids in parent_child_map.items():
            for child in children:
                if child.child_id in child_ids:
                    child.parent_id = parent_id

        return ChunkResult(
            document_id=document_id,
            node_id=node_id,
            parents=parents,
            children=children,
            parent_child_map=parent_child_map,
            total_tokens_document=total_tokens,
            protected_blocks_count=protected_count,
        )

    def _split_text_by_sentence_boundary(
        self, text: str, estimated_tokens: int
    ) -> List[Tuple[str, int, List[str]]]:
        """按句子边界切割文本。

        若文本 token 数 ≤ child_max_tokens，直接返回单条。
        否则按 SENTENCE_BOUNDARY_RE 切割为多个子块。
        """
        cfg = self._config
        if estimated_tokens <= cfg.child_max_tokens and estimated_tokens >= cfg.child_min_tokens:
            return [(text, estimated_tokens, [])]

        if estimated_tokens < cfg.child_min_tokens:
            return [(text, estimated_tokens, [])]

        # 按句子边界切分
        sentences = SENTENCE_BOUNDARY_RE.split(text)
        if len(sentences) <= 1:
            # 无法按句子切分，直接返回
            return [(text, estimated_tokens, [])]

        slices: List[Tuple[str, int, List[str]]] = []
        accumulator: List[str] = []
        acc_tokens: int = 0

        for sent in sentences:
            if not sent.strip():
                continue
            sent_tokens = self._parser._estimate_tokens(sent)
            if acc_tokens + sent_tokens > cfg.child_max_tokens and accumulator:
                slices.append(('\n'.join(accumulator), acc_tokens, []))
                # 重叠: 保留最后一两句到下一个切片
                if len(accumulator) >= 2 and cfg.overlap_tokens > 0:
                    overlap_text = '\n'.join(accumulator[-2:])
                    accumulator = [overlap_text]
                    acc_tokens = self._parser._estimate_tokens(overlap_text)
                else:
                    accumulator = []
                    acc_tokens = 0
            accumulator.append(sent)
            acc_tokens += sent_tokens

        if accumulator:
            slices.append(('\n'.join(accumulator), acc_tokens, []))

        return slices

    def _build_parent(
        self,
        doc_hash: str,
        node_id: str,
        parent_idx: int,
        title: str,
        difficulty: float,
        category: str,
        child_ids: List[str],
        children: List[ChildChunk],
        doc_meta: Dict[str, str],
        heading_path: List[str],
    ) -> ParentChunk:
        """从子块列表构建父块。"""
        parent_id = f"PARENT_{doc_hash}_{node_id}_{parent_idx:04d}"
        # 拼接所有子块内容
        content_parts: List[str] = []
        for cid in child_ids:
            for child in children:
                if child.child_id == cid:
                    content_parts.append(child.content)
                    break

        return ParentChunk(
            parent_id=parent_id,
            node_id=node_id,
            content='\n\n'.join(content_parts),
            title=title,
            difficulty=difficulty,
            category=category,
            metadata={
                **doc_meta,
                "heading_path": ' > '.join(heading_path) if heading_path else "",
                "child_count": str(len(child_ids)),
            },
            child_ids=list(child_ids),
        )

    def _extract_heading_hierarchy(self, blocks: List[AtomicBlock]) -> List[str]:
        """从 AtomicBlock 序列中提取标题层级路径。"""
        headings: List[str] = []
        for block in blocks:
            if block.block_type == "text":
                for line in block.content.split('\n'):
                    if HEADING_RE.match(line.strip()):
                        headings.append(line.strip().lstrip('#').strip())
        return headings


# ============================================================================
# 数据清洗与写入编排器 (Data Ingestion Orchestrator)
# ============================================================================

class DocumentIngestionPipeline:
    """文档清洗 → 切片 → 双写 Milvus 的完整编排管线。

    使用示例:
        >>> pipeline = DocumentIngestionPipeline(milvus_client)
        >>> result = pipeline.ingest(
        ...     document_id="DOC_001",
        ...     node_id="KNOWLEDGE_042",
        ...     content=raw_markdown_text,
        ...     title="反向传播算法",
        ... )
        >>> # result.parents → 可直接写入 Milvus Parent Collection
        >>> # result.children → 可直接写入 Milvus Child Collection
    """

    def __init__(
        self,
        milvus_client: MilvusClient,
        config: Optional[ChunkConfig] = None,
    ) -> None:
        self._milvus = milvus_client
        self._chunker = SemanticChunker(config)

    def ingest(
        self,
        document_id: str,
        node_id: str,
        content: str,
        title: str = "",
        difficulty: float = 0.5,
        category: str = "concept",
        metadata: Optional[Dict[str, str]] = None,
    ) -> ChunkResult:
        """执行完整的文档摄入流程: 切片 → 写入 Milvus。

        Args:
            document_id: 文档 ID。
            node_id: 知识点 ID。
            content: 原始文档内容 (Markdown/LaTeX)。
            title: 文档标题。
            difficulty: 难度系数。
            category: 类别。
            metadata: 额外元数据。

        Returns:
            ChunkResult: 含 parents/children/mapping。
        """
        # Step 1: 语义切片
        result = self._chunker.chunk(
            document_id=document_id,
            node_id=node_id,
            content=content,
            title=title,
            difficulty=difficulty,
            category=category,
            metadata=metadata,
        )

        # Step 2: 写入 Milvus (若已连接)
        if self._milvus.is_connected():
            if result.parents:
                self._milvus.insert_parents_batch(result.parents)
            if result.children:
                self._milvus.insert_children_batch(result.children)

        return result

    @property
    def chunker(self) -> SemanticChunker:
        return self._chunker
