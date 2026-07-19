from src.validation.language import (
    is_chinese_learning_content,
    is_chinese_mermaid_text,
    non_chinese_tutor_fields,
)


def test_chinese_contract_rejects_english_explanations_disguised_as_titles():
    assert not is_chinese_learning_content(
        "This answer is entirely in English and explains the algorithm."
    )
    assert not is_chinese_learning_content(
        "This Is A Complete English Explanation For Students"
    )
    assert not is_chinese_learning_content("Runtime Complexity Overview")
    assert not is_chinese_learning_content("Common Runtime Pitfalls")
    assert not is_chinese_learning_content("Binary Search Tree")
    assert not is_chinese_learning_content(
        "这是用于帮助学生理解的中文前言。Binary tree insertion works recursively."
    )
    assert not is_chinese_learning_content(
        "THIS IS AN ENTIRELY ENGLISH EXPLANATION FOR STUDENTS"
    )
    assert not is_chinese_learning_content("Input -> Process -> Output")
    assert not is_chinese_learning_content("这是中文。 TREES GROW TALL")
    assert not is_chinese_learning_content("中文提示：USERS NEED HELP")
    assert not is_chinese_learning_content("这是中文。 BOOKS MAKE KIDS SMART")
    assert not is_chinese_learning_content("这是中文。 TREES, GROW, TALL")
    assert not is_chinese_learning_content("中文提示：USERS, NEED, HELP")
    assert not is_chinese_learning_content("这是中文。 BOOKS / MAKE / KIDS / SMART")


def test_chinese_contract_allows_code_formulas_symbols_and_technical_names():
    assert is_chinese_learning_content("Dijkstra")
    assert is_chinese_learning_content("Node.js")
    assert is_chinese_learning_content("scikit-learn")
    assert is_chinese_learning_content("N01")
    assert is_chinese_learning_content("Gödel")
    assert is_chinese_learning_content("René Descartes")
    assert is_chinese_learning_content("Bézier curve")
    assert is_chinese_learning_content("使用 HTTP API 和 BFS 完成遍历。")
    assert is_chinese_learning_content(
        "使用 CNN 处理图像，AVL 树通过旋转保持平衡，并用 KMP、DP、DAG 和 MST 求解。"
    )
    assert is_chinese_learning_content("使用 XYZ、ABC 表示两个自定义模块。")
    assert is_chinese_learning_content(
        "本节介绍 Visual Studio Code、OpenAI API 和 TensorFlow Dataset 的用法。"
    )
    assert is_chinese_learning_content(
        "使用 Dijkstra 算法计算 d[v] = min(d[v], d[u] + w(u,v))。"
    )
    assert is_chinese_learning_content("d[v] = min(d[v], d[u] + w(u,v))")
    assert is_chinese_learning_content("$T(n)=O(n\\log n)$")
    assert is_chinese_learning_content(
        "公式 α + β + γ + δ + ε = 1 表示五个参数之和。"
    )
    assert is_chinese_learning_content(
        '```python\n# Keep this code comment in English.\nprint("hello")\n```'
    )
    assert is_chinese_learning_content(
        '    # Keep this code comment in English.\n    print("hello")'
    )
    assert is_chinese_learning_content(
        '概念关系如下：\n```mermaid\ngraph TD\nA[问题] --> B[答案]\n```'
    )


def test_chinese_contract_rejects_prose_hidden_as_code_formula_or_another_language():
    assert not is_chinese_learning_content(
        "中文前言 `This is a complete English explanation (hidden)`"
    )
    assert not is_chinese_learning_content(
        "中文前言\n```text\nThis is a complete English explanation.\n```"
    )
    assert not is_chinese_learning_content(
        "```python\nThis is prose disguised as Python output.\n```"
    )
    assert not is_chinese_learning_content("Check value = next item carefully")
    assert not is_chinese_learning_content(
        "Runtime grows rapidly (quadratic complexity)"
    )
    assert not is_chinese_learning_content("これは日本語の説明です。")
    assert not is_chinese_learning_content("日本語説明")
    assert not is_chinese_learning_content("Это русское объяснение.")
    assert not is_chinese_learning_content("Αυτό είναι ελληνική εξήγηση.")
    assert not is_chinese_learning_content(
        "Αυτό είναι ελληνική εξήγηση και α + β = γ"
    )


def test_tutor_code_example_requires_code_instead_of_disguised_prose():
    assert non_chinese_tutor_fields({
        "text_explanation": "这是中文讲解。",
        "code_example": "def visit(node):\n    return node",
    }) == []
    assert non_chinese_tutor_fields({
        "text_explanation": "这是中文讲解。",
        "code_example": "THE FUNCTION RETURNS AN EMPTY LIST",
    }) == ["code_example"]
    assert non_chinese_tutor_fields({
        "text_explanation": "这是中文讲解。",
        "code_example": "Explanation: This function returns a list.",
    }) == ["code_example"]


def test_mermaid_contract_checks_visible_labels_without_rejecting_names_or_formulas():
    assert not is_chinese_mermaid_text("graph TD\nQuestion --> Answer")
    assert not is_chinese_mermaid_text(
        'graph TD\nA["Question"] --> B["Key concept"]'
    )
    assert not is_chinese_mermaid_text(
        "graph TD\nsubgraph English Section\nA[问题] --> B[答案]\nend"
    )
    assert not is_chinese_mermaid_text(
        "graph TD\nA[日本語説明] --> B[答案]"
    )
    assert not is_chinese_mermaid_text(
        "sequenceDiagram\nAlice->>Bob: Explain the answer"
    )
    assert not is_chinese_mermaid_text(
        "gantt\ntitle English study plan"
    )
    assert not is_chinese_mermaid_text(
        "graph TD\nA[DATABASE CACHE] --> B[QUERY EXECUTION]"
    )
    assert is_chinese_mermaid_text(
        'graph TD\nA["Dijkstra"] --> B["最短路径"]'
    )
    assert is_chinese_mermaid_text(
        'graph TD\nA["Gödel"] --> B["编码"]'
    )
    assert is_chinese_mermaid_text(
        'graph TD\nA["CNN"] --> B["特征提取"]\nB --> C["KMP"]'
    )
    assert is_chinese_mermaid_text(
        'graph TD\nA["O(n log n)"] --> B["复杂度"]'
    )
    assert is_chinese_mermaid_text(
        '%%{init: {"theme": "base"}}%%\n'
        'graph TD\nA["OpenAI API"] --> B["调用结果"]'
    )
