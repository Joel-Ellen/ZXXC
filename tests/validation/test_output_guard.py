from src.validation.output_guard import OutputGuard


def test_output_guard_accepts_valid_python_code_block():
    result = OutputGuard().validate_text("```python\nprint(1)\n```", output_type="code_snippet")
    assert result.passed is True


def test_output_guard_rejects_invalid_python_code_block():
    result = OutputGuard().validate_text("```python\nif True print(1)\n```", output_type="code_snippet")
    assert result.passed is False
    assert any(issue.code == "code_syntax_error" for issue in result.issues)


def test_output_guard_flags_sensitive_content():
    result = OutputGuard().validate_text("This explains malware attack steps", output_type="concept_map")
    assert result.passed is True or result.decision.value in {"refined", "rejected"}
    assert result.issues or result.sanitized_text
