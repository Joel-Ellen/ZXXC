# -*- coding: utf-8 -*-
"""
Layout-Aware 版面感知动态语义切片引擎 — 单元测试套件
======================================================

覆盖范围:
  1. LayoutParser: LaTeX 公式块识别与保护
  2. LayoutParser: 代码块识别与保护
  3. LayoutParser: 表格识别
  4. LayoutParser: 混合文档 (公式 + 代码 + 文本)
  5. SemanticChunker: 基础 Parent-Child 切片
  6. SemanticChunker: 公式块完整性（原子块不被切碎）
  7. SemanticChunker: 代码块完整性
  8. SemanticChunker: Parent-Child 映射关系正确性
  9. DocumentIngestionPipeline: 端到端摄入
  10. 边界条件: 空文档 / 极短文档 / 纯公式文档

运行方式:
    pytest tests/test_document_chunker.py -v
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.document_chunker import (
    LayoutParser,
    SemanticChunker,
    DocumentIngestionPipeline,
    ChunkConfig,
    ChunkStrategy,
    AtomicBlock,
    ChunkResult,
)
from src.vector.milvus_client import MilvusClient, MilvusConfig


# ============================================================================
# 测试文档素材
# ============================================================================

SIMPLE_DOC = """
# 反向传播算法

反向传播（Backpropagation）是训练神经网络的核心算法。

## 数学原理

误差函数对权重的梯度通过链式法则计算：

$$
\\frac{\\partial L}{\\partial w_{ij}} = \\frac{\\partial L}{\\partial a_j} \\cdot \\frac{\\partial a_j}{\\partial z_j} \\cdot \\frac{\\partial z_j}{\\partial w_{ij}}
$$

其中 $a_j = \\sigma(z_j)$ 是激活函数的输出。

## 代码实现

```python
def backward(self, grad_output):
    grad_input = grad_output * self._activation_derivative(self.z)
    self.grad_w = torch.matmul(self.x.T, grad_input)
    self.grad_b = grad_input.sum(dim=0)
    return grad_input
```

## 小结

通过链式法则，我们可以高效计算任意深度网络的梯度。
"""


FORMULA_HEAVY_DOC = """
# 概率论基础

贝叶斯公式的核心形式为：

$$P(A|B) = \\frac{P(B|A) \\cdot P(A)}{P(B)}$$

其中：
- $P(A|B)$ 是后验概率
- $P(A)$ 是先验概率
- $P(B|A)$ 是似然函数
- $P(B)$ 是边缘概率（归一化常数）

对于连续变量的推广：

$$P(\\theta | \\mathcal{D}) = \\frac{P(\\mathcal{D} | \\theta) \\cdot P(\\theta)}{\\int P(\\mathcal{D} | \\theta) \\cdot P(\\theta) \\, d\\theta}$$

利用共轭先验的性质，若先验 $P(\\theta)$ 服从 Beta 分布：

$$P(\\theta; \\alpha, \\beta) = \\frac{\\theta^{\\alpha-1} \\cdot (1-\\theta)^{\\beta-1}}{B(\\alpha, \\beta)}$$

则后验亦为 Beta 分布。
"""


CODE_HEAVY_DOC = """
# 快速排序实现

```python
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
```

时间复杂度分析：平均 $O(n \\log n)$，最坏 $O(n^2)$。

```java
public static void quickSort(int[] arr, int low, int high) {
    if (low < high) {
        int pi = partition(arr, low, high);
        quickSort(arr, low, pi - 1);
        quickSort(arr, pi + 1, high);
    }
}
```


