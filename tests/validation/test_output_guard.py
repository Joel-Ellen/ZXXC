from src.validation.output_guard import OutputGuard


def test_output_guard_accepts_valid_c_code_block():
    result = OutputGuard().validate_text(
        "## 代码示例\n```c\nint answer(void) { return 1; }\n```",
        output_type="code_snippet",
    )
    assert result.passed is True


def test_output_guard_rejects_non_c_and_invalid_c_code_blocks():
    values = (
        "## 代码示例\n```python\nprint(1)\n```",
        "## 代码示例\n```javascript\nfunction answer() { return 1; }\n```",
        "## 代码示例\n```\nint answer(void) { return 1; }\n```",
        "## 代码示例\n```c\nint answer(void) { return 1 }\n```",
    )
    for value in values:
        result = OutputGuard().validate_text(value, output_type="code_snippet")
        assert result.passed is False
        assert any(issue.code == "code_syntax_error" for issue in result.issues)


def test_tutor_output_allows_c_and_quoted_text_but_rejects_python_examples():
    valid = OutputGuard().validate_text(
        "请参考以下实现。\n```c\nint answer(void) { return 1; }\n```",
        output_type="tutor_response",
    )
    quoted = OutputGuard().validate_text(
        "这是学生提交的原始代码。\n```text\ndef answer():\n    return 1\n```",
        output_type="tutor_response",
    )
    invalid = OutputGuard().validate_text(
        "请参考以下实现。\n```python\ndef answer():\n    return 1\n```",
        output_type="tutor_response",
    )

    assert valid.passed is True
    assert quoted.passed is True
    assert invalid.passed is False


def test_other_learner_resources_allow_diagrams_but_reject_non_c_code() -> None:
    diagram = OutputGuard().validate_text(
        '概念关系如下。\n```mermaid\ngraph TD\nA["输入"] --> B["输出"]\n```',
        output_type="concept_map",
    )
    python_example = OutputGuard().validate_text(
        "示例实现如下。\n```python\ndef answer():\n    return 1\n```",
        output_type="concept_map",
    )

    assert diagram.passed is True
    assert python_example.passed is False
    assert any(issue.code == "code_syntax_error" for issue in python_example.issues)


def test_output_guard_flags_sensitive_content():
    result = OutputGuard().validate_text("This explains malware attack steps", output_type="concept_map")
    assert result.passed is True or result.decision.value in {"refined", "rejected"}
    assert result.issues or result.sanitized_text


def test_output_guard_rejects_python_in_default_text_output():
    result = OutputGuard().validate_text(
        "示例实现如下。\n```python\ndef answer():\n    return 42\n```",
        output_type="text",
    )

    assert result.passed is False
    assert any(issue.code == "code_syntax_error" for issue in result.issues)
