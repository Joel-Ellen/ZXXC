# -*- coding: utf-8 -*-
"""Repro + fix verification for the code_snippet read-gate asymmetry."""
from src.resource_generation.prompts import render_markdown
from src.validation.language import non_chinese_resource_fields, is_chinese_learning_content

base = {
    'render_type': 'code_snippet', 'language': 'c', 'content_language': 'zh-CN',
    'title': '二叉搜索树',
    'code': 'int f(void){return 0;}',
    'scenario': '比较 BST 与 AVL 的查找路径。',
    'explanation': 'BST 最坏退化为链表，AVL 通过旋转保持平衡。',
    'walkthrough_steps': ['构造 BST。', '插入有序序列观察退化。'],
    'complexity_notes': ['BST 最坏 O(n)，AVL 稳定 O(log n)。'],
    'pitfalls': ['忽略 BST AVL 的高度差别。'],
    'prerequisites': ['先了解二叉树。'],
    'experiments': ['试试逆序插入。'],
    'boundary_tests': [{'name': '空树', 'input': 'root = NULL', 'expected': 'return 0'}],
    'objective_ids': ['O1'],
    'evidence_map': {'scenario': ['r1'], 'explanation': ['r1'], 'complexity_notes': ['r1']},
    'source_ref_ids': ['r1'],
}

gen = non_chinese_resource_fields(base)
md = render_markdown('code_snippet', base)
print('payload check (shared by gen+read):', gen or 'PASS')
print('rendered-body check (read-only extra):',
      'PASS' if is_chinese_learning_content(md) else 'FAIL -> card silently dropped before fix')

from src.state.agent_state import ResourceCard
from src.application import resource_service as rs

card = ResourceCard(resource_id='x', node_id='N01', card_type='code_snippet', content=md,
                    metadata={'structured_payload': base})
print('read gate AFTER fix:', rs._resource_card_language_valid(card, 'zh-CN'))

# Also confirm python cards still rejected (existing contract must hold)
py_card = ResourceCard(resource_id='y', node_id='N01', card_type='code_snippet',
                       content='## 示例\n\n```python\ndef f():\n    return 1\n```',
                       metadata={'structured_payload': {'language': 'python', 'code': 'def f():\n    return 1'}})
print('python card still rejected:', rs._resource_card_language_valid(py_card, 'zh-CN') is False)

# And English prose in payload still rejected via shared payload walk
bad = dict(base)
bad['explanation'] = 'We iterate over each element and accumulate the total.'
bad_md = render_markdown('code_snippet', bad)
bad_card = ResourceCard(resource_id='z', node_id='N01', card_type='code_snippet', content=bad_md,
                        metadata={'structured_payload': bad})
print('english-prose payload still rejected:', rs._resource_card_language_valid(bad_card, 'zh-CN') is False)