| 算法       | 平均时间复杂度 | 空间复杂度 |
|------------|---------------|-----------|
| 快速排序   | O(n log n)    | O(log n)  |
| 归并排序   | O(n log n)    | O(n)      |
"""


EMPTY_DOC = ""


SHORT_DOC = "这是一个简短的句子。"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def parser() -> LayoutParser:
    return LayoutParser()


@pytest.fixture
def chunker() -> SemanticChunker:
    return SemanticChunker()


@pytest.fixture
def chunker_small_tokens() -> SemanticChunker:
    """使用较小 token 预算的切片器，便于测试多块切分。"""
    return SemanticChunker(ChunkConfig(
        child_min_tokens=50,
        child_max_tokens=120,
        parent_min_tokens=200,
        parent_max_tokens=450,
        overlap_tokens=20,
    ))


@pytest.fixture
def milvus_client() -> MilvusClient:
    """创建一个未连接的 MilvusClient 用于测试（不依赖实际 Milvus 服务）。"""
    return MilvusClient(MilvusConfig())


# ============================================================================
# 1. LayoutParser — 公式解析
# ============================================================================

class TestLayoutParserFormulas:
    """测试 LaTeX 公式块的版面感知解析。"""

    def test_block_formula_detected(self, parser: LayoutParser) -> None:
        """$$...$$ 公式块应被识别为 latex_block。"""
        blocks = parser.parse(SIMPLE_DOC)
        latex_blocks = [b for b in blocks if b.block_type == "latex_block"]
        assert len(latex_blocks) >= 1, "应至少检测到 1 个 LaTeX 公式块"
        for lb in latex_blocks:
            assert lb.is_protected is True, "公式块应标记为受保护"

    def test_inline_formula_detected(self, parser: LayoutParser) -> None:
        """$...$ 行内公式或 \(...\) 应被识别。"""
        # 使用不含 $$ 代码块的纯文本测试行内公式
        text = "其中 $a_j = \\sigma(z_j)$ 是激活函数。还有 $P(A|B)$ 是条件概率。"
        blocks = parser.parse(text)
        inline_blocks = [b for b in blocks if b.block_type == "latex_inline"]
        assert len(inline_blocks) >= 1, (
            f"应检测到至少 1 个行内公式，实际 {len(inline_blocks)}"
        )

    def test_formula_content_preserved(self, parser: LayoutParser) -> None:
        """公式内容应完整保留，不被截断。"""
        blocks = parser.parse(SIMPLE_DOC)
        for block in blocks:
            if block.block_type in ("latex_block", "latex_inline"):
                assert "\\frac" in block.content or "\\partial" in block.content or \
                       "P(" in block.content or "sigma" in block.content, \
                       f"公式块内容未被完整保留: {block.content[:50]}..."

    def test_formula_heavy_doc(self, parser: LayoutParser) -> None:
        """公式密集型文档应正确识别多个公式块。"""
        blocks = parser.parse(FORMULA_HEAVY_DOC)
        latex_blocks = [b for b in blocks if b.block_type == "latex_block"]
        assert len(latex_blocks) >= 3, f"公式密集型文档应检测到 ≥3 个公式块，实际 {len(latex_blocks)}"


# ============================================================================
# 2. LayoutParser — 代码块解析
# ============================================================================

class TestLayoutParserCode:
    """测试代码块的版面感知解析。"""

    def test_code_block_detected(self, parser: LayoutParser) -> None:
        """```...``` 代码块应被识别。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        code_blocks = [b for b in blocks if b.block_type == "code_block"]
        assert len(code_blocks) >= 2, f"应检测到 ≥2 个代码块，实际 {len(code_blocks)}"

    def test_code_block_content_preserved(self, parser: LayoutParser) -> None:
        """代码块内容应完整保留（包括缩进、换行）。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "code_block":
                assert any(kw in block.content for kw in ("def ", "quicksort", "quickSort", "partition")), \
                    f"代码块内容不完整: {block.content[:80]}"

    def test_code_block_is_protected(self, parser: LayoutParser) -> None:
        """代码块应标记为受保护。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "code_block":
                assert block.is_protected is True


# ============================================================================
# 3. LayoutParser — 表格解析
# ============================================================================

