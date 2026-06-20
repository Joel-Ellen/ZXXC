# -*- coding: utf-8 -*-

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.vector.elasticsearch_knowledge_base import (  # noqa: E402
    ElasticsearchKnowledgeBaseClient,
    ElasticsearchKnowledgeBaseConfig,
    HashingTextEmbedder,
    MarkdownKnowledgeBaseChunker,
)


LONG_EXPLANATION = (
    "AVL 树在插入后可能失衡，需要通过旋转恢复平衡。"
    "为了保证检索时不丢失上下文，这里保留定义、失衡条件、旋转步骤、复杂度和实现细节。"
    "如果把这段内容简单按字数截断，就容易把复杂度公式、旋转前提和代码实现切散。"
    "因此切块必须遵循标题层级，并在接近上限时优先选择自然边界，而不是粗暴截断。"
) * 4

SAMPLE_MD = """# 第 3 章 树与二叉树

## 3.4 平衡二叉树 AVL

### AVL 树的 LL 型旋转

__LONG_EXPLANATION__

时间复杂度通常记为 $O(\\log n)$。

```cpp
struct Node {
    int val;
    Node* left;
    Node* right;
    int height;
};

Node* rotateRight(Node* y) {
    Node* x = y->left;
    Node* T2 = x->right;
    x->right = y;
    y->left = T2;
    return x;
}
```

旋转后需要更新节点高度，并继续向上检查祖先节点。

### AVL 树的 RR 型旋转

与 LL 型旋转对称，依旧保持局部有序性。
"""
SAMPLE_MD = SAMPLE_MD.replace("__LONG_EXPLANATION__", LONG_EXPLANATION)


def make_chunker() -> MarkdownKnowledgeBaseChunker:
    return MarkdownKnowledgeBaseChunker(
        ElasticsearchKnowledgeBaseConfig(
            chunk_size_chars=800,
            chunk_overlap_chars=150,
        )
    )


def test_header_metadata_inheritance() -> None:
    chunker = make_chunker()
    chunks = chunker.chunk_markdown(
        SAMPLE_MD,
        document_id="ds_avl",
        source_path="C:/kb/数据结构-知识库.md",
    )

    assert len(chunks) >= 2
    first = chunks[0]
    assert first.chapter == "第 3 章 树与二叉树"
    assert first.section == "3.4 平衡二叉树 AVL"
    assert first.knowledge_point == "AVL 树的 LL 型旋转"
    assert first.title_path == "数据结构 > 第 3 章 树与二叉树 > 3.4 平衡二叉树 AVL > AVL 树的 LL 型旋转"


def test_code_fence_is_not_truncated() -> None:
    chunker = make_chunker()
    chunks = chunker.chunk_markdown(
        SAMPLE_MD,
        document_id="ds_avl",
        source_path="C:/kb/数据结构-知识库.md",
    )

    code_chunks = [chunk for chunk in chunks if chunk.has_code_block]
    assert code_chunks, "Expected at least one chunk containing a fenced code block."
    for chunk in code_chunks:
        assert chunk.content.count("```") % 2 == 0
        assert "rotateRight" in chunk.content
        assert "Node* T2 = x->right;" in chunk.content


def test_language_tags_and_formula_detection() -> None:
    chunker = make_chunker()
    chunks = chunker.chunk_markdown(
        SAMPLE_MD,
        document_id="ds_avl",
        source_path="C:/kb/数据结构-知识库.md",
    )

    merged_languages = {tag for chunk in chunks for tag in chunk.language_tags}
    assert "C++" in merged_languages
    assert any(chunk.has_latex for chunk in chunks)


def test_rrf_request_contains_standard_and_knn() -> None:
    client = ElasticsearchKnowledgeBaseClient(
        ElasticsearchKnowledgeBaseConfig(vector_dims=64)
    )
    body = client.build_rrf_search_body(
        query="AVL 树 LL 旋转",
        query_vector=[0.1] * 64,
        top_k=5,
        filters={"chapter.keyword": "第 3 章 树与二叉树"},
    )

    retrievers = body["retriever"]["rrf"]["retrievers"]
    assert len(retrievers) == 2
    assert "standard" in retrievers[0]
    assert "knn" in retrievers[1]
    assert body["size"] == 5
    assert retrievers[1]["knn"]["field"] == "embedding"
    assert retrievers[1]["knn"]["filter"] == [
        {"term": {"chapter.keyword": "第 3 章 树与二叉树"}}
    ]


def test_hashing_embedder_returns_stable_vector() -> None:
    embedder = HashingTextEmbedder(dims=64)

    vector = embedder.embed("AVL 树 LL 旋转 O(log n)")
    same_vector = embedder.embed("AVL 树 LL 旋转 O(log n)")
    batch = embedder.embed_batch(["AVL", "红黑树"])

    assert len(vector) == 64
    assert vector == same_vector
    assert len(batch) == 2
    assert all(len(item) == 64 for item in batch)