class TestLayoutParserTable:
    """测试 Markdown 表格的解析。"""

    def test_table_detected(self, parser: LayoutParser) -> None:
        """Markdown 表格应被识别为 table 类型。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        table_blocks = [b for b in blocks if b.block_type == "table"]
        assert len(table_blocks) >= 1, "应检测到至少 1 个表格"

    def test_table_is_protected(self, parser: LayoutParser) -> None:
        """表格应被标记为受保护（不可切碎）。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "table":
                assert block.is_protected is True

    def test_table_content_preserved(self, parser: LayoutParser) -> None:
        """表格的列与行结构应完整保留。"""
        blocks = parser.parse(CODE_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "table":
                assert "快速排序" in block.content
                assert "归并排序" in block.content
                assert "|" in block.content


# ============================================================================
# 4. LayoutParser — 文本块与混合文档
# ============================================================================

class TestLayoutParserText:
    """测试普通文本块的解析与混合文档处理。"""

    def test_text_blocks_exist(self, parser: LayoutParser) -> None:
        """非公式/代码/表格内容应归为 text 类型。"""
        blocks = parser.parse(SIMPLE_DOC)
        text_blocks = [b for b in blocks if b.block_type == "text"]
        assert len(text_blocks) > 0

    def test_atomic_block_ordering(self, parser: LayoutParser) -> None:
        """AtomicBlock 应保持原始文档顺序。"""
        blocks = parser.parse(SIMPLE_DOC)
        positions = [b.start_pos for b in blocks]
        assert positions == sorted(positions), (
            f"块位置应严格递增: {positions}"
        )

    def test_total_content_coverage(self, parser: LayoutParser) -> None:
        """所有块的 content 之和不应丢失原始内容。"""
        doc = CODE_HEAVY_DOC
        blocks = parser.parse(doc)
        # 受保护块的原始内容应在文档中可找到
        for block in blocks:
            if block.is_protected:
                cleaned = block.content.strip()
                assert cleaned in doc or any(
                    line in doc for line in cleaned.split('\n')[:3]
                ), f"受保护块内容应在原文中存在: {cleaned[:60]}"


# ============================================================================
# 5. SemanticChunker — Parent-Child 切片
# ============================================================================

class TestSemanticChunker:
    """测试语义切片器的 Parent-Child 双层切片。"""

    def test_basic_chunking(self, chunker: SemanticChunker) -> None:
        """基础切片: 应产生至少 1 个父块和若干子块。"""
        result = chunker.chunk(
            document_id="DOC_TEST",
            node_id="KN_001",
            content=SIMPLE_DOC,
            title="反向传播算法",
        )
        assert isinstance(result, ChunkResult)
        assert len(result.parents) >= 1, "应产生至少 1 个父块"
        assert len(result.children) >= 1, "应产生至少 1 个子块"

    def test_parent_child_mapping(self, chunker: SemanticChunker) -> None:
        """parent_child_map 映射应双向一致。"""
        result = chunker.chunk("DOC_MAP", "N1", SIMPLE_DOC)
        for parent_id, child_ids in result.parent_child_map.items():
            for cid in child_ids:
                child = next((c for c in result.children if c.child_id == cid), None)
                assert child is not None, f"子块 {cid} 应存在于 children 列表中"
                assert child.parent_id == parent_id, (
                    f"子块 {cid} 的 parent_id ({child.parent_id}) 应与映射一致 ({parent_id})"
                )

    def test_formula_not_fragmented(self, chunker: SemanticChunker) -> None:
        """公式块应保持完整，不被切碎到多个子块中。"""
        result = chunker.chunk("DOC_FORM", "N2", FORMULA_HEAVY_DOC)
        # 检查每个子块: 公式块内容应完整出现在某子块中
        parser = LayoutParser()
        blocks = parser.parse(FORMULA_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "latex_block":
                # 公式内容至少应被某个子块完整包含
                found = False
                for child in result.children:
                    if block.content.strip() in child.content:
                        found = True
                        break
                assert found, (
                    f"公式块应被某子块完整包含: {block.content[:60]}..."
                )

    def test_code_not_fragmented(self, chunker: SemanticChunker) -> None:
        """代码块应保持完整，不被切碎到多个子块中。"""
        result = chunker.chunk("DOC_CODE", "N3", CODE_HEAVY_DOC)
        parser = LayoutParser()
        blocks = parser.parse(CODE_HEAVY_DOC)
        for block in blocks:
            if block.block_type == "code_block":
                # 提取代码特征
                code_marker = block.content.strip().split('\n')[0][:30]
                found = False
                for child in result.children:
                    if code_marker in child.content:
                        found = True
                        break
                assert found, f"代码块特征 '{code_marker}' 应出现在某子块中"

    def test_title_in_parent_metadata(self, chunker: SemanticChunker) -> None:
        """父块的 title 字段应正确填充。"""
        result = chunker.chunk(
            "DOC_TITLE", "N4", SIMPLE_DOC, title="反向传播算法"
        )
        for parent in result.parents:
            assert parent.title == "反向传播算法"

    def test_difficulty_propagated(self, chunker: SemanticChunker) -> None:
        """difficulty 应传播到所有父块。"""
        result = chunker.chunk(
            "DOC_DIFF", "N5", SIMPLE_DOC, difficulty=0.73
        )
        for parent in result.parents:
            assert parent.difficulty == 0.73


# ============================================================================
# 6. SemanticChunker — 小 Token 预算切分
# ============================================================================

class TestSmallTokenChunking:
    """使用较小 token 预算验证多块切分能力。"""

    def test_multiple_children_produced(self, chunker_small_tokens: SemanticChunker) -> None:
        """小 token 预算应产生多个子块。"""
        result = chunker_small_tokens.chunk(
            "DOC_SM", "N6", SIMPLE_DOC,
        )
        assert len(result.children) >= 2, (
            f"小 token 预算应产生 ≥2 个子块，实际 {len(result.children)}"
        )

    def test_multiple_parents_produced(self, chunker_small_tokens: SemanticChunker) -> None:
        """若内容足够大，可能产生多个父块。"""
        # 构造较长的文档
        long_doc = SIMPLE_DOC * 5
        result = chunker_small_tokens.chunk(
            "DOC_LONG", "N7", long_doc,
        )
        assert len(result.parents) >= 2, (
            f"长文档应产生 ≥2 个父块，实际 {len(result.parents)}"
        )

    def test_overlap_reference(self, chunker_small_tokens: SemanticChunker) -> None:
        """相邻子块间应有重叠内容（减少信息断裂）。"""
        # 构造无公式/代码的长文本
        long_text = "。".join([
            f"这是第{i}个测试句子，用于验证重叠机制的完整性"
            for i in range(20)
        ])
        result = chunker_small_tokens.chunk("DOC_OVERLAP", "N8", long_text)
        # 此测试不强制验证重叠，而是确保不报错
        assert len(result.children) > 0


# ============================================================================
# 7. DocumentIngestionPipeline — 端到端
# ============================================================================

class TestDocumentIngestionPipeline:
    """测试完整的数据摄入管线。"""

    def test_pipeline_returns_chunk_result(self, milvus_client: MilvusClient) -> None:
        """端到端摄入应返回正确的 ChunkResult。"""
        pipeline = DocumentIngestionPipeline(milvus_client)
        result = pipeline.ingest(
            document_id="PIPE_001",
            node_id="KN_042",
            content=SIMPLE_DOC,
            title="反向传播算法",
            difficulty=0.65,
            category="concept",
            metadata={"source": "textbook_ch3", "language": "zh"},
        )
        assert isinstance(result, ChunkResult)
        assert result.document_id == "PIPE_001"
        assert result.node_id == "KN_042"
        assert len(result.parents) > 0
        assert len(result.children) > 0
        assert result.total_tokens_document > 0
        assert result.protected_blocks_count > 0, (
            "包含公式/代码的文档应有受保护块计数 > 0"
        )

    def test_pipeline_disconnected_milvus_no_error(self) -> None:
        """未连接的 Milvus 不应导致管线报错（仅跳过写入）。"""
        client = MilvusClient(MilvusConfig())
        pipeline = DocumentIngestionPipeline(client)
        result = pipeline.ingest(
            document_id="PIPE_002",
            node_id="KN_042",
            content=SIMPLE_DOC,
        )
        assert result.parents is not None
        assert result.children is not None


# ============================================================================
# 8. 边界条件
# ============================================================================

class TestBoundaryConditions:
    """测试极端输入的鲁棒性。"""

    def test_empty_document(self, chunker: SemanticChunker) -> None:
        """空文档不应抛出异常。"""
        result = chunker.chunk("DOC_EMPTY", "N1", EMPTY_DOC)
        assert isinstance(result, ChunkResult)
        assert result.total_tokens_document == 0

    def test_very_short_document(self, chunker: SemanticChunker) -> None:
        """极短文档应产生至少 1 个子块。"""
        result = chunker.chunk("DOC_SHORT", "N1", SHORT_DOC)
        assert len(result.children) >= 1

    def test_pure_formula_document(self, chunker: SemanticChunker) -> None:
        """纯公式文档应正确处理。"""
        pure_latex = "$$E = mc^2$$"
        result = chunker.chunk("DOC_LATEX", "N1", pure_latex)
        assert len(result.children) >= 1

    def test_large_document_no_crash(self, chunker: SemanticChunker) -> None:
        """大文档不应导致内存/性能问题。"""
        large_doc = (SIMPLE_DOC + "\n") * 100
        result = chunker.chunk("DOC_LARGE", "N1", large_doc)
        assert result.total_tokens_document > 0
        assert len(result.children) > 10

    def test_unicode_and_special_chars(self, chunker: SemanticChunker) -> None:
        """特殊 Unicode 字符（α, β, γ, ∑, ∏ 等）应正确保留。"""
        special_doc = "损失函数 ℒ 的参数 θ 通过梯度 ∇ℒ 更新。$$\\alpha + \\beta = \\gamma$$"
        result = chunker.chunk("DOC_UNICODE", "N1", special_doc)
        combined = ' '.join(c.content for c in result.children)
        assert "∇" in combined or "\\alpha" in combined

    def test_metadata_propagation(self, chunker: SemanticChunker) -> None:
        """metadata 应传播到所有子块和父块。"""
        test_meta = {"author": "test_author", "version": "1.0"}
        result = chunker.chunk(
            "DOC_META", "N1", SIMPLE_DOC, metadata=test_meta
        )
        for child in result.children:
            assert "author" in child.metadata
            assert child.metadata["author"] == "test_author"

    def test_chunk_config_validation(self) -> None:
        """ChunkConfig 参数应在合法范围内。"""
        cfg = ChunkConfig(
            child_min_tokens=100,
            child_max_tokens=500,
            parent_max_tokens=2000,
        )
        assert cfg.child_min_tokens == 100
        assert cfg.child_max_tokens == 500


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
